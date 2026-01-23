"""
Unit Tests for Prometheus Metrics Module.

Tests all metric types, decorators, and helper functions for the
Blazing Buffalo mistake learning system.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch
from prometheus_client import REGISTRY

# Import all metrics and helpers
from lib.metrics import (
    # Counters
    mistakes_detected_total,
    playbook_executions_total,
    playbook_steps_total,
    rca_analyses_total,
    rca_convergence_total,
    circuit_breaker_trips_total,
    taxonomy_cluster_assignments_total,

    # Histograms
    rca_latency_seconds,
    playbook_duration_seconds,
    playbook_step_duration_seconds,
    similar_mistake_search_latency_seconds,

    # Gauges
    circuit_breaker_state,
    active_playbook_executions,
    playbook_success_rate,
    playbook_error_budget_remaining,
    taxonomy_cluster_count,
    taxonomy_cluster_size,

    # Decorators
    track_rca_latency,
    track_playbook_execution,
    track_step_execution,

    # Helpers
    update_circuit_breaker_state,
    update_playbook_success_rate,
    update_error_budget,
    record_mistake_detection,
    record_rca_analysis,
    record_circuit_breaker_trip,
    update_taxonomy_metrics,
    metrics_endpoint,
    init_metrics,
)


@pytest.fixture
def reset_metrics():
    """Reset all metrics before each test."""
    # Note: This is a simplified reset - in production you'd use a separate registry
    yield
    # Metrics persist in the global registry, but that's OK for testing


class TestCounters:
    """Test counter metrics."""

    def test_mistakes_detected_counter(self):
        """Test mistake detection counter with labels."""
        before = mistakes_detected_total.labels(
            category="tool_misuse",
            severity="high",
            detection_method="pattern_match"
        )._value.get()

        record_mistake_detection(
            category="tool_misuse",
            severity="high",
            detection_method="pattern_match"
        )

        after = mistakes_detected_total.labels(
            category="tool_misuse",
            severity="high",
            detection_method="pattern_match"
        )._value.get()

        assert after == before + 1

    def test_playbook_execution_counter(self):
        """Test playbook execution counter."""
        before = playbook_executions_total.labels(
            playbook_id="fix-import",
            status="success"
        )._value.get()

        playbook_executions_total.labels(
            playbook_id="fix-import",
            status="success"
        ).inc()

        after = playbook_executions_total.labels(
            playbook_id="fix-import",
            status="success"
        )._value.get()

        assert after == before + 1

    def test_rca_analyses_counter(self):
        """Test RCA analyses counter."""
        before = rca_analyses_total.labels(
            root_cause_category="knowledge_gap",
            model="claude"
        )._value.get()

        record_rca_analysis(
            root_cause_category="knowledge_gap",
            model="claude",
            converged=True
        )

        after = rca_analyses_total.labels(
            root_cause_category="knowledge_gap",
            model="claude"
        )._value.get()

        assert after == before + 1

    def test_rca_convergence_counter(self):
        """Test RCA convergence tracking."""
        before_true = rca_convergence_total.labels(converged="true")._value.get()

        record_rca_analysis(
            root_cause_category="tool_misuse",
            model="gemini",
            converged=True
        )

        after_true = rca_convergence_total.labels(converged="true")._value.get()

        assert after_true == before_true + 1

    def test_circuit_breaker_trips_counter(self):
        """Test circuit breaker trip counter."""
        before = circuit_breaker_trips_total.labels(
            playbook_id="test-playbook",
            from_state="closed",
            to_state="open"
        )._value.get()

        record_circuit_breaker_trip(
            playbook_id="test-playbook",
            from_state="closed",
            to_state="open"
        )

        after = circuit_breaker_trips_total.labels(
            playbook_id="test-playbook",
            from_state="closed",
            to_state="open"
        )._value.get()

        assert after == before + 1


class TestHistograms:
    """Test histogram metrics."""

    def test_rca_latency_histogram(self):
        """Test RCA latency histogram observations."""
        # Get metric sample to check observations
        before = rca_latency_seconds.collect()[0].samples

        # Observe some latencies
        rca_latency_seconds.observe(1.5)
        rca_latency_seconds.observe(2.3)
        rca_latency_seconds.observe(0.8)

        # Check observations were recorded
        after = rca_latency_seconds.collect()[0].samples

        # Find the _sum sample
        sum_sample = [s for s in after if s.name.endswith('_sum')][0]
        assert sum_sample.value > 0

    def test_playbook_duration_histogram(self):
        """Test playbook duration histogram with labels."""
        playbook_duration_seconds.labels(playbook_id="test-pb").observe(5.2)

        # Check that observation was recorded
        samples = playbook_duration_seconds.collect()[0].samples
        sum_samples = [s for s in samples if s.name.endswith('_sum') and s.labels.get('playbook_id') == 'test-pb']
        assert len(sum_samples) > 0
        assert sum_samples[0].value >= 5.2

    def test_step_duration_histogram(self):
        """Test playbook step duration tracking."""
        playbook_step_duration_seconds.labels(
            step_type="Read",
            timeout_tier="instant"
        ).observe(0.3)

        samples = playbook_step_duration_seconds.collect()[0].samples
        sum_samples = [s for s in samples if s.name.endswith('_sum') and
                      s.labels.get('step_type') == 'Read' and
                      s.labels.get('timeout_tier') == 'instant']
        assert len(sum_samples) > 0
        assert sum_samples[0].value >= 0.3


class TestGauges:
    """Test gauge metrics."""

    def test_circuit_breaker_state_gauge(self):
        """Test circuit breaker state gauge."""
        update_circuit_breaker_state("test-pb", "closed")
        assert circuit_breaker_state.labels(playbook_id="test-pb")._value.get() == 0

        update_circuit_breaker_state("test-pb", "open")
        assert circuit_breaker_state.labels(playbook_id="test-pb")._value.get() == 1

        update_circuit_breaker_state("test-pb", "half_open")
        assert circuit_breaker_state.labels(playbook_id="test-pb")._value.get() == 2

    def test_active_playbook_executions_gauge(self):
        """Test active playbook executions gauge."""
        initial = active_playbook_executions._value.get()

        active_playbook_executions.inc()
        assert active_playbook_executions._value.get() == initial + 1

        active_playbook_executions.dec()
        assert active_playbook_executions._value.get() == initial

    def test_playbook_success_rate_gauge(self):
        """Test playbook success rate gauge."""
        update_playbook_success_rate("test-pb", 0.95)
        assert playbook_success_rate.labels(playbook_id="test-pb")._value.get() == 0.95

        update_playbook_success_rate("test-pb", 0.42)
        assert playbook_success_rate.labels(playbook_id="test-pb")._value.get() == 0.42

    def test_error_budget_gauge(self):
        """Test error budget gauge."""
        update_error_budget("test-pb", 1.0)
        assert playbook_error_budget_remaining.labels(playbook_id="test-pb")._value.get() == 1.0

        update_error_budget("test-pb", 0.25)
        assert playbook_error_budget_remaining.labels(playbook_id="test-pb")._value.get() == 0.25

    def test_taxonomy_cluster_count_gauge(self):
        """Test taxonomy cluster count gauge."""
        taxonomy_cluster_count.set(15)
        assert taxonomy_cluster_count._value.get() == 15

    def test_taxonomy_cluster_size_gauge(self):
        """Test taxonomy cluster size gauge with labels."""
        taxonomy_cluster_size.labels(cluster_label="tool_errors").set(42)
        assert taxonomy_cluster_size.labels(cluster_label="tool_errors")._value.get() == 42

    def test_update_taxonomy_metrics_helper(self):
        """Test taxonomy metrics update helper."""
        cluster_sizes = {
            "tool_errors": 25,
            "knowledge_gaps": 18,
            "pattern_violations": 7
        }

        update_taxonomy_metrics(3, cluster_sizes)

        assert taxonomy_cluster_count._value.get() == 3
        assert taxonomy_cluster_size.labels(cluster_label="tool_errors")._value.get() == 25
        assert taxonomy_cluster_size.labels(cluster_label="knowledge_gaps")._value.get() == 18


class TestDecorators:
    """Test metric decorators."""

    @pytest.mark.asyncio
    async def test_track_rca_latency_decorator_async(self):
        """Test RCA latency tracking decorator on async function."""
        before_samples = rca_latency_seconds.collect()[0].samples
        before_count_samples = [s for s in before_samples if s.name.endswith('_count')]
        before_count = before_count_samples[0].value if before_count_samples else 0

        @track_rca_latency
        async def mock_rca():
            await asyncio.sleep(0.1)
            return "analysis_complete"

        result = await mock_rca()
        assert result == "analysis_complete"

        after_samples = rca_latency_seconds.collect()[0].samples
        after_count_samples = [s for s in after_samples if s.name.endswith('_count')]
        after_count = after_count_samples[0].value if after_count_samples else 0
        assert after_count == before_count + 1

    def test_track_rca_latency_decorator_sync(self):
        """Test RCA latency tracking decorator on sync function."""
        before_samples = rca_latency_seconds.collect()[0].samples
        before_count_samples = [s for s in before_samples if s.name.endswith('_count')]
        before_count = before_count_samples[0].value if before_count_samples else 0

        @track_rca_latency
        def mock_rca_sync():
            time.sleep(0.05)
            return "done"

        result = mock_rca_sync()
        assert result == "done"

        after_samples = rca_latency_seconds.collect()[0].samples
        after_count_samples = [s for s in after_samples if s.name.endswith('_count')]
        after_count = after_count_samples[0].value if after_count_samples else 0
        assert after_count == before_count + 1

    @pytest.mark.asyncio
    async def test_track_playbook_execution_success(self):
        """Test playbook execution decorator on success."""
        before_active = active_playbook_executions._value.get()
        before_total = playbook_executions_total.labels(
            playbook_id="test-pb",
            status="success"
        )._value.get()

        @track_playbook_execution("test-pb")
        async def mock_execute():
            await asyncio.sleep(0.05)
            # Return object with status attribute
            result = Mock()
            result.status = "success"
            return result

        result = await mock_execute()
        assert result.status == "success"

        # Active should return to initial
        assert active_playbook_executions._value.get() == before_active

        # Total should increment
        after_total = playbook_executions_total.labels(
            playbook_id="test-pb",
            status="success"
        )._value.get()
        assert after_total == before_total + 1

    @pytest.mark.asyncio
    async def test_track_playbook_execution_failure(self):
        """Test playbook execution decorator on failure."""
        before_total = playbook_executions_total.labels(
            playbook_id="fail-pb",
            status="failed"
        )._value.get()

        @track_playbook_execution("fail-pb")
        async def mock_execute_fail():
            await asyncio.sleep(0.05)
            raise ValueError("Simulated failure")

        with pytest.raises(ValueError, match="Simulated failure"):
            await mock_execute_fail()

        # Failed status should increment
        after_total = playbook_executions_total.labels(
            playbook_id="fail-pb",
            status="failed"
        )._value.get()
        assert after_total == before_total + 1

    @pytest.mark.asyncio
    async def test_track_playbook_execution_timeout(self):
        """Test playbook execution decorator on timeout."""
        before_total = playbook_executions_total.labels(
            playbook_id="timeout-pb",
            status="timeout"
        )._value.get()

        @track_playbook_execution("timeout-pb")
        async def mock_execute_timeout():
            await asyncio.sleep(0.05)
            raise asyncio.TimeoutError("Execution timed out")

        with pytest.raises(asyncio.TimeoutError):
            await mock_execute_timeout()

        # Timeout status should increment
        after_total = playbook_executions_total.labels(
            playbook_id="timeout-pb",
            status="timeout"
        )._value.get()
        assert after_total == before_total + 1

    @pytest.mark.asyncio
    async def test_track_step_execution_decorator(self):
        """Test step execution decorator."""
        before_samples = playbook_step_duration_seconds.collect()[0].samples
        before_count_samples = [s for s in before_samples if s.name.endswith('_count') and
                               s.labels.get('step_type') == 'Read' and
                               s.labels.get('timeout_tier') == 'instant']
        before_count = before_count_samples[0].value if before_count_samples else 0

        @track_step_execution("Read", "instant")
        async def mock_read_step(playbook_id="test"):
            await asyncio.sleep(0.02)
            return "file_contents"

        result = await mock_read_step(playbook_id="test-pb")
        assert result == "file_contents"

        after_samples = playbook_step_duration_seconds.collect()[0].samples
        after_count_samples = [s for s in after_samples if s.name.endswith('_count') and
                              s.labels.get('step_type') == 'Read' and
                              s.labels.get('timeout_tier') == 'instant']
        after_count = after_count_samples[0].value if after_count_samples else 0
        assert after_count == before_count + 1


class TestHelpers:
    """Test helper functions."""

    def test_record_mistake_detection(self):
        """Test mistake detection recording helper."""
        before = mistakes_detected_total.labels(
            category="edge_case",
            severity="medium",
            detection_method="manual"
        )._value.get()

        record_mistake_detection(
            category="edge_case",
            severity="medium",
            detection_method="manual"
        )

        after = mistakes_detected_total.labels(
            category="edge_case",
            severity="medium",
            detection_method="manual"
        )._value.get()

        assert after == before + 1

    def test_record_rca_analysis_convergence(self):
        """Test RCA analysis recording with convergence."""
        before_analyses = rca_analyses_total.labels(
            root_cause_category="context_missing",
            model="glm"
        )._value.get()

        before_convergence = rca_convergence_total.labels(
            converged="false"
        )._value.get()

        record_rca_analysis(
            root_cause_category="context_missing",
            model="glm",
            converged=False
        )

        after_analyses = rca_analyses_total.labels(
            root_cause_category="context_missing",
            model="glm"
        )._value.get()

        after_convergence = rca_convergence_total.labels(
            converged="false"
        )._value.get()

        assert after_analyses == before_analyses + 1
        assert after_convergence == before_convergence + 1

    def test_record_circuit_breaker_trip(self):
        """Test circuit breaker trip recording."""
        playbook_id = "cb-test-pb"

        # Initial state should be set
        record_circuit_breaker_trip(playbook_id, "closed", "open")

        # State gauge should update
        assert circuit_breaker_state.labels(playbook_id=playbook_id)._value.get() == 1

        # Counter should increment
        trips = circuit_breaker_trips_total.labels(
            playbook_id=playbook_id,
            from_state="closed",
            to_state="open"
        )._value.get()
        assert trips >= 1


class TestMetricsEndpoint:
    """Test metrics endpoint functionality."""

    def test_metrics_endpoint_returns_bytes(self):
        """Test that metrics endpoint returns bytes."""
        result = metrics_endpoint()
        assert isinstance(result, bytes)

    def test_metrics_endpoint_contains_metrics(self):
        """Test that metrics endpoint contains expected metrics."""
        # Record some test metrics
        record_mistake_detection("test", "low", "test")
        playbook_executions_total.labels(playbook_id="test", status="success").inc()

        result = metrics_endpoint()
        text = result.decode('utf-8')

        # Should contain metric names
        assert "blazing_buffalo_mistakes_detected_total" in text
        assert "blazing_buffalo_playbook_executions_total" in text

    def test_metrics_endpoint_prometheus_format(self):
        """Test that metrics are in valid Prometheus format."""
        result = metrics_endpoint()
        text = result.decode('utf-8')

        # Should have TYPE and HELP lines
        assert "# TYPE" in text
        assert "# HELP" in text

        # Should have metric lines with values
        lines = [line for line in text.split('\n') if line and not line.startswith('#')]
        assert len(lines) > 0


class TestInitialization:
    """Test metrics initialization."""

    def test_init_metrics_sets_system_info(self):
        """Test that init_metrics sets system info."""
        init_metrics(version="2.0.0", environment="testing")

        # System info should be set (check via metrics endpoint)
        result = metrics_endpoint()
        text = result.decode('utf-8')

        assert "blazing_buffalo_system_info" in text
        assert "version=\"2.0.0\"" in text
        assert "environment=\"testing\"" in text

    def test_init_metrics_resets_active_executions(self):
        """Test that init_metrics resets active executions gauge."""
        # Set to some value
        active_playbook_executions.set(5)

        # Initialize
        init_metrics()

        # Should be reset to 0
        assert active_playbook_executions._value.get() == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
