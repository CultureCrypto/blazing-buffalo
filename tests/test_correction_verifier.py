"""
Unit tests for correction verifier (BB-008).

Tests verification logic for preventing false positive corrections.
"""

import pytest
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from correction_verifier import (
    CorrectionVerifier,
    VerificationStatus,
    VerificationResult
)
from mistake_types import DetectedMistake, DetectionMethod, Severity


@pytest.fixture
def verifier():
    """Create a verifier instance."""
    return CorrectionVerifier()


@pytest.fixture
def sample_mistake():
    """Create a sample detected mistake."""
    return DetectedMistake(
        id="mst_test123456",
        category="tool_error.Bash",
        description="Used wrong command flag",
        session_id="session_123",
        agent_id="backend-developer",
        file_path="/home/pook/test.py",
        line_number=42,
        detection_method="user_correction",
        severity="medium",
        confidence=0.8,
        timestamp=datetime.now().isoformat(),
        context_hash="hash123",
        raw_signal="User said: no that's wrong"
    )


@pytest.fixture
def minimal_context():
    """Minimal context for testing."""
    return {
        'previous_messages': [],
        'tool_outputs': [],
        'file_changes': [],
        'user_profile': {},
        'suggested_correction': '',
        'task_description': '',
        'recent_test_results': {},
        'messages_since_mistake': 1
    }


class TestSyntaxValidityCheck:
    """Tests for syntax validity checking."""

    def test_valid_python_code(self, verifier, sample_mistake, minimal_context):
        """Valid Python code should pass."""
        minimal_context['suggested_correction'] = 'print("hello")'

        passed, score, details = verifier.check_syntax_validity(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score == 1.0
        assert "parses successfully" in details.lower()

    def test_invalid_python_syntax(self, verifier, sample_mistake, minimal_context):
        """Invalid Python syntax should fail."""
        minimal_context['suggested_correction'] = 'print("hello"'  # Missing closing paren

        passed, score, details = verifier.check_syntax_validity(
            sample_mistake, minimal_context
        )

        assert passed is False
        assert score == 0.0
        assert "syntax error" in details.lower()

    def test_no_correction_provided(self, verifier, sample_mistake, minimal_context):
        """No correction should pass with neutral score."""
        minimal_context['suggested_correction'] = ''

        passed, score, details = verifier.check_syntax_validity(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score == 0.7
        assert "no correction" in details.lower()

    def test_non_python_file(self, verifier, sample_mistake, minimal_context):
        """Non-Python files should pass with neutral score."""
        sample_mistake.file_path = "/home/pook/test.js"
        minimal_context['suggested_correction'] = 'console.log("test")'

        passed, score, details = verifier.check_syntax_validity(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score > 0.5

    def test_unbalanced_braces_js(self, verifier, sample_mistake, minimal_context):
        """JS code with unbalanced braces should fail."""
        sample_mistake.file_path = "/home/pook/test.js"
        minimal_context['suggested_correction'] = 'function test() { console.log("hi");'

        passed, score, details = verifier.check_syntax_validity(
            sample_mistake, minimal_context
        )

        assert passed is False
        assert "unbalanced" in details.lower()


class TestSemanticConsistencyCheck:
    """Tests for semantic consistency checking."""

    def test_aligned_with_task(self, verifier, sample_mistake, minimal_context):
        """Correction aligned with task should pass."""
        sample_mistake.description = "Fix authentication error in login function"
        minimal_context['task_description'] = "Implement user login authentication system"

        passed, score, details = verifier.check_semantic_consistency(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score > 0.5
        assert "aligned" in details.lower()

    def test_contradicts_previous_message(self, verifier, sample_mistake, minimal_context):
        """Correction contradicting previous message should fail."""
        sample_mistake.description = "Don't use requests library"
        minimal_context['previous_messages'] = [
            "Use requests library for HTTP calls"
        ]

        passed, score, details = verifier.check_semantic_consistency(
            sample_mistake, minimal_context
        )

        assert passed is False
        assert score < 0.5
        assert "contradicts" in details.lower()

    def test_no_task_context(self, verifier, sample_mistake, minimal_context):
        """No task context should give neutral score."""
        minimal_context['task_description'] = ''

        passed, score, details = verifier.check_semantic_consistency(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score == 0.7

    def test_low_alignment_fails(self, verifier, sample_mistake, minimal_context):
        """Low alignment with task should fail."""
        sample_mistake.description = "Fix database connection pool"
        minimal_context['task_description'] = "Build frontend React components"

        passed, score, details = verifier.check_semantic_consistency(
            sample_mistake, minimal_context
        )

        assert passed is False
        assert score < 0.5


class TestAgainstTestsCheck:
    """Tests for test result validation."""

    def test_addresses_test_failure(self, verifier, sample_mistake, minimal_context):
        """Correction addressing test failure should pass."""
        sample_mistake.description = "Fix assertion error expected 200 actual 404"
        minimal_context['recent_test_results'] = {
            'status': 'failing',
            'message': 'AssertionError: expected 200, actual 404'
        }

        passed, score, details = verifier.check_against_tests(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score == 1.0
        assert "addresses" in details.lower()

    def test_doesnt_address_failure(self, verifier, sample_mistake, minimal_context):
        """Correction not addressing failure should fail."""
        sample_mistake.description = "Change variable name"
        minimal_context['recent_test_results'] = {
            'status': 'failing',
            'message': 'ValueError: invalid database connection string'
        }

        passed, score, details = verifier.check_against_tests(
            sample_mistake, minimal_context
        )

        assert passed is False
        assert score < 0.5

    def test_no_test_results(self, verifier, sample_mistake, minimal_context):
        """No test results should give neutral score."""
        minimal_context['recent_test_results'] = {}

        passed, score, details = verifier.check_against_tests(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score == 0.6

    def test_tests_passing(self, verifier, sample_mistake, minimal_context):
        """Correction when tests passing should be cautious."""
        minimal_context['recent_test_results'] = {
            'status': 'passing'
        }

        passed, score, details = verifier.check_against_tests(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score == 0.5  # Neutral - might be style correction


class TestUserHistoryCheck:
    """Tests for user history validation."""

    def test_reliable_user(self, verifier, sample_mistake, minimal_context):
        """Reliable user should pass."""
        minimal_context['user_profile'] = {
            'correction_accuracy': 0.9,
            'domain_familiarity': {'tool_error': 0.85}
        }

        passed, score, details = verifier.check_user_history(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score >= 0.7

    def test_unreliable_user(self, verifier, sample_mistake, minimal_context):
        """Unreliable user should fail."""
        minimal_context['user_profile'] = {
            'correction_accuracy': 0.4,
            'domain_familiarity': {'tool_error': 0.3}
        }

        passed, score, details = verifier.check_user_history(
            sample_mistake, minimal_context
        )

        assert passed is False
        assert score < 0.7

    def test_no_user_history(self, verifier, sample_mistake, minimal_context):
        """No user history should give neutral score."""
        minimal_context['user_profile'] = {}

        passed, score, details = verifier.check_user_history(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score == 0.5


class TestContextCoherenceCheck:
    """Tests for context coherence validation."""

    def test_timely_correction(self, verifier, sample_mistake, minimal_context):
        """Timely correction (1 message) should pass with high score."""
        minimal_context['messages_since_mistake'] = 1

        passed, score, details = verifier.check_context_coherence(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score >= 0.85

    def test_late_correction(self, verifier, sample_mistake, minimal_context):
        """Late correction (6+ messages) should fail."""
        minimal_context['messages_since_mistake'] = 6

        passed, score, details = verifier.check_context_coherence(
            sample_mistake, minimal_context
        )

        assert passed is False
        assert score < 0.5

    def test_moderately_late(self, verifier, sample_mistake, minimal_context):
        """Moderately late (3 messages) should pass with lower score."""
        minimal_context['messages_since_mistake'] = 3

        passed, score, details = verifier.check_context_coherence(
            sample_mistake, minimal_context
        )

        assert passed is True
        assert score >= 0.5
        assert score < 0.85


class TestFullVerification:
    """Tests for full verification workflow."""

    def test_high_confidence_verified(self, verifier, sample_mistake, minimal_context):
        """High confidence should result in VERIFIED status."""
        # Set up all checks to pass
        minimal_context['suggested_correction'] = 'print("test")'
        minimal_context['task_description'] = 'Fix test command'
        minimal_context['user_profile'] = {'correction_accuracy': 0.9}
        minimal_context['messages_since_mistake'] = 1
        sample_mistake.description = "Fix test command"

        result = verifier.verify(sample_mistake, minimal_context)

        assert result.status == VerificationStatus.VERIFIED
        assert result.confidence >= 0.6
        assert result.recommendation == "Add to knowledge base"
        assert result.clarification_needed is None

    def test_low_confidence_rejected(self, verifier, sample_mistake, minimal_context):
        """Low confidence should result in REJECTED status."""
        # Set up checks to fail
        minimal_context['suggested_correction'] = 'print("test"'  # Syntax error
        minimal_context['user_profile'] = {'correction_accuracy': 0.3}
        minimal_context['messages_since_mistake'] = 10
        minimal_context['previous_messages'] = ["Use this exact approach"]
        sample_mistake.description = "Don't use this approach"

        result = verifier.verify(sample_mistake, minimal_context)

        assert result.status == VerificationStatus.REJECTED
        assert result.confidence < 0.4
        assert "Discard" in result.recommendation

    def test_uncertain_requests_clarification(self, verifier, sample_mistake, minimal_context):
        """Medium confidence should result in UNCERTAIN status."""
        # Set up mixed results
        minimal_context['suggested_correction'] = 'print("test")'
        minimal_context['user_profile'] = {'correction_accuracy': 0.6}
        minimal_context['messages_since_mistake'] = 4

        result = verifier.verify(sample_mistake, minimal_context)

        if result.status == VerificationStatus.UNCERTAIN:
            assert 0.4 <= result.confidence < 0.6
            assert "clarification" in result.recommendation.lower()
            assert result.clarification_needed is not None

    def test_all_checks_recorded(self, verifier, sample_mistake, minimal_context):
        """All checks should be recorded in result."""
        result = verifier.verify(sample_mistake, minimal_context)

        total_checks = len(result.checks_passed) + len(result.checks_failed)
        assert total_checks == 5  # All 5 checks should be accounted for


class TestClarificationGeneration:
    """Tests for clarification question generation."""

    def test_semantic_failure_clarification(self, verifier, sample_mistake):
        """Semantic consistency failure should generate specific question."""
        failed_checks = ["check_semantic_consistency: Contradicts earlier message"]

        question = verifier._generate_clarification_question(
            sample_mistake, failed_checks
        )

        assert "clarify" in question.lower()
        assert "incorrect" in question.lower() or "expected" in question.lower()

    def test_user_history_clarification(self, verifier, sample_mistake):
        """User history failure should ask for confirmation."""
        failed_checks = ["check_user_history: User has mixed history"]

        question = verifier._generate_clarification_question(
            sample_mistake, failed_checks
        )

        assert "confirm" in question.lower()
        assert "correction" in question.lower()

    def test_test_failure_clarification(self, verifier, sample_mistake):
        """Test failure should ask about functional vs style."""
        failed_checks = ["check_against_tests: Doesn't address test failure"]

        question = verifier._generate_clarification_question(
            sample_mistake, failed_checks
        )

        assert "test" in question.lower()

    def test_context_coherence_clarification(self, verifier, sample_mistake):
        """Late correction should ask about timing."""
        failed_checks = ["check_context_coherence: Correction 6 messages late"]

        question = verifier._generate_clarification_question(
            sample_mistake, failed_checks
        )

        assert "message" in question.lower() or "earlier" in question.lower()


class TestHelperMethods:
    """Tests for helper methods."""

    def test_is_contradictory_use_pattern(self, verifier):
        """Should detect 'use X' vs 'don't use X' contradictions."""
        assert verifier._is_contradictory(
            "use requests library",
            "don't use requests library"
        )

    def test_is_contradictory_correct_wrong(self, verifier):
        """Should detect 'X is correct' vs 'X is wrong' contradictions."""
        assert verifier._is_contradictory(
            "approach is correct",
            "approach is wrong"
        )

    def test_not_contradictory(self, verifier):
        """Should not flag non-contradictory statements."""
        assert not verifier._is_contradictory(
            "use async functions",
            "implement async functions for better performance"
        )

    def test_calculate_alignment_high(self, verifier):
        """High keyword overlap should give high score."""
        score = verifier._calculate_alignment(
            "fix authentication login error timeout",
            "implement user authentication and login system"
        )
        assert score > 0.5

    def test_calculate_alignment_low(self, verifier):
        """Low keyword overlap should give low score."""
        score = verifier._calculate_alignment(
            "fix database connection",
            "implement frontend react components"
        )
        assert score < 0.5

    def test_correction_addresses_failure_match(self, verifier, sample_mistake):
        """Should detect when correction addresses failure."""
        sample_mistake.description = "Fix assertion error: expected 200 actual 404"

        result = verifier._correction_addresses_failure(
            sample_mistake,
            "AssertionError: expected 200, actual 404"
        )

        assert result is True

    def test_correction_addresses_failure_no_match(self, verifier, sample_mistake):
        """Should detect when correction doesn't address failure."""
        sample_mistake.description = "Change variable name"

        result = verifier._correction_addresses_failure(
            sample_mistake,
            "ValueError: invalid connection string"
        )

        assert result is False

    def test_balanced_braces_valid(self, verifier):
        """Should detect balanced braces."""
        assert verifier._check_balanced_braces("function test() { return {}; }")

    def test_balanced_braces_invalid(self, verifier):
        """Should detect unbalanced braces."""
        assert not verifier._check_balanced_braces("function test() { return {};")
        assert not verifier._check_balanced_braces("function test() { return {; }")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
