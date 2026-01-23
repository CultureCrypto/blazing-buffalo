"""
Multi-Agent Attribution Scoring for Blazing Buffalo.

Trace mistakes through multi-agent workflows and calculate contribution scores
for each agent involved.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime
import json


class AgentRole(Enum):
    """Role an agent played in a mistake."""
    ORIGINATOR = "originator"      # Created the mistake
    PROPAGATOR = "propagator"      # Passed mistake along without catching
    AMPLIFIER = "amplifier"        # Made mistake worse
    DETECTOR = "detector"          # Caught the mistake
    RESOLVER = "resolver"          # Fixed the mistake


@dataclass
class AgentContribution:
    """An agent's contribution to a mistake."""
    agent_id: str
    role: AgentRole
    score: float  # 0.0 to 1.0
    action: str  # What the agent did
    timestamp: datetime
    evidence: Dict = field(default_factory=dict)


@dataclass
class AttributionResult:
    """Complete attribution for a mistake."""
    mistake_id: str
    contributions: List[AgentContribution]
    workflow_trace: List[str]  # Ordered list of agent IDs
    primary_responsible: str  # Agent ID most responsible
    confidence: float


class MistakeAttribution:
    """
    Trace mistakes through multi-agent workflows and
    calculate contribution scores.
    """

    # Weight factors for different roles
    ROLE_WEIGHTS = {
        AgentRole.ORIGINATOR: 0.5,
        AgentRole.AMPLIFIER: 0.3,
        AgentRole.PROPAGATOR: 0.15,
        AgentRole.DETECTOR: -0.1,  # Positive contribution
        AgentRole.RESOLVER: -0.2,  # Positive contribution
    }

    def __init__(self):
        self.workflow_history: Dict[str, List[Dict]] = {}

    def trace_agents(self, mistake_id: str,
                     workflow: List[Dict]) -> List[str]:
        """
        Trace which agents were involved in a mistake.

        Args:
            mistake_id: ID of the mistake
            workflow: List of workflow steps, each containing:
                - agent_id: str
                - action: str (tool call, response, etc.)
                - timestamp: datetime
                - output: str

        Returns:
            Ordered list of agent IDs involved
        """
        # Store for later analysis
        self.workflow_history[mistake_id] = workflow

        # Extract unique agents in order
        seen = set()
        agents = []
        for step in workflow:
            agent_id = step.get('agent_id')
            if agent_id and agent_id not in seen:
                seen.add(agent_id)
                agents.append(agent_id)

        return agents

    def calculate_contribution(self, agent_id: str,
                               role: AgentRole,
                               context: Dict) -> float:
        """
        Calculate contribution score for an agent.

        Args:
            agent_id: ID of the agent
            role: Role the agent played
            context: Additional context including:
                - position_in_workflow: int (0 = first)
                - time_with_mistake: float (seconds)
                - actions_taken: List[str]
                - had_opportunity_to_detect: bool

        Returns:
            Contribution score (higher = more responsible)
        """
        base_weight = self.ROLE_WEIGHTS.get(role, 0.1)

        # Adjust based on context
        multiplier = 1.0

        # Position factor - earlier agents more responsible
        position = context.get('position_in_workflow', 0)
        total_agents = context.get('total_agents', 1)
        position_factor = 1.0 - (position / max(total_agents, 1)) * 0.3
        multiplier *= position_factor

        # Time factor - longer time without catching = more responsible
        time_with_mistake = context.get('time_with_mistake', 0)
        if time_with_mistake > 60:  # More than a minute
            multiplier *= 1.2

        # Opportunity factor
        if context.get('had_opportunity_to_detect', False):
            if role == AgentRole.PROPAGATOR:
                multiplier *= 1.3  # Should have caught it

        # Calculate final score
        score = max(0.0, min(1.0, base_weight * multiplier))

        return score

    def attribute(self, mistake_id: str,
                  workflow: List[Dict],
                  mistake_details: Dict) -> AttributionResult:
        """
        Full attribution analysis for a mistake.

        Args:
            mistake_id: ID of the mistake
            workflow: Workflow steps
            mistake_details: Details about the mistake including:
                - detection_method: str
                - detection_agent: str
                - error_type: str
                - error_location: dict (file, line)

        Returns:
            Complete attribution result
        """
        agents = self.trace_agents(mistake_id, workflow)
        contributions = []

        detection_agent = mistake_details.get('detection_agent')

        for i, step in enumerate(workflow):
            agent_id = step.get('agent_id')
            if not agent_id:
                continue

            # Determine role
            role = self._determine_role(
                agent_id=agent_id,
                step=step,
                position=i,
                workflow=workflow,
                mistake_details=mistake_details,
                detection_agent=detection_agent
            )

            # Calculate context
            context = {
                'position_in_workflow': i,
                'total_agents': len(agents),
                'time_with_mistake': self._calculate_time_with_mistake(
                    workflow, i, mistake_details
                ),
                'had_opportunity_to_detect': self._had_opportunity(
                    step, mistake_details
                ),
                'actions_taken': step.get('actions', [])
            }

            # Calculate score
            score = self.calculate_contribution(agent_id, role, context)

            contribution = AgentContribution(
                agent_id=agent_id,
                role=role,
                score=score,
                action=step.get('action', 'unknown'),
                timestamp=step.get('timestamp', datetime.utcnow()),
                evidence={
                    'output_preview': step.get('output', '')[:200],
                    'role_determination': role.value
                }
            )

            contributions.append(contribution)

        # Find primary responsible agent (highest positive score)
        positive_contributions = [
            c for c in contributions
            if c.role not in [AgentRole.DETECTOR, AgentRole.RESOLVER]
        ]

        if positive_contributions:
            primary = max(positive_contributions, key=lambda c: c.score)
        else:
            # Fallback to first agent if no positive contributions
            primary = contributions[0] if contributions else None

        # Calculate overall confidence
        confidence = self._calculate_confidence(contributions, workflow)

        return AttributionResult(
            mistake_id=mistake_id,
            contributions=contributions,
            workflow_trace=agents,
            primary_responsible=primary.agent_id if primary else "unknown",
            confidence=confidence
        )

    def _determine_role(self, agent_id: str, step: Dict,
                        position: int, workflow: List[Dict],
                        mistake_details: Dict,
                        detection_agent: Optional[str]) -> AgentRole:
        """Determine the role an agent played."""

        # Check if detector
        if agent_id == detection_agent:
            return AgentRole.DETECTOR

        # Check if resolver
        if step.get('action') == 'fix' or 'fix' in step.get('output', '').lower():
            return AgentRole.RESOLVER

        # Check if originator (first agent, or agent that created the error)
        error_location = mistake_details.get('error_location', {})
        if position == 0:
            return AgentRole.ORIGINATOR

        # Check if agent touched the error location
        touched_files = step.get('files_modified', [])
        error_file = error_location.get('file')

        if error_file and error_file in touched_files:
            # Check if they made it worse or just passed it along
            output = step.get('output', '')
            if 'error' in output.lower() or 'exception' in output.lower():
                return AgentRole.AMPLIFIER
            return AgentRole.ORIGINATOR

        # Default to propagator
        return AgentRole.PROPAGATOR

    def _calculate_time_with_mistake(self, workflow: List[Dict],
                                     position: int,
                                     mistake_details: Dict) -> float:
        """Calculate how long an agent had the mistake."""
        if position >= len(workflow) - 1:
            return 0.0

        current_time = workflow[position].get('timestamp')
        next_time = workflow[position + 1].get('timestamp')

        if current_time and next_time:
            if isinstance(current_time, str):
                current_time = datetime.fromisoformat(current_time)
            if isinstance(next_time, str):
                next_time = datetime.fromisoformat(next_time)

            return (next_time - current_time).total_seconds()

        return 0.0

    def _had_opportunity(self, step: Dict,
                         mistake_details: Dict) -> bool:
        """Check if agent had opportunity to detect the mistake."""
        # If agent ran tests, type checker, or linter - they had opportunity
        actions = step.get('actions', [])
        detection_tools = ['pytest', 'jest', 'pyright', 'mypy', 'tsc',
                          'ruff', 'eslint', 'test', 'lint', 'check']

        for action in actions:
            if any(tool in str(action).lower() for tool in detection_tools):
                return True

        return False

    def _calculate_confidence(self, contributions: List[AgentContribution],
                              workflow: List[Dict]) -> float:
        """Calculate confidence in the attribution."""
        # More workflow steps = more confident
        step_factor = min(1.0, len(workflow) / 5)

        # Clear role distinctions = more confident
        roles = [c.role for c in contributions]
        has_originator = AgentRole.ORIGINATOR in roles
        has_detector = AgentRole.DETECTOR in roles
        role_clarity = 0.5 + (0.25 if has_originator else 0) + (0.25 if has_detector else 0)

        return (step_factor + role_clarity) / 2

    def emit_to_neo4j(self, result: AttributionResult) -> Dict[str, any]:
        """
        Generate Neo4j Cypher queries for attribution relationships.

        Creates:
        (m:Mistake)-[:CONTRIBUTED_BY {score: 0.4, role: "propagator"}]->(a:Agent)

        Returns:
            Dict with queries and parameters for execution
        """
        queries = []

        for contribution in result.contributions:
            query = {
                'cypher': """
                MATCH (m:Mistake {id: $mistake_id})
                MATCH (a:Agent {id: $agent_id})
                MERGE (m)-[r:CONTRIBUTED_BY]->(a)
                SET r.score = $score,
                    r.role = $role,
                    r.position = $position,
                    r.timestamp = datetime()
                """,
                'params': {
                    'mistake_id': result.mistake_id,
                    'agent_id': contribution.agent_id,
                    'score': contribution.score,
                    'role': contribution.role.value,
                    'position': result.workflow_trace.index(contribution.agent_id)
                }
            }
            queries.append(query)

        return {
            'queries': queries,
            'primary_responsible': result.primary_responsible,
            'confidence': result.confidence
        }

    def get_agent_stats(self, agent_id: str,
                       neo4j_results: Optional[List[Dict]] = None) -> Dict:
        """
        Get attribution statistics for an agent.

        Args:
            agent_id: ID of the agent
            neo4j_results: Optional pre-fetched results from Neo4j query

        Returns:
            Statistics dictionary
        """
        if neo4j_results is None:
            # Return structure for empty case
            return {
                "agent_id": agent_id,
                "total_mistakes_involved": 0,
                "as_originator": 0,
                "as_propagator": 0,
                "as_amplifier": 0,
                "as_detector": 0,
                "as_resolver": 0,
                "average_contribution_score": 0.0,
                "max_contribution_score": 0.0,
                "min_contribution_score": 0.0
            }

        # Calculate stats from results
        role_counts = {
            'originator': 0,
            'propagator': 0,
            'amplifier': 0,
            'detector': 0,
            'resolver': 0
        }

        scores = []

        for result in neo4j_results:
            role = result.get('role', 'propagator')
            score = result.get('score', 0.0)

            role_counts[role] = role_counts.get(role, 0) + 1
            scores.append(score)

        return {
            "agent_id": agent_id,
            "total_mistakes_involved": len(neo4j_results),
            "as_originator": role_counts.get('originator', 0),
            "as_propagator": role_counts.get('propagator', 0),
            "as_amplifier": role_counts.get('amplifier', 0),
            "as_detector": role_counts.get('detector', 0),
            "as_resolver": role_counts.get('resolver', 0),
            "average_contribution_score": sum(scores) / len(scores) if scores else 0.0,
            "max_contribution_score": max(scores) if scores else 0.0,
            "min_contribution_score": min(scores) if scores else 0.0
        }

    def to_json(self, result: AttributionResult) -> str:
        """Serialize attribution result to JSON."""
        return json.dumps({
            'mistake_id': result.mistake_id,
            'primary_responsible': result.primary_responsible,
            'confidence': result.confidence,
            'workflow_trace': result.workflow_trace,
            'contributions': [
                {
                    'agent_id': c.agent_id,
                    'role': c.role.value,
                    'score': c.score,
                    'action': c.action,
                    'timestamp': c.timestamp.isoformat(),
                    'evidence': c.evidence
                }
                for c in result.contributions
            ]
        }, indent=2)
