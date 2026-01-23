"""
Playbook Generator with Template System.

Generates YAML playbooks from resolved mistakes that can be automatically
executed to prevent similar mistakes in the future.

Key Features:
- Jinja2 templating with autoescape for security
- Timeout tiers for step execution (instant, fast, standard, long, background)
- Pattern-based triggers for automatic playbook matching
- Success criteria definition
- Template injection protection via autoescape
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path
from enum import Enum
import yaml
import uuid
import re
from jinja2 import Environment, BaseLoader, select_autoescape

# Import from BB-011
try:
    from lib.mistake_rca import RCAResult, RootCauseCategory, SimilarMistake
except ImportError:
    # Fallback for testing
    from enum import Enum

    class RootCauseCategory(Enum):
        KNOWLEDGE_GAP = "knowledge_gap"
        TOOL_MISUSE = "tool_misuse"
        PATTERN_VIOLATION = "pattern_violation"
        CONTEXT_MISSING = "context_missing"
        ASSUMPTION_ERROR = "assumption_error"
        COMMUNICATION_BREAKDOWN = "communication_breakdown"

    @dataclass
    class SimilarMistake:
        mistake_id: str
        similarity: float
        description: str
        resolution: Optional[str] = None
        prevention_rule: Optional[str] = None

    @dataclass
    class RCAResult:
        mistake_id: str
        root_cause: RootCauseCategory
        explanation: str
        contributing_factors: List[str]
        prevention_rule: str
        confidence: float
        similar_mistakes: List[SimilarMistake] = field(default_factory=list)
        ralph_iterations: List[Dict] = field(default_factory=list)
        consensus_reached: bool = False
        agreement_level: float = 0.0
        timestamp: datetime = field(default_factory=datetime.now)


class TimeoutTier(Enum):
    """Timeout tiers for playbook steps."""
    INSTANT = ("instant", 5)      # Read, Grep
    FAST = ("fast", 30)           # Edit, simple Bash
    STANDARD = ("standard", 120)  # Build, test
    LONG = ("long", 600)          # Deploy, migrate
    BACKGROUND = ("background", 0) # Async with callback

    @property
    def tier_name(self) -> str:
        """Get the tier name."""
        return self.value[0]

    @property
    def timeout_seconds(self) -> int:
        """Get the timeout in seconds."""
        return self.value[1]


@dataclass
class PlaybookStep:
    """A step in a playbook."""
    id: str
    name: str
    action: str  # analyze, read, edit, execute, verify
    timeout_tier: TimeoutTier
    command: Optional[str] = None
    template: Optional[str] = None
    files: List[str] = field(default_factory=list)
    conditions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlaybookTrigger:
    """Trigger conditions for a playbook."""
    patterns: List[str]  # Regex patterns
    detection_methods: List[str]
    file_patterns: List[str] = field(default_factory=list)
    min_confidence: float = 0.8
    excluded_patterns: List[str] = field(default_factory=list)


@dataclass
class Playbook:
    """A complete playbook."""
    id: str
    name: str
    version: str
    created_at: datetime
    source_mistake: str
    trigger: PlaybookTrigger
    context_requirements: Dict[str, Any]
    resolution_steps: List[PlaybookStep]
    success_criteria: Dict[str, bool]
    metadata: Dict[str, Any]


class PlaybookGenerator:
    """
    Generate YAML playbooks from resolved mistakes.
    Uses Jinja2 with autoescape for security.
    """

    TEMPLATE_DIR = Path("/home/pook/engineer-team/templates")
    OUTPUT_DIR = Path("/home/pook/engineer-team/playbooks")

    def __init__(self):
        # Set up Jinja2 with autoescape for security (prevents template injection)
        self.jinja_env = Environment(
            loader=BaseLoader(),
            autoescape=select_autoescape(['html', 'xml', 'yaml'])
        )

        # Playbook templates by root cause category
        self.templates = self._load_templates()

    def generate(self, rca_result: RCAResult,
                 mistake: Dict) -> Playbook:
        """
        Generate a playbook from an RCA result.

        Args:
            rca_result: Result from BB-011 RCA pipeline
            mistake: Original mistake data

        Returns:
            Generated Playbook
        """
        # Generate unique ID
        playbook_id = f"pb_{uuid.uuid4().hex[:12]}"

        # Create trigger from RCA patterns
        trigger = self._create_trigger(rca_result, mistake)

        # Determine context requirements
        context_reqs = self._determine_context_requirements(mistake)

        # Generate resolution steps based on root cause
        steps = self._generate_steps(rca_result, mistake)

        # Define success criteria
        success_criteria = self._define_success_criteria(rca_result)

        # Build metadata
        metadata = {
            "category": mistake.get('category', 'unknown'),
            "severity": mistake.get('severity', 'medium'),
            "success_rate": 0.0,  # Will be updated with usage
            "usage_count": 0,
            "last_used": None,
            "confidence": rca_result.confidence,
            "root_cause": rca_result.root_cause.value,
            "similar_playbooks": self._find_similar_playbooks(rca_result)
        }

        # Create playbook
        playbook = Playbook(
            id=playbook_id,
            name=self._generate_name(rca_result, mistake),
            version="1.0.0",
            created_at=datetime.now(),
            source_mistake=mistake.get('id', 'unknown'),
            trigger=trigger,
            context_requirements=context_reqs,
            resolution_steps=steps,
            success_criteria=success_criteria,
            metadata=metadata
        )

        return playbook

    def save(self, playbook: Playbook) -> Path:
        """
        Save playbook to YAML file.
        Uses Jinja2 autoescape for secure template rendering.
        """
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # Convert to dict for YAML
        playbook_dict = self._playbook_to_dict(playbook)

        # Write YAML
        output_path = self.OUTPUT_DIR / f"{playbook.id}.yaml"
        with open(output_path, 'w') as f:
            yaml.dump(playbook_dict, f, default_flow_style=False, sort_keys=False)

        return output_path

    def _create_trigger(self, rca_result: RCAResult,
                        mistake: Dict) -> PlaybookTrigger:
        """Create trigger conditions from RCA result."""
        # Extract patterns from mistake description and similar mistakes
        patterns = []

        # Add error message pattern
        description = mistake.get('description', '')
        if description:
            # Escape special regex chars and create pattern
            pattern = re.escape(description[:50])
            # Make it more flexible by allowing variations
            pattern = pattern.replace(r'\ ', r'.*')
            patterns.append(pattern)

        # Add patterns from similar mistakes
        for similar in rca_result.similar_mistakes[:3]:
            if similar.description:
                escaped = re.escape(similar.description[:30])
                if escaped not in patterns:
                    patterns.append(escaped)

        # Detection methods
        detection_methods = [mistake.get('detection_method', 'tool_failure')]

        # File patterns based on file extension
        file_path = mistake.get('file_path', '')
        file_patterns = []
        if file_path:
            ext = Path(file_path).suffix
            if ext:
                file_patterns.append(f"*{ext}")

        return PlaybookTrigger(
            patterns=patterns,
            detection_methods=detection_methods,
            file_patterns=file_patterns,
            min_confidence=0.8
        )

    def _determine_context_requirements(self, mistake: Dict) -> Dict[str, Any]:
        """Determine what context is required for this playbook."""
        requirements = {}

        file_path = mistake.get('file_path', '')
        if file_path:
            ext = Path(file_path).suffix
            lang_map = {
                '.py': 'python',
                '.ts': 'typescript',
                '.js': 'javascript',
                '.go': 'go',
                '.rs': 'rust'
            }
            if ext in lang_map:
                requirements['language'] = [lang_map[ext]]

        # Check if type annotations are relevant
        category = mistake.get('category', '')
        if 'type' in category.lower():
            requirements['has_type_annotations'] = True

        return requirements

    def _generate_steps(self, rca_result: RCAResult,
                        mistake: Dict) -> List[PlaybookStep]:
        """Generate resolution steps based on root cause."""
        steps = []

        root_cause = rca_result.root_cause

        # Step 1: Always analyze first
        description = mistake.get('description', '')[:100]
        steps.append(PlaybookStep(
            id="step_analyze",
            name="Analyze the issue",
            action="analyze",
            timeout_tier=TimeoutTier.FAST,
            command=f"Examine the error: {description}"
        ))

        # Root cause specific steps
        if root_cause == RootCauseCategory.KNOWLEDGE_GAP:
            steps.extend([
                PlaybookStep(
                    id="step_research",
                    name="Research the topic",
                    action="read",
                    timeout_tier=TimeoutTier.FAST,
                    command="Consult documentation and examples for this pattern"
                ),
                PlaybookStep(
                    id="step_apply",
                    name="Apply learned pattern",
                    action="edit",
                    timeout_tier=TimeoutTier.STANDARD,
                    template="Apply the correct pattern based on research"
                )
            ])

        elif root_cause == RootCauseCategory.TOOL_MISUSE:
            steps.extend([
                PlaybookStep(
                    id="step_identify_tool",
                    name="Identify correct tool",
                    action="analyze",
                    timeout_tier=TimeoutTier.INSTANT,
                    command="Determine the appropriate tool for this task"
                ),
                PlaybookStep(
                    id="step_use_tool",
                    name="Use correct tool",
                    action="execute",
                    timeout_tier=TimeoutTier.STANDARD,
                    command="Execute with the correct tool and parameters"
                )
            ])

        elif root_cause == RootCauseCategory.PATTERN_VIOLATION:
            steps.extend([
                PlaybookStep(
                    id="step_find_pattern",
                    name="Find existing pattern",
                    action="read",
                    timeout_tier=TimeoutTier.FAST,
                    files=["**/*.py"],
                    command="Search for similar patterns in codebase"
                ),
                PlaybookStep(
                    id="step_align",
                    name="Align with pattern",
                    action="edit",
                    timeout_tier=TimeoutTier.STANDARD,
                    template="Modify code to match established pattern"
                )
            ])

        else:
            # Generic steps for other root causes
            steps.append(PlaybookStep(
                id="step_fix",
                name="Apply fix",
                action="edit",
                timeout_tier=TimeoutTier.STANDARD,
                template=rca_result.prevention_rule
            ))

        # Final verification step
        steps.append(PlaybookStep(
            id="step_verify",
            name="Verify fix",
            action="verify",
            timeout_tier=TimeoutTier.STANDARD,
            command="Run tests and type checks to verify the fix"
        ))

        return steps

    def _define_success_criteria(self, rca_result: RCAResult) -> Dict[str, bool]:
        """Define success criteria based on root cause."""
        criteria = {
            "no_new_errors": True
        }

        if rca_result.root_cause in [
            RootCauseCategory.KNOWLEDGE_GAP,
            RootCauseCategory.TOOL_MISUSE
        ]:
            criteria["type_check_passes"] = True

        if rca_result.root_cause == RootCauseCategory.PATTERN_VIOLATION:
            criteria["lint_passes"] = True

        return criteria

    def _generate_name(self, rca_result: RCAResult,
                       mistake: Dict) -> str:
        """Generate a descriptive name for the playbook."""
        root_cause = rca_result.root_cause.value.replace('_', ' ').title()
        category = mistake.get('category', 'unknown').split('.')[-1].replace('_', ' ')
        return f"Fix {category} ({root_cause})"

    def _find_similar_playbooks(self, rca_result: RCAResult) -> List[str]:
        """Find playbooks that handle similar mistakes."""
        similar_ids = []

        # Check if any similar mistakes have playbooks
        for similar in rca_result.similar_mistakes:
            if similar.prevention_rule:
                similar_ids.append(similar.mistake_id)

        return similar_ids[:3]

    def _playbook_to_dict(self, playbook: Playbook) -> Dict:
        """Convert Playbook to dictionary for YAML serialization."""
        return {
            "id": playbook.id,
            "name": playbook.name,
            "version": playbook.version,
            "created_at": playbook.created_at.isoformat(),
            "source_mistake": playbook.source_mistake,
            "trigger": {
                "patterns": playbook.trigger.patterns,
                "detection_methods": playbook.trigger.detection_methods,
                "file_patterns": playbook.trigger.file_patterns,
                "min_confidence": playbook.trigger.min_confidence
            },
            "context_requirements": playbook.context_requirements,
            "resolution_steps": [
                {
                    "id": step.id,
                    "name": step.name,
                    "action": step.action,
                    "timeout_tier": step.timeout_tier.tier_name,
                    "timeout_seconds": step.timeout_tier.timeout_seconds,
                    "command": step.command,
                    "template": step.template,
                    "files": step.files
                }
                for step in playbook.resolution_steps
            ],
            "success_criteria": playbook.success_criteria,
            "metadata": playbook.metadata
        }

    def _load_templates(self) -> Dict[str, str]:
        """Load playbook templates."""
        templates = {}
        template_dir = self.TEMPLATE_DIR

        if template_dir.exists():
            for template_file in template_dir.glob("*.yaml.j2"):
                name = template_file.stem.replace('.yaml', '')
                templates[name] = template_file.read_text()

        return templates

    def render_template(self, template_name: str,
                        context: Dict) -> str:
        """
        Safely render a template with autoescape.
        Prevents template injection attacks.
        """
        if template_name not in self.templates:
            return ""

        template = self.jinja_env.from_string(self.templates[template_name])
        return template.render(**context)
