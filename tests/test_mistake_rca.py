"""
Tests for Root Cause Analysis pipeline with Ralph multi-model integration.
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from lib.mistake_rca import (
    MistakeRCA,
    RootCauseCategory,
    RCAContext,
    SimilarMistake,
    RCAResult
)
from lib.attribution import AttributionResult, AgentContribution, AgentRole


@pytest.fixture
def rca():
    """Create MistakeRCA instance with mocked dependencies."""
    with patch('lib.mistake_rca.DynamicTaxonomy') as MockTaxonomy:
        with patch('lib.mistake_rca.MistakeAttribution') as MockAttribution:
            # Setup taxonomy mock
            mock_taxonomy = MockTaxonomy.return_value
            mock_cluster = Mock()
            mock_cluster.cluster_id = "cluster_001"
            mock_cluster.is_new_cluster = False
            mock_taxonomy.get_category.return_value = mock_cluster
            mock_taxonomy.get_embedding.return_value = [0.1] * 384
            mock_taxonomy.mistake_to_cluster = {}
            mock_taxonomy.clusters = {"cluster_001": {"name": "import_errors"}}

            # Setup attribution mock
            mock_attribution = MockAttribution.return_value
            mock_result = Mock(spec=AttributionResult)
            mock_result.primary_responsible = "backend-dev"
            mock_result.confidence = 0.85
            mock_attribution.attribute.return_value = mock_result

            instance = MistakeRCA(
                taxonomy=mock_taxonomy,
                attribution=mock_attribution
            )
            yield instance


@pytest.fixture
def basic_mistake():
    """Basic mistake for testing."""
    return {
        "id": "mst_test_001",
        "description": "Used wrong import path for the utils module",
        "file_path": "/app/src/main.py",
        "line_number": 15
    }


@pytest.fixture
def basic_context():
    """Basic session context for testing."""
    return {
        "messages": [
            {"role": "user", "content": "Fix the import error"},
            {"role": "assistant", "content": "I'll update the import"}
        ],
        "tool_outputs": [
            {"tool": "write", "result": "success"},
            {"tool": "bash", "result": "ImportError: No module named 'utils'"}
        ],
        "file_changes": ["main.py", "utils.py"],
        "workflow": [
            {"agent_id": "planner", "action": "plan", "timestamp": datetime.utcnow()},
            {"agent_id": "backend-dev", "action": "implement", "timestamp": datetime.utcnow()}
        ]
    }


@pytest.fixture
def similar_mistakes():
    """Similar mistakes for testing."""
    return [
        SimilarMistake(
            mistake_id="mst_past_001",
            similarity=0.92,
            description="Wrong import in handler module",
            resolution="Updated import path",
            prevention_rule="Verify import paths before writing"
        ),
        SimilarMistake(
            mistake_id="mst_past_002",
            similarity=0.85,
            description="Missing module import",
            resolution="Added missing import",
            prevention_rule=None
        )
    ]


class TestRootCauseCategory:
    """Test RootCauseCategory enum."""

    def test_all_categories_defined(self):
        """Should have all 8 root cause categories."""
        categories = list(RootCauseCategory)
        assert len(categories) == 8

    def test_category_values(self):
        """Should have correct string values."""
        assert RootCauseCategory.KNOWLEDGE_GAP.value == "knowledge_gap"
        assert RootCauseCategory.CONTEXT_MISSING.value == "context_missing"
        assert RootCauseCategory.TOOL_MISUSE.value == "tool_misuse"
        assert RootCauseCategory.PATTERN_VIOLATION.value == "pattern_violation"


class TestRCAContext:
    """Test RCAContext dataclass."""

    def test_context_creation(self):
        """Should create context with all fields."""
        ctx = RCAContext(
            mistake_id="mst_001",
            mistake_description="Test mistake",
            surrounding_code="def test(): pass",
            conversation_history=[{"role": "user", "content": "hi"}],
            tool_outputs=[{"tool": "bash"}],
            file_changes=["file.py"]
        )

        assert ctx.mistake_id == "mst_001"
        assert ctx.mistake_description == "Test mistake"
        assert ctx.surrounding_code is not None

    def test_context_to_dict(self):
        """Should serialize to dict correctly."""
        ctx = RCAContext(
            mistake_id="mst_001",
            mistake_description="Test"
        )

        data = ctx.to_dict()
        assert data['mistake_id'] == "mst_001"
        assert data['mistake_description'] == "Test"
        assert data['surrounding_code'] is None

    def test_context_with_attribution(self):
        """Should include attribution in dict if present."""
        mock_attr = Mock(spec=AttributionResult)
        mock_attr.primary_responsible = "agent-1"
        mock_attr.confidence = 0.9

        ctx = RCAContext(
            mistake_id="mst_001",
            mistake_description="Test",
            attribution=mock_attr
        )

        data = ctx.to_dict()
        assert data['attribution']['primary_responsible'] == "agent-1"
        assert data['attribution']['confidence'] == 0.9


class TestSimilarMistake:
    """Test SimilarMistake dataclass."""

    def test_similar_creation(self):
        """Should create similar mistake."""
        sm = SimilarMistake(
            mistake_id="mst_past",
            similarity=0.85,
            description="Past mistake",
            resolution="Fixed it",
            prevention_rule="Check first"
        )

        assert sm.similarity == 0.85
        assert sm.prevention_rule == "Check first"

    def test_similar_to_dict(self):
        """Should serialize correctly."""
        sm = SimilarMistake(
            mistake_id="mst_past",
            similarity=0.85,
            description="Past mistake"
        )

        data = sm.to_dict()
        assert data['mistake_id'] == "mst_past"
        assert data['similarity'] == 0.85
        assert data['resolution'] is None


class TestRCAResult:
    """Test RCAResult dataclass."""

    def test_result_creation(self):
        """Should create RCA result."""
        result = RCAResult(
            mistake_id="mst_001",
            root_cause=RootCauseCategory.KNOWLEDGE_GAP,
            explanation="Agent lacked module knowledge",
            contributing_factors=["Missing docs", "No examples"],
            prevention_rule="Check docs first",
            confidence=0.85,
            similar_mistakes=[],
            ralph_iterations=[],
            consensus_reached=True
        )

        assert result.root_cause == RootCauseCategory.KNOWLEDGE_GAP
        assert result.confidence == 0.85
        assert result.consensus_reached is True

    def test_result_to_dict(self):
        """Should serialize to dict."""
        result = RCAResult(
            mistake_id="mst_001",
            root_cause=RootCauseCategory.TOOL_MISUSE,
            explanation="Wrong tool used",
            contributing_factors=["factor1"],
            prevention_rule="Use correct tool",
            confidence=0.8,
            similar_mistakes=[],
            ralph_iterations=[{"model": "claude", "result": {}}],
            consensus_reached=True,
            agreement_level=0.9
        )

        data = result.to_dict()
        assert data['root_cause'] == "tool_misuse"
        assert data['agreement_level'] == 0.9
        assert 'timestamp' in data

    def test_result_to_json(self):
        """Should serialize to JSON string."""
        result = RCAResult(
            mistake_id="mst_001",
            root_cause=RootCauseCategory.EDGE_CASE,
            explanation="Edge case",
            contributing_factors=[],
            prevention_rule="Handle edges",
            confidence=0.7,
            similar_mistakes=[],
            ralph_iterations=[],
            consensus_reached=False
        )

        json_str = result.to_json()
        data = json.loads(json_str)
        assert data['root_cause'] == "edge_case"


class TestExtractContext:
    """Test context extraction."""

    def test_basic_extraction(self, rca, basic_mistake, basic_context):
        """Should extract context from mistake and session."""
        ctx = rca.extract_context(basic_mistake, basic_context)

        assert ctx.mistake_id == "mst_test_001"
        assert "wrong import" in ctx.mistake_description.lower()
        assert len(ctx.conversation_history) == 2
        assert len(ctx.tool_outputs) == 2
        assert "main.py" in ctx.file_changes

    def test_extraction_limits_history(self, rca, basic_mistake):
        """Should limit conversation history to 10 messages."""
        context = {
            "messages": [{"content": f"msg_{i}"} for i in range(20)],
            "tool_outputs": [],
            "file_changes": []
        }

        ctx = rca.extract_context(basic_mistake, context)
        assert len(ctx.conversation_history) == 10

    def test_extraction_limits_tool_outputs(self, rca, basic_mistake):
        """Should limit tool outputs to 5."""
        context = {
            "messages": [],
            "tool_outputs": [{"tool": f"tool_{i}"} for i in range(10)],
            "file_changes": []
        }

        ctx = rca.extract_context(basic_mistake, context)
        assert len(ctx.tool_outputs) == 5

    def test_extraction_with_workflow(self, rca, basic_mistake, basic_context):
        """Should include attribution when workflow present."""
        ctx = rca.extract_context(basic_mistake, basic_context)
        assert ctx.attribution is not None

    def test_extraction_without_workflow(self, rca, basic_mistake):
        """Should handle missing workflow."""
        context = {"messages": [], "tool_outputs": [], "file_changes": []}

        ctx = rca.extract_context(basic_mistake, context)
        assert ctx.attribution is None


class TestDetectPatterns:
    """Test pattern detection."""

    def test_basic_pattern_detection(self, rca, basic_mistake, similar_mistakes):
        """Should detect patterns from taxonomy."""
        pattern = rca.detect_patterns(basic_mistake, similar_mistakes)

        assert pattern['cluster_id'] == "cluster_001"
        assert pattern['cluster_name'] == "import_errors"
        assert 'is_new_pattern' in pattern
        assert 'pattern_frequency' in pattern

    def test_pattern_with_no_similar(self, rca, basic_mistake):
        """Should work with no similar mistakes."""
        pattern = rca.detect_patterns(basic_mistake, [])

        assert pattern['pattern_frequency'] == 1
        assert pattern['shared_with'] == []

    def test_pattern_detects_shared(self, rca, basic_mistake, similar_mistakes):
        """Should identify shared patterns with similar mistakes."""
        # Setup taxonomy mock to return same cluster for similar
        rca.taxonomy.mistake_to_cluster = {
            "mst_past_001": "cluster_001"
        }

        pattern = rca.detect_patterns(basic_mistake, similar_mistakes)

        assert len(pattern['shared_with']) >= 1
        assert pattern['pattern_frequency'] >= 2


class TestClassifyRootCause:
    """Test root cause classification."""

    def test_classify_knowledge_gap(self, rca):
        """Should classify knowledge_gap correctly."""
        ralph_result = {"root_cause": "knowledge_gap"}
        ctx = RCAContext(mistake_id="m", mistake_description="")
        pattern = {}

        result = rca.classify_root_cause(ralph_result, ctx, pattern)
        assert result == RootCauseCategory.KNOWLEDGE_GAP

    def test_classify_context_missing(self, rca):
        """Should classify context_missing correctly."""
        ralph_result = {"root_cause": "context_missing"}
        ctx = RCAContext(mistake_id="m", mistake_description="")
        pattern = {}

        result = rca.classify_root_cause(ralph_result, ctx, pattern)
        assert result == RootCauseCategory.CONTEXT_MISSING

    def test_classify_all_categories(self, rca):
        """Should handle all 8 categories."""
        ctx = RCAContext(mistake_id="m", mistake_description="")
        pattern = {}

        for category in RootCauseCategory:
            ralph_result = {"root_cause": category.value}
            result = rca.classify_root_cause(ralph_result, ctx, pattern)
            assert result == category

    def test_classify_unknown_defaults_knowledge_gap(self, rca):
        """Should default to knowledge_gap for unknown."""
        ralph_result = {"root_cause": "unknown_category"}
        ctx = RCAContext(mistake_id="m", mistake_description="")
        pattern = {}

        result = rca.classify_root_cause(ralph_result, ctx, pattern)
        assert result == RootCauseCategory.KNOWLEDGE_GAP

    def test_classify_handles_variations(self, rca):
        """Should handle case and format variations."""
        ctx = RCAContext(mistake_id="m", mistake_description="")
        pattern = {}

        # Test with spaces instead of underscores
        ralph_result = {"root_cause": "knowledge gap"}
        result = rca.classify_root_cause(ralph_result, ctx, pattern)
        assert result == RootCauseCategory.KNOWLEDGE_GAP


class TestGeneratePreventionRule:
    """Test prevention rule generation."""

    def test_uses_ralph_rule_if_present(self, rca):
        """Should use Ralph's suggested rule when available."""
        ralph_result = {"prevention_rule": "Always verify imports before saving"}
        ctx = RCAContext(mistake_id="m", mistake_description="", taxonomy_cluster="imports")

        rule = rca.generate_prevention_rule(
            RootCauseCategory.KNOWLEDGE_GAP,
            ralph_result,
            ctx
        )

        assert "verify imports" in rule.lower()

    def test_generates_default_for_knowledge_gap(self, rca):
        """Should generate appropriate rule for knowledge_gap."""
        ralph_result = {"prevention_rule": ""}
        ctx = RCAContext(mistake_id="m", mistake_description="", taxonomy_cluster="imports")

        rule = rca.generate_prevention_rule(
            RootCauseCategory.KNOWLEDGE_GAP,
            ralph_result,
            ctx
        )

        assert "documentation" in rule.lower() or "consult" in rule.lower()

    def test_generates_default_for_context_missing(self, rca):
        """Should generate appropriate rule for context_missing."""
        ralph_result = {}
        ctx = RCAContext(mistake_id="m", mistake_description="")

        rule = rca.generate_prevention_rule(
            RootCauseCategory.CONTEXT_MISSING,
            ralph_result,
            ctx
        )

        assert "context" in rule.lower()

    def test_generates_default_for_tool_misuse(self, rca):
        """Should generate appropriate rule for tool_misuse."""
        ralph_result = {}
        ctx = RCAContext(mistake_id="m", mistake_description="")

        rule = rca.generate_prevention_rule(
            RootCauseCategory.TOOL_MISUSE,
            ralph_result,
            ctx
        )

        assert "tool" in rule.lower()

    def test_generates_default_for_all_categories(self, rca):
        """Should generate rules for all categories."""
        ctx = RCAContext(mistake_id="m", mistake_description="")

        for category in RootCauseCategory:
            rule = rca.generate_prevention_rule(category, {}, ctx)
            assert len(rule) > 10  # Should be meaningful


class TestBuildRCAPrompt:
    """Test RCA prompt building."""

    def test_basic_prompt_structure(self, rca, similar_mistakes):
        """Should build prompt with correct structure."""
        ctx = RCAContext(
            mistake_id="m",
            mistake_description="Test mistake description"
        )
        pattern = {"cluster_name": "test_cluster", "pattern_frequency": 3, "is_new_pattern": False}

        prompt = rca._build_rca_prompt(ctx, similar_mistakes, pattern)

        assert "## Mistake Description" in prompt
        assert "Test mistake description" in prompt
        assert "## Pattern Information" in prompt
        assert "test_cluster" in prompt

    def test_prompt_includes_code(self, rca):
        """Should include surrounding code when present."""
        ctx = RCAContext(
            mistake_id="m",
            mistake_description="Test",
            surrounding_code="def test():\n    pass"
        )
        pattern = {"cluster_name": "test", "pattern_frequency": 1, "is_new_pattern": True}

        prompt = rca._build_rca_prompt(ctx, [], pattern)

        assert "## Surrounding Code" in prompt
        assert "def test():" in prompt

    def test_prompt_truncates_long_code(self, rca):
        """Should truncate code longer than 500 chars."""
        long_code = "x" * 1000
        ctx = RCAContext(
            mistake_id="m",
            mistake_description="Test",
            surrounding_code=long_code
        )
        pattern = {"cluster_name": "test", "pattern_frequency": 1, "is_new_pattern": True}

        prompt = rca._build_rca_prompt(ctx, [], pattern)

        assert "truncated" in prompt.lower()

    def test_prompt_includes_similar(self, rca, similar_mistakes):
        """Should include similar mistakes."""
        ctx = RCAContext(mistake_id="m", mistake_description="Test")
        pattern = {"cluster_name": "test", "pattern_frequency": 1, "is_new_pattern": True}

        prompt = rca._build_rca_prompt(ctx, similar_mistakes, pattern)

        assert "## Similar Past Mistakes" in prompt
        assert "Wrong import" in prompt

    def test_prompt_includes_prevention_rules(self, rca, similar_mistakes):
        """Should include prevention rules from similar mistakes."""
        ctx = RCAContext(mistake_id="m", mistake_description="Test")
        pattern = {"cluster_name": "test", "pattern_frequency": 1, "is_new_pattern": True}

        prompt = rca._build_rca_prompt(ctx, similar_mistakes, pattern)

        assert "## Previous Prevention Rules" in prompt
        assert "Verify import paths" in prompt


class TestCalculateAgreement:
    """Test agreement calculation."""

    def test_single_iteration_full_agreement(self, rca):
        """Single iteration should return 1.0."""
        iterations = [{"model": "claude", "result": {"root_cause": "knowledge_gap"}}]

        agreement = rca._calculate_agreement(iterations)
        assert agreement == 1.0

    def test_full_agreement_multiple_iterations(self, rca):
        """All same root cause should return 1.0."""
        iterations = [
            {"model": "claude", "result": {"root_cause": "knowledge_gap"}},
            {"model": "gemini", "result": {"root_cause": "knowledge_gap"}},
            {"model": "glm", "result": {"root_cause": "knowledge_gap"}}
        ]

        agreement = rca._calculate_agreement(iterations)
        assert agreement >= 0.9

    def test_partial_agreement(self, rca):
        """2/3 agreement should be around 0.66."""
        iterations = [
            {"model": "claude", "result": {"root_cause": "knowledge_gap"}},
            {"model": "gemini", "result": {"root_cause": "knowledge_gap"}},
            {"model": "glm", "result": {"root_cause": "tool_misuse"}}
        ]

        agreement = rca._calculate_agreement(iterations)
        assert 0.5 <= agreement <= 0.8

    def test_no_agreement(self, rca):
        """All different should be low."""
        iterations = [
            {"model": "claude", "result": {"root_cause": "knowledge_gap"}},
            {"model": "gemini", "result": {"root_cause": "tool_misuse"}},
            {"model": "glm", "result": {"root_cause": "edge_case"}}
        ]

        agreement = rca._calculate_agreement(iterations)
        assert agreement < 0.5

    def test_confirmation_bonus(self, rca):
        """Confirmed results should boost agreement."""
        iterations = [
            {"model": "claude", "result": {"root_cause": "knowledge_gap"}},
            {"model": "gemini", "result": {"root_cause": "knowledge_gap", "confirmed": True}},
        ]

        agreement = rca._calculate_agreement(iterations)
        assert agreement > 0.8


class TestParseJsonResponse:
    """Test JSON response parsing."""

    def test_parse_direct_json(self, rca):
        """Should parse direct JSON."""
        content = '{"root_cause": "knowledge_gap", "confidence": 0.85}'

        result = rca._parse_json_response(content)
        assert result['root_cause'] == "knowledge_gap"
        assert result['confidence'] == 0.85

    def test_parse_json_in_code_block(self, rca):
        """Should parse JSON in markdown code block."""
        content = '''Here is the analysis:
```json
{"root_cause": "tool_misuse", "confidence": 0.9}
```'''

        result = rca._parse_json_response(content)
        assert result['root_cause'] == "tool_misuse"

    def test_parse_json_without_block_marker(self, rca):
        """Should find JSON in text."""
        content = 'The analysis shows {"root_cause": "edge_case"} as the cause.'

        result = rca._parse_json_response(content)
        assert result['root_cause'] == "edge_case"

    def test_parse_invalid_returns_raw(self, rca):
        """Should return raw response for unparseable content."""
        content = "This is not JSON at all"

        result = rca._parse_json_response(content)
        assert 'raw_response' in result
        assert result['parse_error'] is True


class TestSimulateClaudeResponse:
    """Test Claude response simulation."""

    def test_simulates_knowledge_gap(self, rca):
        """Should detect import-related as knowledge_gap."""
        prompt = "The agent used the wrong import module"

        result = rca._simulate_claude_response(prompt)
        assert result['root_cause'] == "knowledge_gap"
        assert 'confidence' in result

    def test_simulates_tool_misuse(self, rca):
        """Should detect tool-related as tool_misuse."""
        prompt = "The agent ran the wrong command tool"

        result = rca._simulate_claude_response(prompt)
        assert result['root_cause'] == "tool_misuse"

    def test_simulates_context_missing(self, rca):
        """Should detect missing context."""
        prompt = "Information was missing from the context"

        result = rca._simulate_claude_response(prompt)
        assert result['root_cause'] == "context_missing"

    def test_always_returns_valid_structure(self, rca):
        """Should always return valid result structure."""
        prompt = "Random prompt without keywords"

        result = rca._simulate_claude_response(prompt)
        assert 'root_cause' in result
        assert 'explanation' in result
        assert 'contributing_factors' in result
        assert 'prevention_rule' in result
        assert 'confidence' in result


class TestEmitToNeo4j:
    """Test Neo4j query generation."""

    def test_generates_main_query(self, rca):
        """Should generate main mistake node query."""
        result = RCAResult(
            mistake_id="mst_001",
            root_cause=RootCauseCategory.KNOWLEDGE_GAP,
            explanation="Test",
            contributing_factors=["factor1"],
            prevention_rule="Rule",
            confidence=0.85,
            similar_mistakes=[],
            ralph_iterations=[],
            consensus_reached=True,
            agreement_level=0.9
        )

        neo4j = rca.emit_to_neo4j(result)

        assert 'queries' in neo4j
        assert len(neo4j['queries']) >= 1
        assert 'MERGE (m:Mistake' in neo4j['queries'][0]['cypher']
        assert neo4j['queries'][0]['params']['mistake_id'] == "mst_001"

    def test_generates_factor_queries(self, rca):
        """Should generate queries for contributing factors."""
        result = RCAResult(
            mistake_id="mst_001",
            root_cause=RootCauseCategory.KNOWLEDGE_GAP,
            explanation="Test",
            contributing_factors=["factor1", "factor2"],
            prevention_rule="Rule",
            confidence=0.85,
            similar_mistakes=[],
            ralph_iterations=[],
            consensus_reached=True
        )

        neo4j = rca.emit_to_neo4j(result)

        # 1 main + 2 factors
        assert len(neo4j['queries']) >= 3
        factor_queries = [q for q in neo4j['queries'] if 'CAUSED_BY' in q['cypher']]
        assert len(factor_queries) == 2

    def test_generates_similar_queries(self, rca, similar_mistakes):
        """Should generate queries for similar mistakes."""
        result = RCAResult(
            mistake_id="mst_001",
            root_cause=RootCauseCategory.KNOWLEDGE_GAP,
            explanation="Test",
            contributing_factors=[],
            prevention_rule="Rule",
            confidence=0.85,
            similar_mistakes=similar_mistakes,
            ralph_iterations=[],
            consensus_reached=True
        )

        neo4j = rca.emit_to_neo4j(result)

        similar_queries = [q for q in neo4j['queries'] if 'SIMILAR_TO' in q['cypher']]
        assert len(similar_queries) == 2


class TestRalphRCA:
    """Test Ralph multi-model RCA."""

    @pytest.mark.asyncio
    async def test_runs_three_models(self, rca, similar_mistakes):
        """Should run Claude, Gemini, GLM in sequence."""
        ctx = RCAContext(mistake_id="m", mistake_description="Test mistake")
        pattern = {"cluster_name": "test", "pattern_frequency": 1, "is_new_pattern": True}

        result = await rca.ralph_rca(ctx, similar_mistakes, pattern)

        # Should have at least 3 iterations
        assert len(result['iterations']) >= 3
        models_used = [it['model'] for it in result['iterations']]
        assert 'claude' in models_used
        assert 'gemini' in models_used
        assert 'glm' in models_used

    @pytest.mark.asyncio
    async def test_returns_valid_structure(self, rca):
        """Should return complete result structure."""
        ctx = RCAContext(mistake_id="m", mistake_description="Test")
        pattern = {"cluster_name": "test", "pattern_frequency": 1, "is_new_pattern": True}

        result = await rca.ralph_rca(ctx, [], pattern)

        assert 'root_cause' in result
        assert 'explanation' in result
        assert 'factors' in result
        assert 'prevention_rule' in result
        assert 'confidence' in result
        assert 'iterations' in result
        assert 'consensus' in result

    @pytest.mark.asyncio
    async def test_checks_convergence(self, rca):
        """Should check for convergence threshold."""
        ctx = RCAContext(mistake_id="m", mistake_description="Test")
        pattern = {"cluster_name": "test", "pattern_frequency": 1, "is_new_pattern": True}

        result = await rca.ralph_rca(ctx, [], pattern)

        # Simulated responses should converge
        assert 'consensus' in result
        assert isinstance(result['consensus'], bool)


class TestFullAnalyze:
    """Test full analysis pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, rca, basic_mistake, basic_context):
        """Should run complete analysis pipeline."""
        result = await rca.analyze(basic_mistake, basic_context)

        assert isinstance(result, RCAResult)
        assert result.mistake_id == "mst_test_001"
        assert isinstance(result.root_cause, RootCauseCategory)
        assert len(result.prevention_rule) > 0
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_caches_results(self, rca, basic_mistake, basic_context):
        """Should cache analysis results."""
        result1 = await rca.analyze(basic_mistake, basic_context)
        result2 = await rca.analyze(basic_mistake, basic_context)

        assert result1 is result2  # Same cached object

    @pytest.mark.asyncio
    async def test_clear_cache(self, rca, basic_mistake, basic_context):
        """Should clear cache when requested."""
        await rca.analyze(basic_mistake, basic_context)
        rca.clear_cache()

        assert len(rca._result_cache) == 0

    @pytest.mark.asyncio
    async def test_generates_mistake_id_if_missing(self, rca, basic_context):
        """Should generate ID if not provided."""
        mistake = {"description": "Test mistake without ID"}

        result = await rca.analyze(mistake, basic_context)

        assert result.mistake_id.startswith("mst_")


class TestFindSimilarMistakes:
    """Test similar mistake search."""

    @pytest.mark.asyncio
    async def test_returns_empty_without_httpx(self, rca):
        """Should return empty list if httpx unavailable."""
        with patch('lib.mistake_rca.HTTPX_AVAILABLE', False):
            result = await rca.find_similar_mistakes("test description")
            assert result == []

    @pytest.mark.asyncio
    async def test_handles_qdrant_error(self, rca):
        """Should handle Qdrant connection errors gracefully."""
        # Will fail to connect, should return empty list
        result = await rca.find_similar_mistakes("test description")
        assert isinstance(result, list)


class TestGetSurroundingCode:
    """Test surrounding code extraction."""

    def test_returns_none_for_missing_file(self, rca):
        """Should return None for non-existent file."""
        result = rca._get_surrounding_code("/nonexistent/file.py", 10)
        assert result is None

    def test_returns_none_for_unreadable_file(self, rca):
        """Should handle unreadable files."""
        result = rca._get_surrounding_code("/root/secret", 10)
        assert result is None
