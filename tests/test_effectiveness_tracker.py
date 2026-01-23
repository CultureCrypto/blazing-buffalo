"""Tests for effectiveness tracker."""

import pytest
from pathlib import Path
import shutil
from lib.effectiveness_tracker import EffectivenessTracker, EffectivenessMetrics, ABTestResult


@pytest.fixture
def tracker(tmp_path):
    """Create tracker with temporary data directory."""
    original_dir = EffectivenessTracker.DATA_DIR
    EffectivenessTracker.DATA_DIR = tmp_path / "effectiveness"
    tracker = EffectivenessTracker()
    yield tracker
    EffectivenessTracker.DATA_DIR = original_dir


def test_record_execution_basic(tracker):
    """Test recording a basic execution."""
    tracker.record_execution(
        playbook_id="pb_001",
        project_type="fastapi",
        success=True,
        duration_ms=1500
    )

    assert len(tracker.executions) == 1
    assert tracker.executions[0]["playbook_id"] == "pb_001"
    assert tracker.executions[0]["success"] is True
    assert tracker.executions[0]["duration_ms"] == 1500


def test_record_execution_with_regression(tracker):
    """Test recording execution with regression flag."""
    tracker.record_execution(
        playbook_id="pb_002",
        project_type="django",
        success=True,
        duration_ms=2000,
        caused_regression=True
    )

    assert tracker.executions[0]["caused_regression"] is True


def test_record_execution_with_variant(tracker):
    """Test recording execution with A/B test variant."""
    tracker.record_execution(
        playbook_id="pb_003",
        project_type="flask",
        success=True,
        duration_ms=1200,
        variant="variant_a"
    )

    assert tracker.executions[0]["variant"] == "variant_a"


def test_metrics_calculation(tracker):
    """Test metrics calculation from executions."""
    # Record multiple executions
    for i in range(10):
        tracker.record_execution(
            playbook_id="pb_004",
            project_type="fastapi",
            success=i < 8,  # 80% success rate
            duration_ms=1000 + i * 100
        )

    metrics = tracker.get_metrics("pb_004", "fastapi")
    assert metrics.success_rate == 0.8
    assert metrics.avg_resolution_time_ms == 1450.0  # Average of 1000-1900
    assert metrics.sample_size == 10


def test_metrics_per_project_type(tracker):
    """Test metrics are tracked separately per project type."""
    # FastAPI executions - high success
    for i in range(5):
        tracker.record_execution("pb_005", "fastapi", success=True, duration_ms=1000)

    # Django executions - low success
    for i in range(5):
        tracker.record_execution("pb_005", "django", success=i < 2, duration_ms=2000)

    fastapi_metrics = tracker.get_metrics("pb_005", "fastapi")
    django_metrics = tracker.get_metrics("pb_005", "django")

    assert fastapi_metrics.success_rate == 1.0
    assert django_metrics.success_rate == 0.4
    assert fastapi_metrics.avg_resolution_time_ms == 1000
    assert django_metrics.avg_resolution_time_ms == 2000


def test_regression_rate_calculation(tracker):
    """Test regression rate calculation."""
    tracker.record_execution("pb_006", "fastapi", success=True, duration_ms=1000, caused_regression=True)
    tracker.record_execution("pb_006", "fastapi", success=True, duration_ms=1000, caused_regression=False)
    tracker.record_execution("pb_006", "fastapi", success=True, duration_ms=1000, caused_regression=True)
    tracker.record_execution("pb_006", "fastapi", success=True, duration_ms=1000, caused_regression=False)

    metrics = tracker.get_metrics("pb_006", "fastapi")
    assert metrics.regression_rate == 0.5  # 2 out of 4


def test_user_feedback_recording(tracker):
    """Test recording user satisfaction feedback."""
    tracker.record_execution("pb_007", "fastapi", success=True, duration_ms=1000)
    tracker.record_feedback("pb_007", "fastapi", satisfaction=0.9)
    tracker.record_feedback("pb_007", "fastapi", satisfaction=0.7)

    metrics = tracker.get_metrics("pb_007", "fastapi")
    assert metrics.user_satisfaction == 0.8  # Average of 0.9 and 0.7


def test_user_feedback_validation(tracker):
    """Test feedback validation."""
    tracker.record_execution("pb_008", "fastapi", success=True, duration_ms=1000)

    with pytest.raises(ValueError, match="Satisfaction must be between 0.0 and 1.0"):
        tracker.record_feedback("pb_008", "fastapi", satisfaction=1.5)

    with pytest.raises(ValueError, match="Satisfaction must be between 0.0 and 1.0"):
        tracker.record_feedback("pb_008", "fastapi", satisfaction=-0.1)


def test_aggregate_metrics(tracker):
    """Test aggregate metrics across project types."""
    # FastAPI: 100% success, 1000ms
    tracker.record_execution("pb_009", "fastapi", success=True, duration_ms=1000)
    tracker.record_execution("pb_009", "fastapi", success=True, duration_ms=1000)

    # Django: 50% success, 2000ms
    tracker.record_execution("pb_009", "django", success=True, duration_ms=2000)
    tracker.record_execution("pb_009", "django", success=False, duration_ms=2000)

    aggregate = tracker.get_metrics("pb_009")
    assert aggregate.success_rate == 0.75  # 3/4
    assert aggregate.avg_resolution_time_ms == 1500.0  # Weighted average
    assert aggregate.sample_size == 4


def test_start_ab_test(tracker):
    """Test starting an A/B test."""
    test_id = tracker.start_ab_test("pb_010", variant_a="approach_1", variant_b="approach_2")

    assert test_id.startswith("pb_010_ab_")
    test = tracker.get_ab_test_result(test_id)
    assert test is not None
    assert test.variant_a == "approach_1"
    assert test.variant_b == "approach_2"
    assert test.completed is False


def test_get_variant(tracker):
    """Test getting variant for A/B test."""
    test_id = tracker.start_ab_test("pb_011", variant_a="v1", variant_b="v2")

    variants = set()
    for _ in range(20):
        variant = tracker.get_variant(test_id)
        variants.add(variant)

    # Should get both variants over 20 calls
    assert "v1" in variants
    assert "v2" in variants


def test_ab_test_update(tracker):
    """Test A/B test updates with executions."""
    test_id = tracker.start_ab_test("pb_012", variant_a="v1", variant_b="v2")

    # Record successes for variant A
    for _ in range(15):
        tracker.record_execution("pb_012", "fastapi", success=True, duration_ms=1000, variant="v1")

    # Record mixed results for variant B
    for i in range(15):
        tracker.record_execution("pb_012", "fastapi", success=i < 8, duration_ms=1000, variant="v2")

    test = tracker.get_ab_test_result(test_id)
    assert test.sample_size_a == 15
    assert test.sample_size_b == 15


def test_ab_test_conclusion(tracker):
    """Test A/B test reaches conclusion with sufficient samples."""
    test_id = tracker.start_ab_test("pb_013", variant_a="v1", variant_b="v2")

    # Variant A: 95% success (19/20)
    for i in range(20):
        tracker.record_execution("pb_013", "fastapi", success=i < 19, duration_ms=1000, variant="v1")

    # Variant B: 50% success (10/20)
    for i in range(20):
        tracker.record_execution("pb_013", "fastapi", success=i < 10, duration_ms=1000, variant="v2")

    test = tracker.get_ab_test_result(test_id)
    assert test.completed is True
    assert test.winner == "v1"


def test_top_playbooks(tracker):
    """Test getting top playbooks for a project type."""
    # Create playbooks with different success rates
    for i in range(15):
        tracker.record_execution("pb_014", "fastapi", success=i < 14, duration_ms=1000)  # 93% success
    for i in range(15):
        tracker.record_execution("pb_015", "fastapi", success=i < 10, duration_ms=1000)  # 67% success
    for i in range(15):
        tracker.record_execution("pb_016", "fastapi", success=i < 12, duration_ms=1000)  # 80% success

    top = tracker.get_top_playbooks("fastapi", limit=2)
    assert len(top) == 2
    assert top[0]["playbook_id"] == "pb_014"  # Highest success rate
    assert top[0]["success_rate"] == pytest.approx(14/15)


def test_top_playbooks_excludes_small_samples(tracker):
    """Test top playbooks excludes entries with insufficient samples."""
    # Small sample size (below MIN_SAMPLE_SIZE)
    for i in range(5):
        tracker.record_execution("pb_017", "fastapi", success=True, duration_ms=1000)

    # Large sample size
    for i in range(15):
        tracker.record_execution("pb_018", "fastapi", success=i < 10, duration_ms=1000)

    top = tracker.get_top_playbooks("fastapi")
    assert len(top) == 1
    assert top[0]["playbook_id"] == "pb_018"


def test_top_playbooks_composite_score(tracker):
    """Test top playbooks uses composite score (success * (1-regression) * satisfaction)."""
    # High success, low regression, high satisfaction
    for i in range(15):
        tracker.record_execution("pb_019", "fastapi", success=True, duration_ms=1000, caused_regression=False)
    tracker.record_feedback("pb_019", "fastapi", satisfaction=0.95)

    # High success, high regression, high satisfaction
    for i in range(15):
        tracker.record_execution("pb_020", "fastapi", success=True, duration_ms=1000, caused_regression=i < 7)
    tracker.record_feedback("pb_020", "fastapi", satisfaction=0.95)

    top = tracker.get_top_playbooks("fastapi")
    assert top[0]["playbook_id"] == "pb_019"  # Better due to low regression


def test_persistence(tracker):
    """Test data persistence across instances."""
    tracker.record_execution("pb_021", "fastapi", success=True, duration_ms=1000)
    tracker.record_feedback("pb_021", "fastapi", satisfaction=0.85)
    test_id = tracker.start_ab_test("pb_021", variant_a="v1", variant_b="v2")

    # Create new instance with same data directory
    tracker2 = EffectivenessTracker()

    assert len(tracker2.executions) == 1
    assert "pb_021:fastapi" in tracker2.feedback
    assert test_id in tracker2.ab_tests


def test_empty_metrics(tracker):
    """Test getting metrics for non-existent playbook."""
    metrics = tracker.get_metrics("non_existent", "fastapi")
    assert metrics.success_rate == 0.0
    assert metrics.sample_size == 0


def test_completed_ab_test_returns_variant_a(tracker):
    """Test completed A/B test always returns variant A."""
    test_id = tracker.start_ab_test("pb_022", variant_a="v1", variant_b="v2")

    # Complete the test
    for i in range(20):
        tracker.record_execution("pb_022", "fastapi", success=True, duration_ms=1000, variant="v1")
    for i in range(20):
        tracker.record_execution("pb_022", "fastapi", success=True, duration_ms=1000, variant="v2")

    # After completion, should return variant_a
    variant = tracker.get_variant(test_id)
    assert variant == "v1"
