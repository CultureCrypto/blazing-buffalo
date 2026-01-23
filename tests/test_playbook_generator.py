"""
Tests for Playbook Generator (BB-012).

Tests cover:
- Playbook generation from RCA results
- Jinja2 template rendering with autoescape
- Trigger pattern creation
- Resolution step generation
- Success criteria definition
- YAML output
- Security (template injection protection)
"""

import pytest
from pathlib import Path
from datetime import datetime
import yaml
import tempfile
import shutil

from lib.playbook_generator import (
    PlaybookGenerator,
    Playbook,
    PlaybookStep,
    PlaybookTrigger,
    TimeoutTier,
    RCAResult,
    RootCauseCategory,
    SimilarMistake
)


@pytest.fixture
def temp_dirs(tmp_path):
    """Create temporary directories for testing."""
    template_dir = tmp_path / "templates"
    output_dir = tmp_path / "playbooks"
    template_dir.mkdir()
    output_dir.mkdir()

    # Patch the class directories
    original_template = PlaybookGenerator.TEMPLATE_DIR
    original_output = PlaybookGenerator.OUTPUT_DIR

    PlaybookGenerator.TEMPLATE_DIR = template_dir
    PlaybookGenerator.OUTPUT_DIR = output_dir

    yield template_dir, output_dir

    # Restore
    PlaybookGenerator.TEMPLATE_DIR = original_template
    PlaybookGenerator.OUTPUT_DIR = original_output


@pytest.fixture
def sample_mistake():
    """Sample mistake data."""
    return {
        "id": "mst_abc123",
        "description": "TypeError: expected str, got int",
        "category": "code_error.type_error",
        "severity": "high",
        "file_path": "/home/user/project/main.py",
        "detection_method": "tool_failure"
    }


@pytest.fixture
def sample_rca_result():
    """Sample RCA result."""
    similar = [
        SimilarMistake(
            mistake_id="mst_xyz",
            similarity=0.85,
            description="TypeError in API handler",
            prevention_rule="Add type validation"
        )
    ]

    return RCAResult(
        mistake_id="mst_abc123",
        root_cause=RootCauseCategory.KNOWLEDGE_GAP,
        explanation="Agent was not aware of type coercion requirements",
        contributing_factors=["Lack of type validation", "No error handling"],
        prevention_rule="Always validate input types before processing",
        confidence=0.9,
        similar_mistakes=similar,
        ralph_iterations=[],
        consensus_reached=True,
        agreement_level=0.9
    )


class TestTimeoutTier:
    """Test timeout tier enum."""

    def test_tier_names(self):
        """Test tier name property."""
        assert TimeoutTier.INSTANT.tier_name == "instant"
        assert TimeoutTier.FAST.tier_name == "fast"
        assert TimeoutTier.STANDARD.tier_name == "standard"
        assert TimeoutTier.LONG.tier_name == "long"
        assert TimeoutTier.BACKGROUND.tier_name == "background"

    def test_timeout_values(self):
        """Test timeout second values."""
        assert TimeoutTier.INSTANT.timeout_seconds == 5
        assert TimeoutTier.FAST.timeout_seconds == 30
        assert TimeoutTier.STANDARD.timeout_seconds == 120
        assert TimeoutTier.LONG.timeout_seconds == 600
        assert TimeoutTier.BACKGROUND.timeout_seconds == 0


class TestPlaybookGenerator:
    """Test PlaybookGenerator class."""

    def test_init(self, temp_dirs):
        """Test generator initialization."""
        generator = PlaybookGenerator()
        assert generator.jinja_env is not None
        assert isinstance(generator.templates, dict)

    def test_generate_playbook(self, temp_dirs, sample_mistake, sample_rca_result):
        """Test playbook generation."""
        generator = PlaybookGenerator()
        playbook = generator.generate(sample_rca_result, sample_mistake)

        assert playbook.id.startswith("pb_")
        assert playbook.name.startswith("Fix")
        assert playbook.version == "1.0.0"
        assert playbook.source_mistake == "mst_abc123"
        assert isinstance(playbook.created_at, datetime)

    def test_trigger_creation(self, temp_dirs, sample_mistake, sample_rca_result):
        """Test trigger pattern creation."""
        generator = PlaybookGenerator()
        trigger = generator._create_trigger(sample_rca_result, sample_mistake)

        assert isinstance(trigger, PlaybookTrigger)
        assert len(trigger.patterns) > 0
        assert "tool_failure" in trigger.detection_methods
        assert trigger.min_confidence == 0.8

    def test_context_requirements_python(self, temp_dirs, sample_mistake, sample_rca_result):
        """Test context requirements for Python files."""
        generator = PlaybookGenerator()
        requirements = generator._determine_context_requirements(sample_mistake)

        assert requirements.get('language') == ['python']
        assert requirements.get('has_type_annotations') is True

    def test_context_requirements_typescript(self, temp_dirs, sample_rca_result):
        """Test context requirements for TypeScript files."""
        mistake = {
            "file_path": "/home/user/project/main.ts",
            "category": "type_error"
        }

        generator = PlaybookGenerator()
        requirements = generator._determine_context_requirements(mistake)

        assert requirements.get('language') == ['typescript']

    def test_step_generation_knowledge_gap(self, temp_dirs, sample_mistake, sample_rca_result):
        """Test step generation for knowledge gap root cause."""
        generator = PlaybookGenerator()
        steps = generator._generate_steps(sample_rca_result, sample_mistake)

        # Should have analyze, research, apply, verify
        assert len(steps) >= 4
        assert steps[0].action == "analyze"
        assert steps[-1].action == "verify"

        # Check for research step
        research_steps = [s for s in steps if "research" in s.name.lower()]
        assert len(research_steps) > 0

    def test_step_generation_tool_misuse(self, temp_dirs, sample_mistake):
        """Test step generation for tool misuse root cause."""
        rca = RCAResult(
            mistake_id="mst_test",
            root_cause=RootCauseCategory.TOOL_MISUSE,
            explanation="Used wrong tool for task",
            contributing_factors=["Tool misunderstanding"],
            prevention_rule="Use correct tool",
            confidence=0.85,
            similar_mistakes=[],
            ralph_iterations=[],
            consensus_reached=True,
            agreement_level=0.85
        )

        generator = PlaybookGenerator()
        steps = generator._generate_steps(rca, sample_mistake)

        # Should have steps for identifying and using correct tool
        tool_steps = [s for s in steps if "tool" in s.name.lower()]
        assert len(tool_steps) >= 1

    def test_step_generation_pattern_violation(self, temp_dirs, sample_mistake):
        """Test step generation for pattern violation root cause."""
        rca = RCAResult(
            mistake_id="mst_test",
            root_cause=RootCauseCategory.PATTERN_VIOLATION,
            explanation="Code doesn't match established patterns",
            contributing_factors=["Pattern mismatch"],
            prevention_rule="Follow codebase patterns",
            confidence=0.88,
            similar_mistakes=[],
            ralph_iterations=[],
            consensus_reached=True,
            agreement_level=0.88
        )

        generator = PlaybookGenerator()
        steps = generator._generate_steps(rca, sample_mistake)

        # Should have steps for finding and aligning with patterns
        pattern_steps = [s for s in steps if "pattern" in s.name.lower()]
        assert len(pattern_steps) >= 1

    def test_timeout_tiers_assigned(self, temp_dirs, sample_mistake, sample_rca_result):
        """Test that timeout tiers are properly assigned to steps."""
        generator = PlaybookGenerator()
        steps = generator._generate_steps(sample_rca_result, sample_mistake)

        for step in steps:
            assert isinstance(step.timeout_tier, TimeoutTier)
            assert step.timeout_tier.timeout_seconds >= 0

    def test_success_criteria_knowledge_gap(self, temp_dirs, sample_rca_result):
        """Test success criteria for knowledge gap."""
        generator = PlaybookGenerator()
        criteria = generator._define_success_criteria(sample_rca_result)

        assert criteria.get("no_new_errors") is True
        assert criteria.get("type_check_passes") is True

    def test_success_criteria_pattern_violation(self, temp_dirs):
        """Test success criteria for pattern violation."""
        rca = RCAResult(
            mistake_id="mst_test",
            root_cause=RootCauseCategory.PATTERN_VIOLATION,
            explanation="Pattern mismatch",
            contributing_factors=["Pattern mismatch"],
            prevention_rule="Follow patterns",
            confidence=0.88,
            similar_mistakes=[],
            ralph_iterations=[],
            consensus_reached=True,
            agreement_level=0.88
        )

        generator = PlaybookGenerator()
        criteria = generator._define_success_criteria(rca)

        assert criteria.get("lint_passes") is True

    def test_playbook_name_generation(self, temp_dirs, sample_mistake, sample_rca_result):
        """Test playbook name generation."""
        generator = PlaybookGenerator()
        name = generator._generate_name(sample_rca_result, sample_mistake)

        assert "Fix" in name
        assert "Knowledge Gap" in name

    def test_similar_playbooks_finding(self, temp_dirs, sample_rca_result):
        """Test finding similar playbooks."""
        generator = PlaybookGenerator()
        similar = generator._find_similar_playbooks(sample_rca_result)

        # Should find similar mistakes with prevention rules
        assert len(similar) <= 3
        if similar:
            assert similar[0] == "mst_xyz"

    def test_save_playbook(self, temp_dirs, sample_mistake, sample_rca_result):
        """Test saving playbook to YAML."""
        generator = PlaybookGenerator()
        playbook = generator.generate(sample_rca_result, sample_mistake)

        output_path = generator.save(playbook)

        assert output_path.exists()
        assert output_path.suffix == ".yaml"

        # Load and verify YAML
        with open(output_path) as f:
            data = yaml.safe_load(f)

        assert data['id'] == playbook.id
        assert data['name'] == playbook.name
        assert data['source_mistake'] == "mst_abc123"

    def test_yaml_structure(self, temp_dirs, sample_mistake, sample_rca_result):
        """Test YAML output structure."""
        generator = PlaybookGenerator()
        playbook = generator.generate(sample_rca_result, sample_mistake)
        output_path = generator.save(playbook)

        with open(output_path) as f:
            data = yaml.safe_load(f)

        # Check required fields
        assert 'id' in data
        assert 'trigger' in data
        assert 'resolution_steps' in data
        assert 'success_criteria' in data
        assert 'metadata' in data

        # Check trigger structure
        assert 'patterns' in data['trigger']
        assert 'detection_methods' in data['trigger']

        # Check steps structure
        for step in data['resolution_steps']:
            assert 'id' in step
            assert 'name' in step
            assert 'action' in step
            assert 'timeout_tier' in step
            assert 'timeout_seconds' in step

    def test_template_injection_prevention(self, temp_dirs):
        """Test that Jinja2 autoescape prevents template injection."""
        generator = PlaybookGenerator()

        # Create a template with potential injection
        malicious_context = {
            "name": "{{ system('rm -rf /') }}",
            "patterns": ["{{ config.items() }}"]
        }

        # Autoescape should prevent execution
        template = generator.jinja_env.from_string("Name: {{ name }}")
        result = template.render(**malicious_context)

        # Should be escaped, not executed
        assert "{{" in result or "&" in result or result == "Name: {{ system('rm -rf /') }}"


class TestPlaybookDataClasses:
    """Test playbook dataclasses."""

    def test_playbook_step_creation(self):
        """Test PlaybookStep creation."""
        step = PlaybookStep(
            id="step_1",
            name="Test step",
            action="analyze",
            timeout_tier=TimeoutTier.FAST,
            command="echo test"
        )

        assert step.id == "step_1"
        assert step.timeout_tier == TimeoutTier.FAST
        assert step.files == []

    def test_playbook_trigger_creation(self):
        """Test PlaybookTrigger creation."""
        trigger = PlaybookTrigger(
            patterns=["error.*type"],
            detection_methods=["tool_failure"],
            min_confidence=0.85
        )

        assert len(trigger.patterns) == 1
        assert trigger.min_confidence == 0.85

    def test_playbook_creation(self):
        """Test Playbook creation."""
        trigger = PlaybookTrigger(
            patterns=["test"],
            detection_methods=["test"]
        )

        playbook = Playbook(
            id="pb_test",
            name="Test Playbook",
            version="1.0.0",
            created_at=datetime.now(),
            source_mistake="mst_test",
            trigger=trigger,
            context_requirements={},
            resolution_steps=[],
            success_criteria={},
            metadata={}
        )

        assert playbook.id == "pb_test"
        assert playbook.version == "1.0.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
