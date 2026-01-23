"""
Shared types for Blazing Buffalo mistake detection system.

These types are used across the mistake detection and learning pipeline.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class DetectionMethod(Enum):
    """How the mistake was detected."""
    USER_CORRECTION = "user_correction"
    TOOL_FAILURE = "tool_failure"
    TEST_FAILURE = "test_failure"
    TYPE_ERROR = "type_error"
    LINT_ERROR = "lint_error"


class Severity(Enum):
    """Mistake severity classification."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DetectedMistake:
    """
    Detected mistake data structure.

    Attributes:
        id: Unique mistake ID (format: mst_<12hex>)
        category: Hierarchical category (e.g., 'tool_error.Bash')
        description: Human-readable description
        session_id: Claude session ID
        agent_id: Agent that made the mistake
        file_path: File where mistake occurred (if applicable)
        line_number: Line number (if applicable)
        detection_method: How it was detected
        severity: LOW, MEDIUM, HIGH, CRITICAL
        confidence: 0.0-1.0 confidence score
        timestamp: ISO 8601 timestamp
        context_hash: Hash of context for deduplication
        raw_signal: Original signal that triggered detection (truncated to 1000 chars)
    """
    id: str
    category: str
    description: str
    session_id: str
    agent_id: str
    file_path: Optional[str]
    line_number: Optional[int]
    detection_method: str
    severity: str
    confidence: float
    timestamp: str
    context_hash: str
    raw_signal: str


# Confidence thresholds by detection method
CONFIDENCE_THRESHOLDS = {
    DetectionMethod.USER_CORRECTION: 0.7,   # User corrections need at least 0.7
    DetectionMethod.TOOL_FAILURE: 1.0,      # Always 1.0 (concrete error)
    DetectionMethod.TEST_FAILURE: 1.0,      # Always 1.0 (test failed)
    DetectionMethod.TYPE_ERROR: 1.0,        # Always 1.0 (type checker said so)
    DetectionMethod.LINT_ERROR: 0.8,        # Errors 0.8, warnings 0.5
}


# Severity mappings
SEVERITY_BY_METHOD = {
    DetectionMethod.USER_CORRECTION: Severity.MEDIUM,
    DetectionMethod.TOOL_FAILURE: Severity.HIGH,
    DetectionMethod.TEST_FAILURE: Severity.HIGH,
    DetectionMethod.TYPE_ERROR: Severity.HIGH,
    DetectionMethod.LINT_ERROR: Severity.MEDIUM,  # Can be LOW for warnings
}
