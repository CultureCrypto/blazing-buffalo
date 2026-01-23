"""
Tests for Circuit Breaker.

Validates three-state circuit breaker pattern for playbook reliability.
"""

import pytest
import time
from datetime import datetime, timedelta, timezone
from lib.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    CircuitStats
)


class TestCircuitBreakerStates:
    """Test circuit state transitions."""

    def test_initial_state_is_closed(self):
        """New circuits start in CLOSED state."""
        breaker = CircuitBreaker()
        assert breaker.get_state("playbook_1") == CircuitState.CLOSED

    def test_can_execute_when_closed(self):
        """Executions allowed in CLOSED state."""
        breaker = CircuitBreaker()
        assert breaker.can_execute("playbook_1") is True

    def test_transitions_to_open_after_threshold_failures(self):
        """Circuit opens after failure threshold reached."""
        breaker = CircuitBreaker(failure_threshold=3)

        # Record 3 failures
        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=False)

        assert breaker.get_state("playbook_1") == CircuitState.OPEN

    def test_cannot_execute_when_open(self):
        """Executions blocked in OPEN state."""
        breaker = CircuitBreaker(failure_threshold=2)

        # Open the circuit
        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=False)

        assert breaker.can_execute("playbook_1") is False

    def test_transitions_to_half_open_after_timeout(self):
        """Circuit moves to HALF_OPEN after recovery timeout."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # Open the circuit
        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=False)
        assert breaker.get_state("playbook_1") == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(1.1)

        # Should allow execution and transition to half-open
        assert breaker.can_execute("playbook_1") is True
        assert breaker.get_state("playbook_1") == CircuitState.HALF_OPEN

    def test_half_open_closes_after_success_threshold(self):
        """Circuit closes after success threshold in HALF_OPEN."""
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=1,
            success_threshold=2
        )

        # Open the circuit
        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=False)

        # Wait and transition to half-open
        time.sleep(1.1)
        breaker.can_execute("playbook_1")

        # Record successes
        breaker.record_result("playbook_1", success=True)
        assert breaker.get_state("playbook_1") == CircuitState.HALF_OPEN
        breaker.record_result("playbook_1", success=True)
        assert breaker.get_state("playbook_1") == CircuitState.CLOSED

    def test_half_open_reopens_on_failure(self):
        """Circuit reopens on failure in HALF_OPEN."""
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=1)

        # Open the circuit
        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=False)

        # Wait and transition to half-open
        time.sleep(1.1)
        breaker.can_execute("playbook_1")
        assert breaker.get_state("playbook_1") == CircuitState.HALF_OPEN

        # Fail in half-open
        breaker.record_result("playbook_1", success=False)
        assert breaker.get_state("playbook_1") == CircuitState.OPEN


class TestCircuitBreakerStats:
    """Test circuit statistics tracking."""

    def test_tracks_success_count(self):
        """Success count increments correctly."""
        breaker = CircuitBreaker()
        breaker.record_result("playbook_1", success=True)
        breaker.record_result("playbook_1", success=True)

        stats = breaker.get_stats("playbook_1")
        assert stats.success_count == 2

    def test_tracks_failure_count(self):
        """Failure count increments correctly."""
        breaker = CircuitBreaker()
        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=False)

        stats = breaker.get_stats("playbook_1")
        assert stats.failure_count == 2

    def test_tracks_last_failure_time(self):
        """Last failure timestamp recorded."""
        breaker = CircuitBreaker()
        before = datetime.now(timezone.utc)
        breaker.record_result("playbook_1", success=False)
        after = datetime.now(timezone.utc)

        stats = breaker.get_stats("playbook_1")
        assert stats.last_failure is not None
        assert before <= stats.last_failure <= after

    def test_tracks_last_success_time(self):
        """Last success timestamp recorded."""
        breaker = CircuitBreaker()
        before = datetime.now(timezone.utc)
        breaker.record_result("playbook_1", success=True)
        after = datetime.now(timezone.utc)

        stats = breaker.get_stats("playbook_1")
        assert stats.last_success is not None
        assert before <= stats.last_success <= after

    def test_resets_failure_count_on_close(self):
        """Failure count resets when circuit closes."""
        breaker = CircuitBreaker(
            failure_threshold=2,
            recovery_timeout=1,
            success_threshold=2
        )

        # Open circuit
        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=False)

        # Close circuit through half-open
        time.sleep(1.1)
        breaker.can_execute("playbook_1")
        breaker.record_result("playbook_1", success=True)
        breaker.record_result("playbook_1", success=True)

        stats = breaker.get_stats("playbook_1")
        assert stats.failure_count == 0


class TestCircuitBreakerConfiguration:
    """Test circuit configuration options."""

    def test_custom_failure_threshold(self):
        """Custom failure threshold works."""
        breaker = CircuitBreaker(failure_threshold=5)

        # 4 failures should not open
        for _ in range(4):
            breaker.record_result("playbook_1", success=False)
        assert breaker.get_state("playbook_1") == CircuitState.CLOSED

        # 5th failure opens
        breaker.record_result("playbook_1", success=False)
        assert breaker.get_state("playbook_1") == CircuitState.OPEN

    def test_custom_recovery_timeout(self):
        """Custom recovery timeout works."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=2)

        # Open circuit
        breaker.record_result("playbook_1", success=False)

        # Before timeout
        time.sleep(1)
        assert breaker.can_execute("playbook_1") is False

        # After timeout
        time.sleep(1.1)
        assert breaker.can_execute("playbook_1") is True

    def test_custom_success_threshold(self):
        """Custom success threshold works."""
        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=1,
            success_threshold=3
        )

        # Open and transition to half-open
        breaker.record_result("playbook_1", success=False)
        time.sleep(1.1)
        breaker.can_execute("playbook_1")

        # Need 3 successes to close
        breaker.record_result("playbook_1", success=True)
        assert breaker.get_state("playbook_1") == CircuitState.HALF_OPEN
        breaker.record_result("playbook_1", success=True)
        assert breaker.get_state("playbook_1") == CircuitState.HALF_OPEN
        breaker.record_result("playbook_1", success=True)
        assert breaker.get_state("playbook_1") == CircuitState.CLOSED


class TestCircuitBreakerIsolation:
    """Test isolation between circuits."""

    def test_independent_circuits(self):
        """Each playbook has independent circuit."""
        breaker = CircuitBreaker(failure_threshold=2)

        # Fail playbook_1
        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=False)

        # playbook_1 open, playbook_2 closed
        assert breaker.get_state("playbook_1") == CircuitState.OPEN
        assert breaker.get_state("playbook_2") == CircuitState.CLOSED
        assert breaker.can_execute("playbook_1") is False
        assert breaker.can_execute("playbook_2") is True

    def test_independent_stats(self):
        """Each playbook has independent stats."""
        breaker = CircuitBreaker()

        breaker.record_result("playbook_1", success=True)
        breaker.record_result("playbook_2", success=False)

        stats_1 = breaker.get_stats("playbook_1")
        stats_2 = breaker.get_stats("playbook_2")

        assert stats_1.success_count == 1
        assert stats_1.failure_count == 0
        assert stats_2.success_count == 0
        assert stats_2.failure_count == 1


class TestCircuitBreakerReset:
    """Test manual circuit reset."""

    def test_reset_closes_circuit(self):
        """Reset transitions circuit to CLOSED."""
        breaker = CircuitBreaker(failure_threshold=2)

        # Open circuit
        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=False)
        assert breaker.get_state("playbook_1") == CircuitState.OPEN

        # Reset
        breaker.reset("playbook_1")
        assert breaker.get_state("playbook_1") == CircuitState.CLOSED

    def test_reset_clears_stats(self):
        """Reset clears statistics."""
        breaker = CircuitBreaker()

        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=True)

        breaker.reset("playbook_1")
        stats = breaker.get_stats("playbook_1")

        assert stats.success_count == 0
        assert stats.failure_count == 0
        assert stats.last_failure is None
        assert stats.last_success is None


class TestCircuitBreakerBulkOperations:
    """Test bulk query operations."""

    def test_get_all_states(self):
        """Get all circuit states."""
        breaker = CircuitBreaker(failure_threshold=1)

        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_2", success=False)

        states = breaker.get_all_states()
        assert states["playbook_1"] == CircuitState.OPEN
        assert states["playbook_2"] == CircuitState.OPEN

    def test_get_open_circuits(self):
        """Get list of open circuits."""
        breaker = CircuitBreaker(failure_threshold=1)

        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_2", success=False)
        breaker.record_result("playbook_3", success=True)

        open_circuits = breaker.get_open_circuits()
        assert set(open_circuits) == {"playbook_1", "playbook_2"}
        assert "playbook_3" not in open_circuits


class TestCircuitBreakerAlerts:
    """Test alert emission."""

    def test_alert_on_circuit_open(self, capsys):
        """Alert emitted when circuit opens."""
        breaker = CircuitBreaker(failure_threshold=2)

        breaker.record_result("playbook_1", success=False)
        breaker.record_result("playbook_1", success=False)

        captured = capsys.readouterr()
        assert "ALERT: Circuit opened for playbook playbook_1" in captured.out
        assert "Failures: 2" in captured.out

    def test_no_alert_on_success(self, capsys):
        """No alert on successful execution."""
        breaker = CircuitBreaker()
        breaker.record_result("playbook_1", success=True)

        captured = capsys.readouterr()
        assert "ALERT" not in captured.out
