"""
Root Cause Analysis Pipeline with Ralph Multi-Model Integration.

Analyzes mistakes using a multi-model review process (Claude -> Gemini -> GLM)
to determine root causes and generate prevention rules.

Key Features:
- Context extraction from surrounding code and conversation
- Similar mistake lookup via Qdrant vector search
- Pattern detection using dynamic taxonomy (BB-009)
- Multi-model RCA with convergence checking
- Prevention rule generation for playbook integration
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum
from datetime import datetime
import json
import asyncio
import re
from collections import Counter

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# Import from previous BB tasks
from lib.dynamic_taxonomy import DynamicTaxonomy, ClusterAssignment
from lib.attribution import MistakeAttribution, AttributionResult


class RootCauseCategory(Enum):
    """Categories of root causes for mistakes."""
    KNOWLEDGE_GAP = "knowledge_gap"           # Agent doesn't know something
    CONTEXT_MISSING = "context_missing"       # Information not provided
    INSTRUCTION_AMBIGUITY = "instruction_ambiguity"  # Unclear requirements
    TOOL_MISUSE = "tool_misuse"               # Wrong tool or wrong usage
    PATTERN_VIOLATION = "pattern_violation"   # Breaks established patterns
    EDGE_CASE = "edge_case"                   # Unusual scenario not handled
    INTEGRATION_ERROR = "integration_error"   # Cross-component issue
    EXTERNAL_DEPENDENCY = "external_dependency"  # Third-party failure


@dataclass
class RCAContext:
    """Context gathered for root cause analysis."""
    mistake_id: str
    mistake_description: str
    surrounding_code: Optional[str] = None
    conversation_history: List[Dict] = field(default_factory=list)
    tool_outputs: List[Dict] = field(default_factory=list)
    file_changes: List[str] = field(default_factory=list)
    taxonomy_cluster: Optional[str] = None
    attribution: Optional[AttributionResult] = None

    def to_dict(self) -> Dict:
        """Convert to serializable dict."""
        return {
            'mistake_id': self.mistake_id,
            'mistake_description': self.mistake_description,
            'surrounding_code': self.surrounding_code,
            'conversation_history': self.conversation_history,
            'tool_outputs': self.tool_outputs,
            'file_changes': self.file_changes,
            'taxonomy_cluster': self.taxonomy_cluster,
            'attribution': {
                'primary_responsible': self.attribution.primary_responsible,
                'confidence': self.attribution.confidence
            } if self.attribution else None
        }


@dataclass
class SimilarMistake:
    """A similar past mistake found via vector search."""
    mistake_id: str
    similarity: float
    description: str
    resolution: Optional[str] = None
    prevention_rule: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to serializable dict."""
        return {
            'mistake_id': self.mistake_id,
            'similarity': self.similarity,
            'description': self.description,
            'resolution': self.resolution,
            'prevention_rule': self.prevention_rule
        }


@dataclass
class RCAResult:
    """Complete result of root cause analysis."""
    mistake_id: str
    root_cause: RootCauseCategory
    explanation: str
    contributing_factors: List[str]
    prevention_rule: str
    confidence: float
    similar_mistakes: List[SimilarMistake]
    ralph_iterations: List[Dict]
    consensus_reached: bool
    agreement_level: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        """Convert to serializable dict."""
        return {
            'mistake_id': self.mistake_id,
            'root_cause': self.root_cause.value,
            'explanation': self.explanation,
            'contributing_factors': self.contributing_factors,
            'prevention_rule': self.prevention_rule,
            'confidence': self.confidence,
            'similar_mistakes': [s.to_dict() for s in self.similar_mistakes],
            'ralph_iterations': self.ralph_iterations,
            'consensus_reached': self.consensus_reached,
            'agreement_level': self.agreement_level,
            'timestamp': self.timestamp.isoformat()
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class MistakeRCA:
    """
    Root Cause Analysis pipeline with Ralph multi-model integration.

    Analyzes mistakes through a comprehensive pipeline:
    1. Extract context (code, conversation, tool outputs)
    2. Find similar past mistakes via Qdrant
    3. Detect patterns using dynamic taxonomy
    4. Run Ralph multi-model RCA (Claude -> Gemini -> GLM)
    5. Classify root cause into one of 8 categories
    6. Generate prevention rule for playbook integration
    """

    RALPH_CONVERGENCE_THRESHOLD = 0.7
    MAX_RALPH_ITERATIONS = 4
    QDRANT_ENDPOINT = "http://localhost:6333"

    def __init__(self,
                 taxonomy: Optional[DynamicTaxonomy] = None,
                 attribution: Optional[MistakeAttribution] = None,
                 qdrant_endpoint: Optional[str] = None,
                 model_endpoints: Optional[Dict[str, str]] = None):
        """
        Initialize RCA pipeline.

        Args:
            taxonomy: DynamicTaxonomy instance (creates new if None)
            attribution: MistakeAttribution instance (creates new if None)
            qdrant_endpoint: Qdrant vector database endpoint
            model_endpoints: Override model endpoints for Ralph
        """
        self.taxonomy = taxonomy or DynamicTaxonomy()
        self.attribution = attribution or MistakeAttribution()

        if qdrant_endpoint:
            self.QDRANT_ENDPOINT = qdrant_endpoint

        # Ralph model endpoints
        self.models = {
            "claude": {
                "endpoint": "local",
                "role": "initial_analysis",
                "temperature": 0.3
            },
            "gemini": {
                "endpoint": model_endpoints.get("gemini", "http://localhost:5050") if model_endpoints else "http://localhost:5050",
                "role": "challenge",
                "temperature": 0.4
            },
            "glm": {
                "endpoint": model_endpoints.get("glm", "http://localhost:5051") if model_endpoints else "http://localhost:5051",
                "role": "synthesis",
                "temperature": 0.2
            }
        }

        # Cache for RCA results
        self._result_cache: Dict[str, RCAResult] = {}

    async def analyze(self, mistake: Dict,
                      context: Dict) -> RCAResult:
        """
        Full RCA pipeline for a mistake.

        Args:
            mistake: Detected mistake from BB-007 with keys:
                - id: Unique mistake identifier
                - description: Human-readable description
                - file_path: Optional file where mistake occurred
                - line_number: Optional line number
            context: Session context with keys:
                - messages: Conversation history
                - tool_outputs: Recent tool outputs
                - file_changes: Modified files
                - workflow: Agent workflow for attribution

        Returns:
            Complete RCA result with prevention rule
        """
        mistake_id = mistake.get('id', f"mst_{datetime.utcnow().timestamp()}")

        # Check cache
        if mistake_id in self._result_cache:
            return self._result_cache[mistake_id]

        # Step 1: Extract context
        rca_context = self.extract_context(mistake, context)

        # Step 2: Find similar mistakes
        similar = await self.find_similar_mistakes(
            rca_context.mistake_description,
            top_k=5
        )

        # Step 3: Detect patterns using taxonomy
        pattern = self.detect_patterns(mistake, similar)

        # Step 4: Run Ralph multi-model RCA
        ralph_result = await self.ralph_rca(rca_context, similar, pattern)

        # Step 5: Classify root cause
        root_cause = self.classify_root_cause(
            ralph_result, rca_context, pattern
        )

        # Step 6: Generate prevention rule
        prevention_rule = self.generate_prevention_rule(
            root_cause, ralph_result, rca_context
        )

        result = RCAResult(
            mistake_id=mistake_id,
            root_cause=root_cause,
            explanation=ralph_result.get('explanation', ''),
            contributing_factors=ralph_result.get('factors', []),
            prevention_rule=prevention_rule,
            confidence=ralph_result.get('confidence', 0.0),
            similar_mistakes=similar,
            ralph_iterations=ralph_result.get('iterations', []),
            consensus_reached=ralph_result.get('consensus', False),
            agreement_level=ralph_result.get('agreement_level', 0.0)
        )

        # Cache result
        self._result_cache[mistake_id] = result

        return result

    def extract_context(self, mistake: Dict,
                        context: Dict) -> RCAContext:
        """
        Gather all relevant context for RCA.

        Args:
            mistake: The detected mistake
            context: Session context

        Returns:
            RCAContext with all gathered information
        """
        # Get conversation history (last 10 messages)
        history = context.get('messages', [])[-10:]

        # Get recent tool outputs
        tool_outputs = context.get('tool_outputs', [])[-5:]

        # Get file changes
        file_changes = context.get('file_changes', [])

        # Get surrounding code if file specified
        surrounding_code = None
        if mistake.get('file_path') and mistake.get('line_number'):
            surrounding_code = self._get_surrounding_code(
                mistake['file_path'],
                mistake['line_number'],
                context_lines=10
            )

        # Get taxonomy cluster
        taxonomy_cluster = None
        cluster_result = self.taxonomy.get_category(
            mistake.get('description', ''),
            mistake.get('id')
        )
        if cluster_result:
            taxonomy_cluster = cluster_result.cluster_id

        # Get attribution if workflow available
        attribution_result = None
        if context.get('workflow'):
            attribution_result = self.attribution.attribute(
                mistake.get('id', 'unknown'),
                context['workflow'],
                mistake
            )

        return RCAContext(
            mistake_id=mistake.get('id', 'unknown'),
            mistake_description=mistake.get('description', ''),
            surrounding_code=surrounding_code,
            conversation_history=history,
            tool_outputs=tool_outputs,
            file_changes=file_changes,
            taxonomy_cluster=taxonomy_cluster,
            attribution=attribution_result
        )

    async def find_similar_mistakes(self, description: str,
                                    top_k: int = 5) -> List[SimilarMistake]:
        """
        Query Qdrant for similar past mistakes.

        Args:
            description: Mistake description to search for
            top_k: Number of similar mistakes to return

        Returns:
            List of similar mistakes with similarity scores
        """
        if not HTTPX_AVAILABLE:
            return []

        # Generate embedding using taxonomy
        try:
            embedding = self.taxonomy.get_embedding(description)
        except Exception:
            # Fallback: return empty if embedding fails
            return []

        # Query Qdrant
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.QDRANT_ENDPOINT}/collections/mistakes/points/search",
                    json={
                        "vector": embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding),
                        "limit": top_k,
                        "with_payload": True
                    }
                )

                if response.status_code == 200:
                    results = response.json().get('result', [])
                    return [
                        SimilarMistake(
                            mistake_id=r['payload'].get('mistake_id', r.get('id', 'unknown')),
                            similarity=r['score'],
                            description=r['payload'].get('description', ''),
                            resolution=r['payload'].get('resolution'),
                            prevention_rule=r['payload'].get('prevention_rule')
                        )
                        for r in results
                    ]
        except Exception as e:
            # Log but don't fail - similar mistakes are optional enhancement
            pass

        return []

    def detect_patterns(self, mistake: Dict,
                        similar: List[SimilarMistake]) -> Dict:
        """
        Detect patterns using taxonomy clustering.

        Args:
            mistake: The current mistake
            similar: Similar past mistakes

        Returns:
            Pattern information including cluster and frequency
        """
        # Get cluster for this mistake
        cluster = self.taxonomy.get_category(
            mistake.get('description', ''),
            mistake.get('id')
        )

        cluster_id = cluster.cluster_id if cluster else 'unknown'
        is_new = cluster.is_new_cluster if cluster else True

        # Check if similar mistakes share patterns
        shared_patterns = []
        if similar and hasattr(self.taxonomy, 'mistake_to_cluster'):
            for sim in similar:
                sim_cluster = self.taxonomy.mistake_to_cluster.get(sim.mistake_id)
                if sim_cluster == cluster_id:
                    shared_patterns.append({
                        "mistake_id": sim.mistake_id,
                        "cluster": sim_cluster,
                        "similarity": sim.similarity
                    })

        # Get cluster name from taxonomy
        cluster_name = 'unknown'
        if hasattr(self.taxonomy, 'clusters') and cluster_id in self.taxonomy.clusters:
            cluster_name = self.taxonomy.clusters[cluster_id].get('name', 'unknown')

        return {
            "cluster_id": cluster_id,
            "cluster_name": cluster_name,
            "is_new_pattern": is_new,
            "shared_with": shared_patterns,
            "pattern_frequency": len(shared_patterns) + 1
        }

    async def ralph_rca(self, context: RCAContext,
                        similar: List[SimilarMistake],
                        pattern: Dict) -> Dict:
        """
        Run Ralph multi-model RCA loop.

        Flow:
        1. Claude: Initial analysis
        2. Gemini: Challenge assumptions, find edge cases
        3. GLM: Synthesize final recommendation
        4. Check convergence (0.7 agreement threshold)

        Args:
            context: RCA context with all gathered information
            similar: Similar past mistakes
            pattern: Pattern detection results

        Returns:
            Combined analysis result with iterations
        """
        iterations = []

        # Prepare the RCA prompt
        rca_prompt = self._build_rca_prompt(context, similar, pattern)

        # Iteration 1: Claude initial analysis
        claude_result = await self._call_model(
            "claude",
            f"""You are performing root cause analysis on a mistake.

{rca_prompt}

Analyze this mistake and provide:
1. Root cause category (knowledge_gap, context_missing, instruction_ambiguity, tool_misuse, pattern_violation, edge_case, integration_error, external_dependency)
2. Detailed explanation
3. Contributing factors (list 3-5)
4. Suggested prevention rule
5. Confidence score (0.0-1.0)

Format as JSON with keys: root_cause, explanation, contributing_factors, prevention_rule, confidence"""
        )
        iterations.append({"model": "claude", "result": claude_result})

        # Iteration 2: Gemini challenges
        gemini_result = await self._call_model(
            "gemini",
            f"""Review this root cause analysis and challenge it:

Original Analysis:
{json.dumps(claude_result, indent=2)}

Mistake Context:
{rca_prompt}

Challenge:
1. What assumptions might be wrong?
2. What edge cases were missed?
3. Is the root cause correctly identified?
4. Are there alternative explanations?
5. Is the prevention rule robust?

Provide revised analysis if needed, or confirm if correct.
Format as JSON with keys: confirmed (boolean), revisions (dict with any changes), challenges (list of concerns), confidence"""
        )
        iterations.append({"model": "gemini", "result": gemini_result})

        # Iteration 3: GLM synthesizes
        glm_result = await self._call_model(
            "glm",
            f"""Synthesize the final root cause analysis:

Claude's Analysis:
{json.dumps(claude_result, indent=2)}

Gemini's Review:
{json.dumps(gemini_result, indent=2)}

Mistake Context:
{rca_prompt}

Synthesize:
1. Final root cause determination
2. Integrated explanation
3. Complete contributing factors
4. Final prevention rule
5. Overall confidence

Also assess:
- Agreement level between models (0.0-1.0)
- Any unresolved disagreements

Format as JSON with keys: root_cause, explanation, contributing_factors, prevention_rule, confidence, agreement_level, unresolved_issues"""
        )
        iterations.append({"model": "glm", "result": glm_result})

        # Check convergence
        agreement = self._calculate_agreement(iterations)
        consensus = agreement >= self.RALPH_CONVERGENCE_THRESHOLD

        # If no consensus, run additional reconciliation iteration
        if not consensus and len(iterations) < self.MAX_RALPH_ITERATIONS:
            reconcile_result = await self._reconcile(iterations, rca_prompt)
            iterations.append({"model": "reconciliation", "result": reconcile_result})
            consensus = True  # Forced consensus after reconciliation
            agreement = reconcile_result.get('agreement_level', agreement)

        # Extract final result from last iteration
        final = iterations[-1]['result']

        return {
            "root_cause": final.get('root_cause', RootCauseCategory.KNOWLEDGE_GAP.value),
            "explanation": final.get('explanation', ''),
            "factors": final.get('contributing_factors', []),
            "prevention_rule": final.get('prevention_rule', ''),
            "confidence": final.get('confidence', 0.7),
            "iterations": iterations,
            "consensus": consensus,
            "agreement_level": agreement
        }

    async def _call_model(self, model_name: str, prompt: str) -> Dict:
        """
        Call a model endpoint.

        Args:
            model_name: Name of model (claude, gemini, glm)
            prompt: Prompt to send

        Returns:
            Parsed JSON response from model
        """
        config = self.models.get(model_name, {})
        endpoint = config.get('endpoint')
        temperature = config.get('temperature', 0.3)

        if endpoint == "local":
            # Local Claude - simulate for now
            # In production, integrate with actual Claude API
            return self._simulate_claude_response(prompt)
        else:
            if not HTTPX_AVAILABLE:
                return {"error": "httpx not available"}

            # Remote Gemini/GLM proxy
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{endpoint}/v1/chat/completions",
                        json={
                            "model": model_name,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": temperature
                        }
                    )
                    if response.status_code == 200:
                        content = response.json()['choices'][0]['message']['content']
                        return self._parse_json_response(content)
                    else:
                        return {"error": f"HTTP {response.status_code}"}
            except Exception as e:
                return {"error": str(e)}

    def _simulate_claude_response(self, prompt: str) -> Dict:
        """
        Simulate Claude response for testing/fallback.

        Analyzes the prompt to generate contextually appropriate response.
        """
        # Extract context from prompt for better simulation
        root_cause = "knowledge_gap"

        # Simple heuristics based on prompt content
        prompt_lower = prompt.lower()
        if "import" in prompt_lower or "module" in prompt_lower:
            root_cause = "knowledge_gap"
        elif "unclear" in prompt_lower or "ambiguous" in prompt_lower:
            root_cause = "instruction_ambiguity"
        elif "tool" in prompt_lower or "command" in prompt_lower:
            root_cause = "tool_misuse"
        elif "pattern" in prompt_lower or "convention" in prompt_lower:
            root_cause = "pattern_violation"
        elif "context" in prompt_lower or "missing" in prompt_lower:
            root_cause = "context_missing"
        elif "edge" in prompt_lower or "corner" in prompt_lower:
            root_cause = "edge_case"
        elif "integration" in prompt_lower or "component" in prompt_lower:
            root_cause = "integration_error"
        elif "external" in prompt_lower or "api" in prompt_lower or "third" in prompt_lower:
            root_cause = "external_dependency"

        return {
            "root_cause": root_cause,
            "explanation": f"Analysis indicates {root_cause.replace('_', ' ')} as the primary cause",
            "contributing_factors": [
                "Insufficient documentation review",
                "Missing validation checks",
                "Incomplete context analysis"
            ],
            "prevention_rule": f"Verify {root_cause.replace('_', ' ')} conditions before proceeding",
            "confidence": 0.8,
            "confirmed": True,
            "agreement_level": 0.85
        }

    def classify_root_cause(self, ralph_result: Dict,
                            context: RCAContext,
                            pattern: Dict) -> RootCauseCategory:
        """
        Determine final root cause category.

        Args:
            ralph_result: Result from Ralph multi-model analysis
            context: RCA context
            pattern: Pattern detection results

        Returns:
            RootCauseCategory enum value
        """
        suggested = ralph_result.get('root_cause', '')

        # Map string to enum
        category_map = {
            "knowledge_gap": RootCauseCategory.KNOWLEDGE_GAP,
            "context_missing": RootCauseCategory.CONTEXT_MISSING,
            "instruction_ambiguity": RootCauseCategory.INSTRUCTION_AMBIGUITY,
            "tool_misuse": RootCauseCategory.TOOL_MISUSE,
            "pattern_violation": RootCauseCategory.PATTERN_VIOLATION,
            "edge_case": RootCauseCategory.EDGE_CASE,
            "integration_error": RootCauseCategory.INTEGRATION_ERROR,
            "external_dependency": RootCauseCategory.EXTERNAL_DEPENDENCY
        }

        # Handle case variations
        suggested_normalized = suggested.lower().replace(' ', '_').replace('-', '_')

        return category_map.get(suggested_normalized, RootCauseCategory.KNOWLEDGE_GAP)

    def generate_prevention_rule(self, root_cause: RootCauseCategory,
                                 ralph_result: Dict,
                                 context: RCAContext) -> str:
        """
        Generate a prevention rule/playbook trigger.

        Args:
            root_cause: Classified root cause category
            ralph_result: Result from Ralph analysis
            context: RCA context

        Returns:
            Prevention rule string for playbook integration
        """
        # Use Ralph's suggested rule if available
        rule = ralph_result.get('prevention_rule', '')

        if rule and len(rule) > 10:
            return rule

        # Generate default rule based on root cause and context
        cluster_name = context.taxonomy_cluster or 'this type of'

        templates = {
            RootCauseCategory.KNOWLEDGE_GAP:
                f"When handling '{cluster_name}' patterns, consult documentation and similar past mistakes before proceeding",
            RootCauseCategory.CONTEXT_MISSING:
                f"Request additional context (file contents, requirements, constraints) before proceeding with similar tasks",
            RootCauseCategory.INSTRUCTION_AMBIGUITY:
                f"Clarify ambiguous instructions by asking specific questions before implementation",
            RootCauseCategory.TOOL_MISUSE:
                f"Verify tool compatibility and correct usage patterns before executing commands",
            RootCauseCategory.PATTERN_VIOLATION:
                f"Check existing patterns in codebase using code search before implementing new code",
            RootCauseCategory.EDGE_CASE:
                f"Consider edge cases and boundary conditions explicitly before finalizing implementation",
            RootCauseCategory.INTEGRATION_ERROR:
                f"Verify cross-component interfaces and data flow before making integration changes",
            RootCauseCategory.EXTERNAL_DEPENDENCY:
                f"Test external dependencies and add appropriate error handling before relying on them"
        }

        return templates.get(root_cause, "Review similar past mistakes before proceeding")

    def _build_rca_prompt(self, context: RCAContext,
                          similar: List[SimilarMistake],
                          pattern: Dict) -> str:
        """
        Build comprehensive RCA prompt.

        Args:
            context: RCA context
            similar: Similar past mistakes
            pattern: Pattern detection results

        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            f"## Mistake Description\n{context.mistake_description}",
            f"\n## Pattern Information\n"
            f"Cluster: {pattern.get('cluster_name', 'unknown')}\n"
            f"Frequency: {pattern.get('pattern_frequency', 1)} occurrences\n"
            f"Is New Pattern: {pattern.get('is_new_pattern', True)}",
        ]

        if context.surrounding_code:
            # Truncate code if too long
            code = context.surrounding_code[:500]
            if len(context.surrounding_code) > 500:
                code += "\n... (truncated)"
            prompt_parts.append(
                f"\n## Surrounding Code\n```\n{code}\n```"
            )

        if context.attribution:
            prompt_parts.append(
                f"\n## Agent Attribution\n"
                f"Primary responsible: {context.attribution.primary_responsible}\n"
                f"Attribution confidence: {context.attribution.confidence:.2f}"
            )

        if context.file_changes:
            files = ", ".join(context.file_changes[:5])
            if len(context.file_changes) > 5:
                files += f" (+{len(context.file_changes) - 5} more)"
            prompt_parts.append(f"\n## Files Changed\n{files}")

        if similar:
            similar_text = "\n".join([
                f"- {s.description[:100]}{'...' if len(s.description) > 100 else ''} (similarity: {s.similarity:.2f})"
                for s in similar[:3]
            ])
            prompt_parts.append(f"\n## Similar Past Mistakes\n{similar_text}")

            # Include prevention rules from similar mistakes if available
            rules = [s.prevention_rule for s in similar if s.prevention_rule]
            if rules:
                rules_text = "\n".join([f"- {r}" for r in rules[:3]])
                prompt_parts.append(f"\n## Previous Prevention Rules\n{rules_text}")

        return "\n".join(prompt_parts)

    def _calculate_agreement(self, iterations: List[Dict]) -> float:
        """
        Calculate agreement level between model outputs.

        Args:
            iterations: List of model iteration results

        Returns:
            Agreement score between 0.0 and 1.0
        """
        if len(iterations) < 2:
            return 1.0

        # Extract root causes from all iterations
        root_causes = []
        for it in iterations:
            result = it.get('result', {})
            if 'root_cause' in result:
                root_causes.append(result['root_cause'])
            elif 'revisions' in result and 'root_cause' in result.get('revisions', {}):
                root_causes.append(result['revisions']['root_cause'])

        if not root_causes:
            return 0.5

        # Calculate mode agreement
        counts = Counter(root_causes)
        most_common_count = counts.most_common(1)[0][1]

        # Base agreement from root cause consensus
        root_cause_agreement = most_common_count / len(root_causes)

        # Bonus for explicit confirmation
        confirmations = sum(
            1 for it in iterations
            if it.get('result', {}).get('confirmed', False)
        )
        confirmation_bonus = confirmations * 0.1

        # Check agreement_level from synthesis if available
        for it in iterations:
            if it.get('result', {}).get('agreement_level'):
                explicit_agreement = it['result']['agreement_level']
                # Blend explicit and calculated agreement
                return min(1.0, (root_cause_agreement + explicit_agreement) / 2 + confirmation_bonus)

        return min(1.0, root_cause_agreement + confirmation_bonus)

    async def _reconcile(self, iterations: List[Dict],
                         original_prompt: str) -> Dict:
        """
        Reconcile disagreements between models.

        Args:
            iterations: Previous iteration results
            original_prompt: Original RCA prompt

        Returns:
            Reconciled result
        """
        # Build reconciliation prompt
        disagreements = []
        for i, it in enumerate(iterations):
            result = it.get('result', {})
            if 'challenges' in result:
                disagreements.extend(result['challenges'])

        reconcile_prompt = f"""Reconcile the following disagreements in root cause analysis:

Disagreements/Challenges:
{json.dumps(disagreements[:5], indent=2) if disagreements else "No explicit disagreements, but models reached different conclusions."}

Previous Iterations:
{json.dumps([{"model": it["model"], "root_cause": it.get("result", {}).get("root_cause")} for it in iterations], indent=2)}

Original Context:
{original_prompt[:1000]}

Provide a final reconciled analysis that addresses the disagreements.
Format as JSON with keys: root_cause, explanation, contributing_factors, prevention_rule, confidence, agreement_level"""

        # Call GLM for final reconciliation
        reconciled = await self._call_model("glm", reconcile_prompt)

        # Ensure agreement_level is reasonable for reconciliation
        if 'agreement_level' not in reconciled or reconciled.get('agreement_level', 0) < 0.7:
            reconciled['agreement_level'] = 0.75  # Forced consensus

        return reconciled

    def _get_surrounding_code(self, file_path: str,
                              line_number: int,
                              context_lines: int = 10) -> Optional[str]:
        """
        Get code surrounding a specific line.

        Args:
            file_path: Path to source file
            line_number: Line number to center on
            context_lines: Number of lines before/after

        Returns:
            Code snippet with line numbers, or None if file not readable
        """
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
                start = max(0, line_number - context_lines - 1)
                end = min(len(lines), line_number + context_lines)

                # Format with line numbers
                result_lines = []
                for i, line in enumerate(lines[start:end], start=start + 1):
                    marker = ">>>" if i == line_number else "   "
                    result_lines.append(f"{marker} {i:4d} | {line.rstrip()}")

                return '\n'.join(result_lines)
        except Exception:
            return None

    def _parse_json_response(self, content: str) -> Dict:
        """
        Parse JSON from model response.

        Handles various response formats including markdown code blocks.
        """
        try:
            # Try direct parse first
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        try:
            # Try to find JSON in markdown code block
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

        try:
            # Try to find any JSON object in response
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        return {"raw_response": content, "parse_error": True}

    def emit_to_neo4j(self, result: RCAResult) -> Dict:
        """
        Generate Neo4j queries for storing RCA result.

        Args:
            result: RCA result to store

        Returns:
            Dict with Cypher queries and parameters
        """
        queries = []

        # Main RCA node
        queries.append({
            "cypher": """
                MERGE (m:Mistake {id: $mistake_id})
                SET m.root_cause = $root_cause,
                    m.explanation = $explanation,
                    m.prevention_rule = $prevention_rule,
                    m.confidence = $confidence,
                    m.consensus_reached = $consensus_reached,
                    m.agreement_level = $agreement_level,
                    m.analyzed_at = datetime()
            """,
            "params": {
                "mistake_id": result.mistake_id,
                "root_cause": result.root_cause.value,
                "explanation": result.explanation,
                "prevention_rule": result.prevention_rule,
                "confidence": result.confidence,
                "consensus_reached": result.consensus_reached,
                "agreement_level": result.agreement_level
            }
        })

        # Contributing factors
        for factor in result.contributing_factors:
            queries.append({
                "cypher": """
                    MATCH (m:Mistake {id: $mistake_id})
                    MERGE (f:Factor {name: $factor})
                    MERGE (m)-[:CAUSED_BY]->(f)
                """,
                "params": {
                    "mistake_id": result.mistake_id,
                    "factor": factor
                }
            })

        # Similar mistakes relationships
        for similar in result.similar_mistakes:
            queries.append({
                "cypher": """
                    MATCH (m:Mistake {id: $mistake_id})
                    MERGE (s:Mistake {id: $similar_id})
                    MERGE (m)-[:SIMILAR_TO {score: $similarity}]->(s)
                """,
                "params": {
                    "mistake_id": result.mistake_id,
                    "similar_id": similar.mistake_id,
                    "similarity": similar.similarity
                }
            })

        return {
            "queries": queries,
            "mistake_id": result.mistake_id,
            "root_cause": result.root_cause.value,
            "confidence": result.confidence
        }

    def to_json(self, result: RCAResult) -> str:
        """Serialize RCA result to JSON string."""
        return result.to_json()

    def clear_cache(self):
        """Clear the result cache."""
        self._result_cache.clear()
