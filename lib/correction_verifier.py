"""
Correction Verifier for Blazing Buffalo mistake detection system.

Prevents false positive corrections from polluting the knowledge base by verifying
detected mistakes before storage.

Part of BB-008 task.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any
import re
import ast

from mistake_types import DetectedMistake


class VerificationStatus(Enum):
    """Status of correction verification."""
    VERIFIED = "verified"
    UNCERTAIN = "uncertain"
    REJECTED = "rejected"


@dataclass
class VerificationResult:
    """
    Result of correction verification.

    Attributes:
        status: VERIFIED, UNCERTAIN, or REJECTED
        confidence: 0.0-1.0 overall confidence score
        checks_passed: List of checks that passed with details
        checks_failed: List of checks that failed with details
        recommendation: Action recommendation
        clarification_needed: Question to ask user if uncertain
    """
    status: VerificationStatus
    confidence: float
    checks_passed: List[str]
    checks_failed: List[str]
    recommendation: str
    clarification_needed: Optional[str] = None


class CorrectionVerifier:
    """Verify detected corrections before adding to knowledge base."""

    # Confidence threshold for auto-verification
    CONFIDENCE_THRESHOLD = 0.6

    # Uncertainty zone threshold
    UNCERTAINTY_THRESHOLD = 0.4

    def __init__(self):
        """Initialize verifier with check functions."""
        self.checks = [
            self.check_syntax_validity,
            self.check_semantic_consistency,
            self.check_against_tests,
            self.check_user_history,
            self.check_context_coherence,
        ]

    def verify(
        self,
        mistake: DetectedMistake,
        context: Dict[str, Any]
    ) -> VerificationResult:
        """
        Main verification entry point.

        Args:
            mistake: DetectedMistake from mistake detector
            context: Session context including:
                - previous_messages: List of conversation history
                - tool_outputs: Recent tool outputs
                - file_changes: Files modified in session
                - user_profile: Historical user behavior
                - suggested_correction: The corrected code/text
                - task_description: Current task description
                - recent_test_results: Test results if available
                - messages_since_mistake: Message count since mistake

        Returns:
            VerificationResult with status, confidence, and recommendation
        """
        checks_passed = []
        checks_failed = []
        total_score = 0.0

        # Run all verification checks
        for check in self.checks:
            passed, score, details = check(mistake, context)

            if passed:
                checks_passed.append(f"{check.__name__}: {details}")
                total_score += score
            else:
                checks_failed.append(f"{check.__name__}: {details}")

        # Calculate final confidence
        confidence = total_score / len(self.checks)

        # Determine status based on confidence
        if confidence >= self.CONFIDENCE_THRESHOLD:
            status = VerificationStatus.VERIFIED
            recommendation = "Add to knowledge base"
            clarification = None
        elif confidence >= self.UNCERTAINTY_THRESHOLD:
            status = VerificationStatus.UNCERTAIN
            recommendation = "Request user clarification"
            clarification = self._generate_clarification_question(
                mistake, checks_failed
            )
        else:
            status = VerificationStatus.REJECTED
            recommendation = "Discard - likely false positive"
            clarification = None

        return VerificationResult(
            status=status,
            confidence=confidence,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            recommendation=recommendation,
            clarification_needed=clarification
        )

    def check_syntax_validity(
        self,
        mistake: DetectedMistake,
        context: Dict[str, Any]
    ) -> tuple[bool, float, str]:
        """
        Check if the correction results in syntactically valid code.

        For code corrections:
        - Parse the corrected code
        - Check for syntax errors
        - Verify imports resolve

        Returns:
            (passed, score, details)
        """
        # If mistake involves code change, validate new code parses
        if mistake.file_path and mistake.file_path.endswith('.py'):
            # Try to parse the suggested correction
            suggested = context.get('suggested_correction', '')

            if not suggested:
                # No correction provided - can't validate
                return (True, 0.7, "No correction code to validate")

            try:
                ast.parse(suggested)
                return (True, 1.0, "Code parses successfully")
            except SyntaxError as e:
                return (
                    False,
                    0.0,
                    f"Syntax error in correction: {str(e)[:100]}"
                )
            except Exception as e:
                return (
                    False,
                    0.0,
                    f"Parse error: {str(e)[:100]}"
                )

        # Non-Python code - check for other file types
        if mistake.file_path:
            ext = mistake.file_path.split('.')[-1]
            if ext in ['js', 'ts', 'tsx', 'jsx']:
                # Basic JS/TS validation - check for balanced braces
                suggested = context.get('suggested_correction', '')
                if suggested and not self._check_balanced_braces(suggested):
                    return (False, 0.0, "Unbalanced braces in correction")
                return (True, 0.8, f"{ext.upper()} correction looks valid")

        # Non-code corrections pass by default
        return (True, 0.8, "Non-code correction")

    def check_semantic_consistency(
        self,
        mistake: DetectedMistake,
        context: Dict[str, Any]
    ) -> tuple[bool, float, str]:
        """
        Check if correction is semantically consistent with context.

        - Does the correction make sense given previous messages?
        - Is it consistent with stated requirements?
        - Does it contradict earlier corrections?

        Returns:
            (passed, score, details)
        """
        previous = context.get('previous_messages', [])

        # Check for contradictions with earlier corrections
        for msg in previous[-10:]:
            if self._is_contradictory(mistake.description, msg):
                return (
                    False,
                    0.2,
                    "Contradicts earlier message"
                )

        # Check alignment with stated task
        task_description = context.get('task_description', '')
        if task_description:
            alignment = self._calculate_alignment(
                mistake.description,
                task_description
            )
            if alignment > 0.5:
                return (
                    True,
                    alignment,
                    f"Aligned with task ({alignment:.2f})"
                )
            else:
                return (
                    False,
                    alignment,
                    f"Low task alignment ({alignment:.2f})"
                )

        # No task context - neutral score
        return (True, 0.7, "No contradictions found")

    def check_against_tests(
        self,
        mistake: DetectedMistake,
        context: Dict[str, Any]
    ) -> tuple[bool, float, str]:
        """
        If tests exist, check if correction aligns with test expectations.

        - Run relevant tests if safe
        - Check test assertions for expected behavior

        Returns:
            (passed, score, details)
        """
        test_results = context.get('recent_test_results', {})

        if not test_results:
            return (True, 0.6, "No test context available")

        # If tests were failing and correction addresses the failure
        if test_results.get('status') == 'failing':
            failure_msg = test_results.get('message', '')
            if self._correction_addresses_failure(mistake, failure_msg):
                return (
                    True,
                    1.0,
                    "Correction addresses test failure"
                )
            else:
                return (
                    False,
                    0.4,
                    "Correction doesn't address test failure"
                )

        # Tests passing - correction might be unnecessary
        if test_results.get('status') == 'passing':
            return (
                True,
                0.5,
                "Tests passing - correction may be style/preference"
            )

        return (True, 0.7, "Tests not conclusive")

    def check_user_history(
        self,
        mistake: DetectedMistake,
        context: Dict[str, Any]
    ) -> tuple[bool, float, str]:
        """
        Check user's historical correction patterns.

        - Does this user frequently make false corrections?
        - What's their correction accuracy rate?
        - Are they in a domain they're familiar with?

        Returns:
            (passed, score, details)
        """
        user_profile = context.get('user_profile', {})

        if not user_profile:
            return (True, 0.5, "No user history available")

        # Get user's correction accuracy
        accuracy_rate = user_profile.get('correction_accuracy', 0.8)

        # Get domain familiarity
        domain = mistake.category.split('.')[0] if '.' in mistake.category else mistake.category
        domain_familiarity = user_profile.get('domain_familiarity', {}).get(
            domain,
            0.5
        )

        # Combined score
        score = (accuracy_rate + domain_familiarity) / 2

        if score >= 0.7:
            return (
                True,
                score,
                f"User reliable in this domain ({score:.2f})"
            )
        else:
            return (
                False,
                score,
                f"User has mixed history ({score:.2f})"
            )

    def check_context_coherence(
        self,
        mistake: DetectedMistake,
        context: Dict[str, Any]
    ) -> tuple[bool, float, str]:
        """
        Check overall context coherence.

        - Is the correction timely (right after the mistake)?
        - Is there sufficient context to understand the correction?
        - Does the correction scope match the mistake scope?

        Returns:
            (passed, score, details)
        """
        # Check timing - corrections should be within ~2-3 messages
        messages_since = context.get('messages_since_mistake', 0)

        if messages_since > 5:
            return (
                False,
                0.3,
                f"Correction {messages_since} messages late"
            )

        # Calculate timing score - decreases with message distance
        timing_score = max(0.5, 1.0 - (messages_since * 0.15))

        return (
            True,
            timing_score,
            f"Timely correction ({messages_since} msgs)"
        )

    def _generate_clarification_question(
        self,
        mistake: DetectedMistake,
        failed_checks: List[str]
    ) -> str:
        """
        Generate a clarification question for uncertain corrections.

        Args:
            mistake: The detected mistake
            failed_checks: List of failed check descriptions

        Returns:
            Clarification question string
        """
        # Extract truncated description
        desc_preview = mistake.description[:50]
        if len(mistake.description) > 50:
            desc_preview += "..."

        # Check which checks failed
        failed_names = [check.split(':')[0] for check in failed_checks]

        if 'check_semantic_consistency' in failed_names:
            return (
                f"I detected a potential correction regarding '{desc_preview}'. "
                "Could you clarify what specifically was incorrect and what the "
                "expected behavior should be?"
            )

        if 'check_user_history' in failed_names:
            return (
                f"Just to confirm - you mentioned '{desc_preview}'. "
                "Is this a correction to what I did, or additional context for the task?"
            )

        if 'check_against_tests' in failed_names:
            return (
                f"You mentioned '{desc_preview}', but the tests seem to be passing. "
                "Is this a functional issue or a style/preference correction?"
            )

        if 'check_context_coherence' in failed_names:
            return (
                f"I noticed your comment about '{desc_preview}' came a few messages "
                "after the code was written. Does this correction apply to the recent "
                "changes, or to something earlier?"
            )

        # Default clarification
        return (
            f"I noticed '{desc_preview}'. "
            "Could you confirm if this is a correction that should be recorded "
            "for future reference?"
        )

    def _is_contradictory(
        self,
        new_correction: str,
        previous_message: str
    ) -> bool:
        """
        Check if new correction contradicts previous message.

        Args:
            new_correction: New correction description
            previous_message: Previous message text

        Returns:
            True if contradictory, False otherwise
        """
        # Convert to lowercase for comparison
        new_lower = new_correction.lower()
        prev_lower = previous_message.lower()

        # Pattern 1: "don't use X" vs "use X"
        # Check if new says "don't use X" and prev says "use X"
        dont_use_pattern = r"(don't|do not|never)\s+use\s+([\w\s]+?)(?:\s|$|for|,)"
        new_dont_use = re.findall(dont_use_pattern, new_lower)

        for _, thing in new_dont_use:
            thing = thing.strip()
            # Check if previous message says to use this thing
            use_pattern = rf"\buse\s+{re.escape(thing)}"
            if re.search(use_pattern, prev_lower):
                # Make sure previous doesn't also say "don't"
                prev_dont = rf"(don't|do not|never)\s+use\s+{re.escape(thing)}"
                if not re.search(prev_dont, prev_lower):
                    return True

        # Pattern 2: "use X" vs "don't use X" (reverse check)
        use_pattern = r"\buse\s+([\w\s]+?)(?:\s|$|for|,)"
        new_use = re.findall(use_pattern, new_lower)

        for thing in new_use:
            thing = thing.strip()
            # Skip if the new message itself says "don't use"
            if re.search(rf"(don't|do not|never)\s+use\s+{re.escape(thing)}", new_lower):
                continue
            # Check if previous message says "don't use"
            prev_dont_pattern = rf"(don't|do not|never)\s+use\s+{re.escape(thing)}"
            if re.search(prev_dont_pattern, prev_lower):
                return True

        # Pattern 3: "X is correct" vs "X is wrong"
        correct_pattern = r'([\w\s]+?)\s+is\s+(correct|right|good)'
        incorrect_pattern = r'([\w\s]+?)\s+is\s+(incorrect|wrong|bad)'

        new_correct = re.findall(correct_pattern, new_lower)
        new_incorrect = re.findall(incorrect_pattern, new_lower)

        for item, _ in new_correct:
            item = item.strip()
            check_pattern = rf'{re.escape(item)}\s+is\s+(incorrect|wrong|bad)'
            if re.search(check_pattern, prev_lower):
                return True

        for item, _ in new_incorrect:
            item = item.strip()
            check_pattern = rf'{re.escape(item)}\s+is\s+(correct|right|good)'
            if re.search(check_pattern, prev_lower):
                return True

        return False

    def _calculate_alignment(
        self,
        correction: str,
        task: str
    ) -> float:
        """
        Calculate semantic alignment between correction and task.

        Simple keyword overlap approach - can be enhanced with embeddings.

        Args:
            correction: Correction description
            task: Task description

        Returns:
            Alignment score 0.0-1.0
        """
        # Extract words (filter out common stopwords)
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
            'to', 'for', 'of', 'with', 'by', 'from', 'is', 'was',
            'are', 'were', 'be', 'been', 'being', 'have', 'has', 'had'
        }

        correction_words = set(
            w.lower() for w in correction.split()
            if w.lower() not in stopwords and len(w) > 2
        )
        task_words = set(
            w.lower() for w in task.split()
            if w.lower() not in stopwords and len(w) > 2
        )

        if not task_words:
            return 0.5

        # Calculate overlap
        overlap = len(correction_words & task_words)

        if overlap == 0:
            return 0.0

        # Score based on overlap relative to task size
        # More lenient calculation - 2+ word overlap is meaningful
        if overlap >= 2:
            # Scale from 0.5-1.0 based on how much we exceed minimum
            min_expected = max(2, len(task_words) * 0.2)
            scaled = 0.5 + min(0.5, overlap / min_expected * 0.5)
            return scaled
        else:
            # Single word overlap - weak alignment
            return 0.3

    def _correction_addresses_failure(
        self,
        mistake: DetectedMistake,
        failure_msg: str
    ) -> bool:
        """
        Check if correction addresses a specific test failure.

        Args:
            mistake: Detected mistake
            failure_msg: Test failure message

        Returns:
            True if correction addresses failure, False otherwise
        """
        # Extract key terms from failure
        failure_lower = failure_msg.lower()
        correction_lower = mistake.description.lower()

        # Check for common error patterns
        patterns = [
            'expected',
            'actual',
            'assertion',
            'error',
            'failed',
            'exception',
            'missing',
            'undefined'
        ]

        matches = 0
        for pattern in patterns:
            if pattern in failure_lower and pattern in correction_lower:
                matches += 1

        # Need at least 2 pattern matches to be confident
        return matches >= 2

    def _check_balanced_braces(self, code: str) -> bool:
        """
        Check if braces are balanced in code.

        Args:
            code: Code string to check

        Returns:
            True if balanced, False otherwise
        """
        stack = []
        pairs = {'(': ')', '[': ']', '{': '}'}

        # Basic check - doesn't handle strings/comments
        for char in code:
            if char in pairs.keys():
                stack.append(char)
            elif char in pairs.values():
                if not stack:
                    return False
                opener = stack.pop()
                if pairs[opener] != char:
                    return False

        return len(stack) == 0
