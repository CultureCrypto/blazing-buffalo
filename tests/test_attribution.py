"""
Tests for multi-agent attribution scoring.
"""

import pytest
from datetime import datetime, timedelta
from lib.attribution import (
    MistakeAttribution,
    AgentRole,
    AgentContribution,
    AttributionResult
)


@pytest.fixture
def attribution():
    """Create MistakeAttribution instance."""
    return MistakeAttribution()


@pytest.fixture
def simple_workflow():
    """Simple 3-agent workflow."""
    base_time = datetime(2026, 1, 21, 10, 0, 0)
    return [
        {
            "agent_id": "architect",
            "action": "design",
            "timestamp": base_time,
            "output": "Designed API schema",
            "files_modified": ["schema.py"]
        },
        {
            "agent_id": "backend-dev",
            "action": "implement",
            "timestamp": base_time + timedelta(minutes=5),
            "output": "Implemented endpoints",
            "files_modified": ["api.py"],
            "actions": ["write_code"]
        },
        {
            "agent_id": "qa-expert",
            "action": "test",
            "timestamp": base_time + timedelta(minutes=10),
            "output": "FAILED: TypeError on line 42",
            "actions": ["pytest", "test_api"]
        }
    ]


@pytest.fixture
def mistake_details():
    """Mistake detection details."""
    return {
        "detection_method": "test_failure",
        "detection_agent": "qa-expert",
        "error_type": "type_error",
        "error_location": {"file": "api.py", "line": 42}
    }


class TestTraceAgents:
    """Test agent tracing functionality."""

    def test_trace_basic_workflow(self, attribution, simple_workflow):
        """Should extract unique agents in order."""
        agents = attribution.trace_agents("mst_001", simple_workflow)

        assert agents == ["architect", "backend-dev", "qa-expert"]
        assert "mst_001" in attribution.workflow_history

    def test_trace_duplicate_agents(self, attribution):
        """Should deduplicate repeated agents."""
        workflow = [
            {"agent_id": "agent-a", "action": "step1", "timestamp": datetime.utcnow()},
            {"agent_id": "agent-b", "action": "step2", "timestamp": datetime.utcnow()},
            {"agent_id": "agent-a", "action": "step3", "timestamp": datetime.utcnow()},
        ]

        agents = attribution.trace_agents("mst_002", workflow)

        assert agents == ["agent-a", "agent-b"]
        assert len(agents) == 2

    def test_trace_empty_workflow(self, attribution):
        """Should handle empty workflow."""
        agents = attribution.trace_agents("mst_003", [])

        assert agents == []

    def test_trace_missing_agent_ids(self, attribution):
        """Should skip steps without agent_id."""
        workflow = [
            {"agent_id": "agent-a", "action": "step1", "timestamp": datetime.utcnow()},
            {"action": "system-step", "timestamp": datetime.utcnow()},  # No agent_id
            {"agent_id": "agent-b", "action": "step2", "timestamp": datetime.utcnow()},
        ]

        agents = attribution.trace_agents("mst_004", workflow)

        assert agents == ["agent-a", "agent-b"]


class TestCalculateContribution:
    """Test contribution score calculation."""

    def test_originator_base_score(self, attribution):
        """Originator should get base weight of 0.5."""
        context = {
            'position_in_workflow': 0,
            'total_agents': 3,
            'time_with_mistake': 30,
            'had_opportunity_to_detect': False
        }

        score = attribution.calculate_contribution(
            "agent-1",
            AgentRole.ORIGINATOR,
            context
        )

        assert 0.4 <= score <= 0.6  # Should be around 0.5 with position factor

    def test_propagator_base_score(self, attribution):
        """Propagator should get base weight of 0.15."""
        context = {
            'position_in_workflow': 1,
            'total_agents': 3,
            'time_with_mistake': 30,
            'had_opportunity_to_detect': False
        }

        score = attribution.calculate_contribution(
            "agent-2",
            AgentRole.PROPAGATOR,
            context
        )

        assert 0.1 <= score <= 0.2

    def test_detector_negative_score(self, attribution):
        """Detector should get negative score (positive contribution)."""
        context = {
            'position_in_workflow': 2,
            'total_agents': 3,
            'time_with_mistake': 0,
            'had_opportunity_to_detect': True
        }

        score = attribution.calculate_contribution(
            "agent-3",
            AgentRole.DETECTOR,
            context
        )

        assert score == 0.0  # Clamped at 0

    def test_time_multiplier(self, attribution):
        """Long time with mistake should increase score."""
        context_short = {
            'position_in_workflow': 0,
            'total_agents': 2,
            'time_with_mistake': 30,  # 30 seconds
            'had_opportunity_to_detect': False
        }

        context_long = {
            'position_in_workflow': 0,
            'total_agents': 2,
            'time_with_mistake': 120,  # 2 minutes
            'had_opportunity_to_detect': False
        }

        score_short = attribution.calculate_contribution(
            "agent-1",
            AgentRole.ORIGINATOR,
            context_short
        )

        score_long = attribution.calculate_contribution(
            "agent-1",
            AgentRole.ORIGINATOR,
            context_long
        )

        assert score_long > score_short

    def test_opportunity_multiplier(self, attribution):
        """Having opportunity to detect should increase propagator score."""
        context_no_opp = {
            'position_in_workflow': 1,
            'total_agents': 3,
            'time_with_mistake': 30,
            'had_opportunity_to_detect': False
        }

        context_had_opp = {
            'position_in_workflow': 1,
            'total_agents': 3,
            'time_with_mistake': 30,
            'had_opportunity_to_detect': True
        }

        score_no_opp = attribution.calculate_contribution(
            "agent-2",
            AgentRole.PROPAGATOR,
            context_no_opp
        )

        score_had_opp = attribution.calculate_contribution(
            "agent-2",
            AgentRole.PROPAGATOR,
            context_had_opp
        )

        assert score_had_opp > score_no_opp

    def test_position_factor(self, attribution):
        """Earlier agents should get higher scores."""
        context_first = {
            'position_in_workflow': 0,
            'total_agents': 3,
            'time_with_mistake': 30,
            'had_opportunity_to_detect': False
        }

        context_last = {
            'position_in_workflow': 2,
            'total_agents': 3,
            'time_with_mistake': 30,
            'had_opportunity_to_detect': False
        }

        score_first = attribution.calculate_contribution(
            "agent-1",
            AgentRole.ORIGINATOR,
            context_first
        )

        score_last = attribution.calculate_contribution(
            "agent-3",
            AgentRole.ORIGINATOR,
            context_last
        )

        assert score_first > score_last


class TestAttributeFull:
    """Test full attribution analysis."""

    def test_basic_attribution(self, attribution, simple_workflow, mistake_details):
        """Should attribute mistake correctly."""
        result = attribution.attribute(
            "mst_001",
            simple_workflow,
            mistake_details
        )

        assert result.mistake_id == "mst_001"
        assert len(result.contributions) == 3
        assert result.workflow_trace == ["architect", "backend-dev", "qa-expert"]
        assert result.primary_responsible in ["architect", "backend-dev"]
        assert 0.0 <= result.confidence <= 1.0

    def test_originator_detection(self, attribution, simple_workflow, mistake_details):
        """First agent should be identified as originator."""
        result = attribution.attribute(
            "mst_002",
            simple_workflow,
            mistake_details
        )

        architect_contrib = next(c for c in result.contributions if c.agent_id == "architect")

        assert architect_contrib.role == AgentRole.ORIGINATOR

    def test_detector_identification(self, attribution, simple_workflow, mistake_details):
        """Detection agent should be identified as detector."""
        result = attribution.attribute(
            "mst_003",
            simple_workflow,
            mistake_details
        )

        qa_contrib = next(c for c in result.contributions if c.agent_id == "qa-expert")

        assert qa_contrib.role == AgentRole.DETECTOR

    def test_primary_responsible(self, attribution, simple_workflow, mistake_details):
        """Primary responsible should be agent with highest positive score."""
        result = attribution.attribute(
            "mst_004",
            simple_workflow,
            mistake_details
        )

        # Should not be the detector
        assert result.primary_responsible != "qa-expert"

        # Should be one of the agents who touched the code
        assert result.primary_responsible in ["architect", "backend-dev"]

    def test_confidence_calculation(self, attribution, simple_workflow, mistake_details):
        """Confidence should be reasonable for clear workflow."""
        result = attribution.attribute(
            "mst_005",
            simple_workflow,
            mistake_details
        )

        # Should have moderate to high confidence with clear roles
        assert result.confidence >= 0.5


class TestRoleDetermination:
    """Test role determination logic."""

    def test_detector_role(self, attribution):
        """Agent matching detection_agent should be detector."""
        role = attribution._determine_role(
            agent_id="qa-expert",
            step={"action": "test", "output": "Test failed"},
            position=2,
            workflow=[],
            mistake_details={"error_location": {}},
            detection_agent="qa-expert"
        )

        assert role == AgentRole.DETECTOR

    def test_resolver_role(self, attribution):
        """Agent with fix action should be resolver."""
        role = attribution._determine_role(
            agent_id="fixer",
            step={"action": "fix", "output": "Fixed the bug"},
            position=3,
            workflow=[],
            mistake_details={"error_location": {}},
            detection_agent="qa-expert"
        )

        assert role == AgentRole.RESOLVER

    def test_first_agent_originator(self, attribution):
        """First agent should be originator."""
        role = attribution._determine_role(
            agent_id="first-agent",
            step={"action": "create", "output": "Created file"},
            position=0,
            workflow=[],
            mistake_details={"error_location": {}},
            detection_agent="qa-expert"
        )

        assert role == AgentRole.ORIGINATOR

    def test_amplifier_role(self, attribution):
        """Agent that touched error file with error in output should be amplifier."""
        role = attribution._determine_role(
            agent_id="bad-agent",
            step={
                "action": "modify",
                "output": "Error: Something went wrong",
                "files_modified": ["api.py"]
            },
            position=1,
            workflow=[],
            mistake_details={"error_location": {"file": "api.py"}},
            detection_agent="qa-expert"
        )

        assert role == AgentRole.AMPLIFIER


class TestHelperMethods:
    """Test helper methods."""

    def test_calculate_time_with_mistake(self, attribution):
        """Should calculate time difference correctly."""
        workflow = [
            {"timestamp": datetime(2026, 1, 21, 10, 0, 0)},
            {"timestamp": datetime(2026, 1, 21, 10, 5, 0)},  # 5 minutes later
        ]

        time_diff = attribution._calculate_time_with_mistake(
            workflow,
            position=0,
            mistake_details={}
        )

        assert time_diff == 300.0  # 5 minutes = 300 seconds

    def test_had_opportunity_with_tests(self, attribution):
        """Should detect test actions as opportunity."""
        step = {"actions": ["pytest", "run_tests"]}

        assert attribution._had_opportunity(step, {}) is True

    def test_had_opportunity_without_tests(self, attribution):
        """Should return False when no test actions."""
        step = {"actions": ["write_code", "format"]}

        assert attribution._had_opportunity(step, {}) is False

    def test_confidence_with_clear_roles(self, attribution):
        """Should have high confidence with clear role distinctions."""
        contributions = [
            AgentContribution(
                agent_id="a1",
                role=AgentRole.ORIGINATOR,
                score=0.5,
                action="create",
                timestamp=datetime.utcnow()
            ),
            AgentContribution(
                agent_id="a2",
                role=AgentRole.DETECTOR,
                score=0.0,
                action="test",
                timestamp=datetime.utcnow()
            )
        ]

        confidence = attribution._calculate_confidence(
            contributions,
            [{}, {}, {}, {}, {}]  # 5 workflow steps
        )

        assert confidence >= 0.75  # Should be high with originator + detector


class TestNeo4jEmission:
    """Test Neo4j query generation."""

    def test_emit_to_neo4j(self, attribution, simple_workflow, mistake_details):
        """Should generate correct Neo4j queries."""
        result = attribution.attribute(
            "mst_006",
            simple_workflow,
            mistake_details
        )

        neo4j_data = attribution.emit_to_neo4j(result)

        assert 'queries' in neo4j_data
        assert len(neo4j_data['queries']) == 3  # One per agent
        assert neo4j_data['primary_responsible'] == result.primary_responsible
        assert neo4j_data['confidence'] == result.confidence

        # Check query structure
        first_query = neo4j_data['queries'][0]
        assert 'cypher' in first_query
        assert 'params' in first_query
        assert 'CONTRIBUTED_BY' in first_query['cypher']


class TestAgentStats:
    """Test agent statistics calculation."""

    def test_empty_stats(self, attribution):
        """Should return zero stats for no data."""
        stats = attribution.get_agent_stats("agent-1")

        assert stats['agent_id'] == "agent-1"
        assert stats['total_mistakes_involved'] == 0
        assert stats['average_contribution_score'] == 0.0

    def test_stats_with_data(self, attribution):
        """Should calculate stats from Neo4j results."""
        neo4j_results = [
            {'role': 'originator', 'score': 0.5},
            {'role': 'propagator', 'score': 0.15},
            {'role': 'detector', 'score': 0.0},
        ]

        stats = attribution.get_agent_stats("agent-1", neo4j_results)

        assert stats['total_mistakes_involved'] == 3
        assert stats['as_originator'] == 1
        assert stats['as_propagator'] == 1
        assert stats['as_detector'] == 1
        assert stats['average_contribution_score'] == pytest.approx(0.2166, abs=0.01)


class TestSerialization:
    """Test JSON serialization."""

    def test_to_json(self, attribution, simple_workflow, mistake_details):
        """Should serialize attribution result to JSON."""
        result = attribution.attribute(
            "mst_007",
            simple_workflow,
            mistake_details
        )

        json_str = attribution.to_json(result)

        assert "mst_007" in json_str
        assert "primary_responsible" in json_str
        assert "contributions" in json_str

        # Should be valid JSON
        import json
        data = json.loads(json_str)
        assert data['mistake_id'] == "mst_007"
        assert len(data['contributions']) == 3
