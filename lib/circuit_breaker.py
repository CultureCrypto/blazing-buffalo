"""
Circuit Breaker for Playbook Reliability.

Implements three-state circuit breaker pattern to prevent cascading failures
from faulty playbooks.

States:
- CLOSED: Normal operation, executions allowed
- OPEN: Too many failures, block executions
- HALF_OPEN: Testing if system recovered

Features:
- Configurable failure thresholds
- Automatic recovery timeout
- Thread-safe state management
- Alert emission on circuit open
- Per-playbook circuit tracking
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from enum import Enum
from datetime import datetime, timedelta, timezone
import threading


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Blocking executions
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class CircuitStats:
    """Statistics for a circuit."""
    success_count: int = 0
    failure_count: int = 0
    last_failure: Optional[datetime] = None
    last_success: Optional[datetime] = None
    state_changed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CircuitBreaker:
    """
    Three-state circuit breaker for playbook execution reliability.

    States:
    - CLOSED: Normal operation, executions allowed
    - OPEN: Too many failures, block executions
    - HALF_OPEN: Testing if system recovered

    Example:
        breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=300)

        if breaker.can_execute("playbook_123"):
            result = execute_playbook("playbook_123")
            breaker.record_result("playbook_123", success=result.success)
        else:
            print("Circuit is open, execution blocked")
    """

    DEFAULT_FAILURE_THRESHOLD = 3
    DEFAULT_RECOVERY_TIMEOUT = 300  # 5 minutes
    DEFAULT_SUCCESS_THRESHOLD = 2   # Successes needed in half-open

    def __init__(self, failure_threshold: int = None,
                 recovery_timeout: int = None,
                 success_threshold: int = None):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before testing recovery
            success_threshold: Successes needed in half-open to close
        """
        self.failure_threshold = failure_threshold or self.DEFAULT_FAILURE_THRESHOLD
        self.recovery_timeout = recovery_timeout or self.DEFAULT_RECOVERY_TIMEOUT
        self.success_threshold = success_threshold or self.DEFAULT_SUCCESS_THRESHOLD
        self.circuits: Dict[str, CircuitState] = {}
        self.stats: Dict[str, CircuitStats] = {}
        self._lock = threading.Lock()

    def can_execute(self, playbook_id: str) -> bool:
        """
        Check if playbook execution is allowed.

        Args:
            playbook_id: Unique playbook identifier

        Returns:
            True if execution allowed, False otherwise
        """
        with self._lock:
            state = self.circuits.get(playbook_id, CircuitState.CLOSED)

            if state == CircuitState.CLOSED:
                return True

            if state == CircuitState.OPEN:
                # Check if recovery timeout elapsed
                stats = self.stats.get(playbook_id, CircuitStats())
                elapsed = datetime.now(timezone.utc) - stats.state_changed_at
                if elapsed.total_seconds() >= self.recovery_timeout:
                    self._transition(playbook_id, CircuitState.HALF_OPEN)
                    return True
                return False

            if state == CircuitState.HALF_OPEN:
                return True  # Allow test execution

            return False

    def record_result(self, playbook_id: str, success: bool) -> None:
        """
        Record execution result and update circuit state.

        Args:
            playbook_id: Unique playbook identifier
            success: Whether execution succeeded
        """
        with self._lock:
            if playbook_id not in self.stats:
                self.stats[playbook_id] = CircuitStats()

            stats = self.stats[playbook_id]
            state = self.circuits.get(playbook_id, CircuitState.CLOSED)

            if success:
                stats.success_count += 1
                stats.last_success = datetime.now(timezone.utc)

                if state == CircuitState.HALF_OPEN:
                    if stats.success_count >= self.success_threshold:
                        self._transition(playbook_id, CircuitState.CLOSED)
                        stats.failure_count = 0
            else:
                stats.failure_count += 1
                stats.last_failure = datetime.now(timezone.utc)

                if state == CircuitState.HALF_OPEN:
                    # Failed in half-open, go back to open
                    self._transition(playbook_id, CircuitState.OPEN)
                elif state == CircuitState.CLOSED and stats.failure_count >= self.failure_threshold:
                    # Too many failures, open circuit
                    self._transition(playbook_id, CircuitState.OPEN)
                    self._emit_alert(playbook_id)

    def _transition(self, playbook_id: str, new_state: CircuitState) -> None:
        """
        Transition circuit to new state.

        Args:
            playbook_id: Unique playbook identifier
            new_state: New circuit state
        """
        old_state = self.circuits.get(playbook_id, CircuitState.CLOSED)
        self.circuits[playbook_id] = new_state
        self.stats[playbook_id].state_changed_at = datetime.now(timezone.utc)

        # Reset success counter on state change to half-open
        if new_state == CircuitState.HALF_OPEN:
            self.stats[playbook_id].success_count = 0

    def _emit_alert(self, playbook_id: str) -> None:
        """
        Emit alert when circuit opens.

        Args:
            playbook_id: Unique playbook identifier
        """
        stats = self.stats[playbook_id]
        print(f"ALERT: Circuit opened for playbook {playbook_id}")
        print(f"  Failures: {stats.failure_count}")
        print(f"  Last failure: {stats.last_failure}")
        print(f"  Recovery in {self.recovery_timeout}s")

    def get_state(self, playbook_id: str) -> CircuitState:
        """
        Get current circuit state.

        Args:
            playbook_id: Unique playbook identifier

        Returns:
            Current circuit state
        """
        return self.circuits.get(playbook_id, CircuitState.CLOSED)

    def get_stats(self, playbook_id: str) -> CircuitStats:
        """
        Get circuit statistics.

        Args:
            playbook_id: Unique playbook identifier

        Returns:
            Circuit statistics
        """
        return self.stats.get(playbook_id, CircuitStats())

    def reset(self, playbook_id: str) -> None:
        """
        Manually reset a circuit.

        Args:
            playbook_id: Unique playbook identifier
        """
        with self._lock:
            self.circuits[playbook_id] = CircuitState.CLOSED
            self.stats[playbook_id] = CircuitStats()

    def get_all_states(self) -> Dict[str, CircuitState]:
        """
        Get states of all circuits.

        Returns:
            Dictionary mapping playbook IDs to states
        """
        with self._lock:
            return self.circuits.copy()

    def get_open_circuits(self) -> list[str]:
        """
        Get list of playbook IDs with open circuits.

        Returns:
            List of playbook IDs
        """
        with self._lock:
            return [
                playbook_id
                for playbook_id, state in self.circuits.items()
                if state == CircuitState.OPEN
            ]
