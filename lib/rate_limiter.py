"""
Rate Limiter for RCA Pipeline.

Implements multi-window rate limiting to prevent resource exhaustion.

Windows:
- Per-minute: 10 requests max
- Per-hour: 100 requests max
- Per-day: 500 requests max
- Concurrent: 3 parallel executions max

Features:
- Thread-safe using locks
- Automatic window cleanup
- Retry-after calculation
- Concurrent execution tracking
- Detailed status reporting
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime, timedelta, timezone
from collections import deque
import threading


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    per_minute: int = 10
    per_hour: int = 100
    per_day: int = 500
    max_concurrent: int = 3


@dataclass
class RateLimitStatus:
    """Status of a rate limit check."""
    allowed: bool
    remaining_minute: int
    remaining_hour: int
    remaining_day: int
    current_concurrent: int
    retry_after_seconds: Optional[int] = None
    reason: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class RateLimiter:
    """
    Rate limiter for RCA pipeline with multiple time windows.

    Provides burst protection (per-minute), sustained limits (per-hour),
    daily quotas (per-day), and concurrent execution caps.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        Initialize rate limiter.

        Args:
            config: Rate limit configuration. Defaults to RateLimitConfig().
        """
        self.config = config or RateLimitConfig()
        self.minute_window: deque = deque()
        self.hour_window: deque = deque()
        self.day_window: deque = deque()
        self.concurrent_count = 0
        self._lock = threading.Lock()

    def check(self) -> RateLimitStatus:
        """
        Check if a request is allowed under rate limits.

        Does NOT modify state - use acquire() to record a request.

        Returns:
            RateLimitStatus with allowed flag and remaining quotas.
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            self._cleanup_windows(now)

            # Check concurrent limit first (fastest check)
            if self.concurrent_count >= self.config.max_concurrent:
                return RateLimitStatus(
                    allowed=False,
                    remaining_minute=self.config.per_minute - len(self.minute_window),
                    remaining_hour=self.config.per_hour - len(self.hour_window),
                    remaining_day=self.config.per_day - len(self.day_window),
                    current_concurrent=self.concurrent_count,
                    reason="max_concurrent_reached",
                    retry_after_seconds=None
                )

            # Check per-minute window
            if len(self.minute_window) >= self.config.per_minute:
                oldest = self.minute_window[0]
                retry_after = self._calculate_retry_after(oldest, now, 60)
                return RateLimitStatus(
                    allowed=False,
                    remaining_minute=0,
                    remaining_hour=self.config.per_hour - len(self.hour_window),
                    remaining_day=self.config.per_day - len(self.day_window),
                    current_concurrent=self.concurrent_count,
                    retry_after_seconds=retry_after,
                    reason="per_minute_exceeded"
                )

            # Check per-hour window
            if len(self.hour_window) >= self.config.per_hour:
                oldest = self.hour_window[0]
                retry_after = self._calculate_retry_after(oldest, now, 3600)
                return RateLimitStatus(
                    allowed=False,
                    remaining_minute=self.config.per_minute - len(self.minute_window),
                    remaining_hour=0,
                    remaining_day=self.config.per_day - len(self.day_window),
                    current_concurrent=self.concurrent_count,
                    retry_after_seconds=retry_after,
                    reason="per_hour_exceeded"
                )

            # Check per-day window
            if len(self.day_window) >= self.config.per_day:
                oldest = self.day_window[0]
                retry_after = self._calculate_retry_after(oldest, now, 86400)
                return RateLimitStatus(
                    allowed=False,
                    remaining_minute=self.config.per_minute - len(self.minute_window),
                    remaining_hour=self.config.per_hour - len(self.hour_window),
                    remaining_day=0,
                    current_concurrent=self.concurrent_count,
                    retry_after_seconds=retry_after,
                    reason="per_day_exceeded"
                )

            # All limits permit the request
            return RateLimitStatus(
                allowed=True,
                remaining_minute=self.config.per_minute - len(self.minute_window) - 1,
                remaining_hour=self.config.per_hour - len(self.hour_window) - 1,
                remaining_day=self.config.per_day - len(self.day_window) - 1,
                current_concurrent=self.concurrent_count
            )

    def acquire(self) -> RateLimitStatus:
        """
        Attempt to acquire a rate limit slot.

        If allowed, increments counters and records request in time windows.
        Returns status with allowed flag and remaining quotas.

        Returns:
            RateLimitStatus with allowed flag. If True, caller should call
            release() when work completes to free the concurrent slot.
        """
        status = self.check()
        if status.allowed:
            with self._lock:
                now = datetime.now(timezone.utc)
                self.minute_window.append(now)
                self.hour_window.append(now)
                self.day_window.append(now)
                self.concurrent_count += 1
        return status

    def release(self) -> None:
        """
        Release a concurrent execution slot.

        Should be called when RCA execution completes (success or failure).
        Decrements concurrent counter to allow other requests through.
        """
        with self._lock:
            if self.concurrent_count > 0:
                self.concurrent_count -= 1

    def _cleanup_windows(self, now: datetime) -> None:
        """
        Remove expired entries from all time windows.

        Removes entries older than their respective window duration.
        Should be called under lock before checking limits.
        """
        minute_ago = now - timedelta(minutes=1)
        hour_ago = now - timedelta(hours=1)
        day_ago = now - timedelta(days=1)

        while self.minute_window and self.minute_window[0] < minute_ago:
            self.minute_window.popleft()

        while self.hour_window and self.hour_window[0] < hour_ago:
            self.hour_window.popleft()

        while self.day_window and self.day_window[0] < day_ago:
            self.day_window.popleft()

    @staticmethod
    def _calculate_retry_after(oldest_timestamp: datetime, now: datetime, window_seconds: int) -> int:
        """
        Calculate seconds until oldest request expires.

        Args:
            oldest_timestamp: Timestamp of oldest request in window
            now: Current timestamp
            window_seconds: Total window duration in seconds

        Returns:
            Seconds until oldest request expires (minimum 1).
        """
        elapsed = (now - oldest_timestamp).total_seconds()
        retry_after = max(1, window_seconds - int(elapsed))
        return retry_after

    def get_stats(self) -> Dict:
        """
        Get current rate limit statistics.

        Includes request counts in each window, concurrent usage, and
        configured limits.

        Returns:
            Dict with requests_last_minute, requests_last_hour,
            requests_last_day, concurrent_active, and limits.
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            self._cleanup_windows(now)
            return {
                "requests_last_minute": len(self.minute_window),
                "requests_last_hour": len(self.hour_window),
                "requests_last_day": len(self.day_window),
                "concurrent_active": self.concurrent_count,
                "limits": {
                    "per_minute": self.config.per_minute,
                    "per_hour": self.config.per_hour,
                    "per_day": self.config.per_day,
                    "max_concurrent": self.config.max_concurrent
                }
            }

    def reset(self) -> None:
        """Reset all counters and windows. Useful for testing."""
        with self._lock:
            self.minute_window.clear()
            self.hour_window.clear()
            self.day_window.clear()
            self.concurrent_count = 0
