"""
Comprehensive tests for RCA rate limiter.

Tests all rate limit windows, concurrent execution tracking, thread safety,
and retry-after calculations.
"""

import pytest
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

from lib.rate_limiter import RateLimiter, RateLimitConfig, RateLimitStatus


class TestRateLimiterBasics:
    """Basic rate limiter functionality tests."""

    def test_initialization_with_defaults(self):
        """Test rate limiter initializes with default config."""
        limiter = RateLimiter()
        assert limiter.config.per_minute == 10
        assert limiter.config.per_hour == 100
        assert limiter.config.per_day == 500
        assert limiter.config.max_concurrent == 3

    def test_initialization_with_custom_config(self):
        """Test rate limiter initializes with custom config."""
        config = RateLimitConfig(
            per_minute=5,
            per_hour=50,
            per_day=200,
            max_concurrent=2
        )
        limiter = RateLimiter(config)
        assert limiter.config.per_minute == 5
        assert limiter.config.per_hour == 50
        assert limiter.config.per_day == 200
        assert limiter.config.max_concurrent == 2

    def test_check_allowed_on_first_request(self):
        """Test that first request is always allowed."""
        limiter = RateLimiter()
        status = limiter.check()
        assert status.allowed is True
        assert status.reason is None
        assert status.retry_after_seconds is None

    def test_acquire_first_request(self):
        """Test acquiring first rate limit slot."""
        limiter = RateLimiter()
        status = limiter.acquire()
        assert status.allowed is True
        assert limiter.concurrent_count == 1
        assert len(limiter.minute_window) == 1
        assert len(limiter.hour_window) == 1
        assert len(limiter.day_window) == 1

    def test_check_does_not_modify_state(self):
        """Test that check() doesn't modify any state."""
        limiter = RateLimiter()
        initial_concurrent = limiter.concurrent_count
        initial_minute = len(limiter.minute_window)

        status = limiter.check()

        assert limiter.concurrent_count == initial_concurrent
        assert len(limiter.minute_window) == initial_minute
        assert status.allowed is True

    def test_release_decrements_concurrent(self):
        """Test that release() decrements concurrent counter."""
        limiter = RateLimiter()
        limiter.acquire()
        assert limiter.concurrent_count == 1

        limiter.release()
        assert limiter.concurrent_count == 0

    def test_release_does_not_go_negative(self):
        """Test that release() never goes negative."""
        limiter = RateLimiter()
        limiter.release()
        limiter.release()
        assert limiter.concurrent_count == 0


class TestPerMinuteLimit:
    """Per-minute rate limit tests."""

    def test_per_minute_allows_up_to_limit(self):
        """Test that per-minute limit allows N requests."""
        limiter = RateLimiter(RateLimitConfig(per_minute=3))
        for i in range(3):
            status = limiter.acquire()
            assert status.allowed is True, f"Request {i+1} should be allowed"

    def test_per_minute_blocks_over_limit(self):
        """Test that per-minute limit blocks request N+1."""
        limiter = RateLimiter(RateLimitConfig(per_minute=2))
        limiter.acquire()
        limiter.acquire()

        status = limiter.acquire()
        assert status.allowed is False
        assert status.reason == "per_minute_exceeded"
        assert status.remaining_minute == 0

    def test_per_minute_provides_retry_after(self):
        """Test that per-minute limit provides retry-after value."""
        limiter = RateLimiter(RateLimitConfig(per_minute=1))
        limiter.acquire()

        status = limiter.acquire()
        assert status.allowed is False
        assert status.retry_after_seconds is not None
        assert status.retry_after_seconds > 0
        assert status.retry_after_seconds <= 60

    def test_per_minute_remaining_calculation(self):
        """Test remaining_minute calculation."""
        limiter = RateLimiter(RateLimitConfig(per_minute=5))
        limiter.acquire()
        status = limiter.check()
        assert status.remaining_minute == 3  # 5 - 1 - 1

        limiter.acquire()
        status = limiter.check()
        assert status.remaining_minute == 2  # 5 - 2 - 1


class TestPerHourLimit:
    """Per-hour rate limit tests."""

    def test_per_hour_allows_within_minute_quota(self):
        """Test per-hour limit doesn't block when per-minute allows."""
        limiter = RateLimiter(
            RateLimitConfig(per_minute=100, per_hour=50, max_concurrent=100)
        )
        for i in range(50):
            status = limiter.acquire()
            assert status.allowed is True, f"Request {i+1} within per-hour should be allowed"

    def test_per_hour_blocks_over_limit(self):
        """Test that per-hour limit blocks request N+1."""
        limiter = RateLimiter(
            RateLimitConfig(per_minute=100, per_hour=2)
        )
        limiter.acquire()
        limiter.acquire()

        status = limiter.acquire()
        assert status.allowed is False
        assert status.reason == "per_hour_exceeded"
        assert status.remaining_hour == 0

    def test_per_hour_provides_retry_after(self):
        """Test that per-hour limit provides retry-after value."""
        limiter = RateLimiter(
            RateLimitConfig(per_minute=100, per_hour=1)
        )
        limiter.acquire()

        status = limiter.acquire()
        assert status.allowed is False
        assert status.retry_after_seconds is not None
        assert status.retry_after_seconds > 0
        assert status.retry_after_seconds <= 3600

    def test_per_hour_remaining_calculation(self):
        """Test remaining_hour calculation."""
        limiter = RateLimiter(
            RateLimitConfig(per_minute=100, per_hour=10)
        )
        limiter.acquire()
        status = limiter.check()
        assert status.remaining_hour == 8  # 10 - 1 - 1


class TestPerDayLimit:
    """Per-day rate limit tests."""

    def test_per_day_allows_within_hour_quota(self):
        """Test per-day limit doesn't block when per-hour allows."""
        limiter = RateLimiter(
            RateLimitConfig(per_minute=100, per_hour=100, per_day=50, max_concurrent=100)
        )
        for i in range(50):
            status = limiter.acquire()
            assert status.allowed is True, f"Request {i+1} within per-day should be allowed"

    def test_per_day_blocks_over_limit(self):
        """Test that per-day limit blocks request N+1."""
        limiter = RateLimiter(
            RateLimitConfig(per_minute=100, per_hour=100, per_day=2)
        )
        limiter.acquire()
        limiter.acquire()

        status = limiter.acquire()
        assert status.allowed is False
        assert status.reason == "per_day_exceeded"
        assert status.remaining_day == 0

    def test_per_day_provides_retry_after(self):
        """Test that per-day limit provides retry-after value."""
        limiter = RateLimiter(
            RateLimitConfig(per_minute=100, per_hour=100, per_day=1)
        )
        limiter.acquire()

        status = limiter.acquire()
        assert status.allowed is False
        assert status.retry_after_seconds is not None
        assert status.retry_after_seconds > 0
        assert status.retry_after_seconds <= 86400

    def test_per_day_remaining_calculation(self):
        """Test remaining_day calculation."""
        limiter = RateLimiter(
            RateLimitConfig(per_minute=100, per_hour=100, per_day=10)
        )
        limiter.acquire()
        status = limiter.check()
        assert status.remaining_day == 8  # 10 - 1 - 1


class TestConcurrentLimit:
    """Concurrent execution limit tests."""

    def test_concurrent_limit_reached(self):
        """Test that concurrent limit blocks further requests."""
        limiter = RateLimiter(RateLimitConfig(max_concurrent=2))
        limiter.acquire()
        limiter.acquire()

        status = limiter.acquire()
        assert status.allowed is False
        assert status.reason == "max_concurrent_reached"
        assert status.current_concurrent == 2

    def test_concurrent_limit_priority(self):
        """Test concurrent limit is checked before time windows."""
        limiter = RateLimiter(
            RateLimitConfig(
                per_minute=100,
                per_hour=100,
                per_day=100,
                max_concurrent=1
            )
        )
        limiter.acquire()

        # Second request fails on concurrent check before time window check
        status = limiter.acquire()
        assert status.allowed is False
        assert status.reason == "max_concurrent_reached"

    def test_concurrent_counter_increments_on_acquire(self):
        """Test concurrent counter increments with acquire()."""
        limiter = RateLimiter()
        assert limiter.concurrent_count == 0

        limiter.acquire()
        assert limiter.concurrent_count == 1

        limiter.acquire()
        assert limiter.concurrent_count == 2

        limiter.acquire()
        assert limiter.concurrent_count == 3

    def test_concurrent_counter_decrements_on_release(self):
        """Test concurrent counter decrements with release()."""
        limiter = RateLimiter()
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()
        assert limiter.concurrent_count == 3

        limiter.release()
        assert limiter.concurrent_count == 2

        limiter.release()
        assert limiter.concurrent_count == 1

        limiter.release()
        assert limiter.concurrent_count == 0

    def test_concurrent_available_after_release(self):
        """Test that releasing concurrent slot allows new requests."""
        limiter = RateLimiter(RateLimitConfig(max_concurrent=1))
        limiter.acquire()
        assert limiter.acquire().allowed is False

        limiter.release()
        assert limiter.acquire().allowed is True


class TestWindowCleanup:
    """Time window cleanup and expiration tests."""

    def test_minute_window_cleanup_removes_old_entries(self):
        """Test that old entries are removed from minute window."""
        limiter = RateLimiter()

        # Manually insert old entries
        old_time = datetime.now(timezone.utc) - timedelta(minutes=2)
        limiter.minute_window.append(old_time)
        limiter.hour_window.append(old_time)
        limiter.day_window.append(old_time)
        assert len(limiter.minute_window) == 1

        # Check should trigger cleanup
        limiter.check()
        assert len(limiter.minute_window) == 0
        # Hour and day windows should still have it (not expired yet)
        assert len(limiter.hour_window) == 1
        assert len(limiter.day_window) == 1

    def test_hour_window_cleanup_removes_old_entries(self):
        """Test that old entries are removed from hour window."""
        limiter = RateLimiter()

        # Manually insert old entries
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        limiter.minute_window.append(old_time)
        limiter.hour_window.append(old_time)
        limiter.day_window.append(old_time)
        assert len(limiter.hour_window) == 1

        limiter.check()
        # Minute should be cleared too
        assert len(limiter.minute_window) == 0
        # Hour should be cleared
        assert len(limiter.hour_window) == 0
        # Day should still have it
        assert len(limiter.day_window) == 1

    def test_day_window_cleanup_removes_old_entries(self):
        """Test that old entries are removed from day window."""
        limiter = RateLimiter()

        # Manually insert old entries
        old_time = datetime.now(timezone.utc) - timedelta(days=2)
        limiter.minute_window.append(old_time)
        limiter.hour_window.append(old_time)
        limiter.day_window.append(old_time)
        assert len(limiter.day_window) == 1

        limiter.check()
        # All should be cleared
        assert len(limiter.minute_window) == 0
        assert len(limiter.hour_window) == 0
        assert len(limiter.day_window) == 0


class TestRetryAfterCalculation:
    """Retry-after timing calculation tests."""

    def test_retry_after_near_window_end(self):
        """Test retry-after when request is near end of window."""
        limiter = RateLimiter(RateLimitConfig(per_minute=1))

        # Manually insert a request that's almost expired
        almost_expired = datetime.now(timezone.utc) - timedelta(seconds=55)
        limiter.minute_window.append(almost_expired)
        limiter.hour_window.append(almost_expired)
        limiter.day_window.append(almost_expired)

        status = limiter.check()
        assert status.retry_after_seconds is not None
        # Should be approximately 5 seconds (60 - 55)
        assert 4 <= status.retry_after_seconds <= 6

    def test_retry_after_near_window_start(self):
        """Test retry-after when request is near start of window."""
        limiter = RateLimiter(RateLimitConfig(per_minute=1))

        # Manually insert a request that's fresh
        almost_fresh = datetime.now(timezone.utc) - timedelta(seconds=2)
        limiter.minute_window.append(almost_fresh)
        limiter.hour_window.append(almost_fresh)
        limiter.day_window.append(almost_fresh)

        status = limiter.check()
        assert status.retry_after_seconds is not None
        # Should be approximately 58 seconds (60 - 2)
        assert 56 <= status.retry_after_seconds <= 60

    def test_retry_after_minimum_one_second(self):
        """Test that retry_after never goes below 1 second."""
        limiter = RateLimiter(RateLimitConfig(per_minute=1))

        # Manually insert a request that's almost fully expired
        almost_fully_expired = datetime.now(timezone.utc) - timedelta(seconds=59)
        limiter.minute_window.append(almost_fully_expired)
        limiter.hour_window.append(almost_fully_expired)
        limiter.day_window.append(almost_fully_expired)

        status = limiter.check()
        assert status.retry_after_seconds is not None
        # Should be at least 1
        assert status.retry_after_seconds >= 1


class TestStatistics:
    """Rate limit statistics reporting tests."""

    def test_get_stats_initial_state(self):
        """Test get_stats on fresh limiter."""
        limiter = RateLimiter()
        stats = limiter.get_stats()

        assert stats["requests_last_minute"] == 0
        assert stats["requests_last_hour"] == 0
        assert stats["requests_last_day"] == 0
        assert stats["concurrent_active"] == 0
        assert stats["limits"]["per_minute"] == 10
        assert stats["limits"]["per_hour"] == 100
        assert stats["limits"]["per_day"] == 500
        assert stats["limits"]["max_concurrent"] == 3

    def test_get_stats_after_requests(self):
        """Test get_stats reflects current request counts."""
        limiter = RateLimiter()
        limiter.acquire()
        limiter.acquire()

        stats = limiter.get_stats()
        assert stats["requests_last_minute"] == 2
        assert stats["requests_last_hour"] == 2
        assert stats["requests_last_day"] == 2
        assert stats["concurrent_active"] == 2

    def test_get_stats_after_release(self):
        """Test get_stats reflects concurrent count after release."""
        limiter = RateLimiter()
        limiter.acquire()
        limiter.acquire()
        limiter.release()

        stats = limiter.get_stats()
        assert stats["concurrent_active"] == 1
        # Windows still show 2 (not released from windows, only concurrent)
        assert stats["requests_last_minute"] == 2


class TestThreadSafety:
    """Thread safety and concurrent access tests."""

    def test_concurrent_acquire_calls(self):
        """Test multiple threads acquiring rate limits."""
        limiter = RateLimiter(RateLimitConfig(max_concurrent=10))
        results = []

        def acquire_slot():
            status = limiter.acquire()
            results.append(status.allowed)

        threads = [threading.Thread(target=acquire_slot) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 10 should succeed
        assert all(results)
        assert limiter.concurrent_count == 10

    def test_concurrent_acquire_release_calls(self):
        """Test multiple threads acquiring and releasing."""
        limiter = RateLimiter(
            RateLimitConfig(per_minute=100, per_hour=100, per_day=100, max_concurrent=2)
        )
        lock = threading.Lock()
        success_count = 0
        start_time = time.time()

        def work_and_release():
            nonlocal success_count
            # Retry logic for rate limited requests
            while time.time() - start_time < 2:  # 2 second timeout
                status = limiter.acquire()
                if status.allowed:
                    time.sleep(0.01)  # Simulate work
                    limiter.release()
                    with lock:
                        success_count += 1
                    return
                else:
                    time.sleep(0.01)  # Small backoff before retry

        threads = [threading.Thread(target=work_and_release) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 5 should eventually complete
        assert success_count == 5
        assert limiter.concurrent_count == 0

    def test_concurrent_check_calls(self):
        """Test multiple threads checking rate limits concurrently."""
        limiter = RateLimiter()
        results = []

        def check_status():
            status = limiter.check()
            results.append(status.allowed)

        threads = [threading.Thread(target=check_status) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All checks should succeed (doesn't modify state)
        assert all(results)
        # State should be unchanged
        assert limiter.concurrent_count == 0
        assert len(limiter.minute_window) == 0


class TestReset:
    """Reset functionality tests."""

    def test_reset_clears_all_windows(self):
        """Test reset clears all time windows."""
        limiter = RateLimiter()
        limiter.acquire()
        limiter.acquire()
        limiter.acquire()

        assert len(limiter.minute_window) == 3
        assert len(limiter.hour_window) == 3
        assert len(limiter.day_window) == 3

        limiter.reset()

        assert len(limiter.minute_window) == 0
        assert len(limiter.hour_window) == 0
        assert len(limiter.day_window) == 0
        assert limiter.concurrent_count == 0

    def test_reset_allows_subsequent_requests(self):
        """Test that reset allows requests after limit was hit."""
        limiter = RateLimiter(RateLimitConfig(per_minute=1))
        limiter.acquire()

        status = limiter.acquire()
        assert status.allowed is False

        limiter.reset()

        status = limiter.acquire()
        assert status.allowed is True


class TestRateLimitStatus:
    """RateLimitStatus dataclass tests."""

    def test_status_default_timestamp(self):
        """Test that status gets default timestamp."""
        status = RateLimitStatus(
            allowed=True,
            remaining_minute=5,
            remaining_hour=50,
            remaining_day=200,
            current_concurrent=1
        )
        assert status.timestamp is not None
        assert isinstance(status.timestamp, datetime)

    def test_status_with_retry_after(self):
        """Test status with retry_after value."""
        status = RateLimitStatus(
            allowed=False,
            remaining_minute=0,
            remaining_hour=50,
            remaining_day=200,
            current_concurrent=3,
            retry_after_seconds=30,
            reason="per_minute_exceeded"
        )
        assert status.retry_after_seconds == 30
        assert status.reason == "per_minute_exceeded"

    def test_status_string_representation(self):
        """Test that status has useful string representation."""
        status = RateLimitStatus(
            allowed=True,
            remaining_minute=5,
            remaining_hour=50,
            remaining_day=200,
            current_concurrent=1
        )
        status_str = str(status)
        assert "RateLimitStatus" in status_str


class TestEdgeCases:
    """Edge case and corner condition tests."""

    def test_zero_config_values(self):
        """Test limiter with zero limits (all requests blocked)."""
        limiter = RateLimiter(
            RateLimitConfig(
                per_minute=0,
                per_hour=0,
                per_day=0,
                max_concurrent=0
            )
        )
        status = limiter.acquire()
        assert status.allowed is False
        assert status.reason == "max_concurrent_reached"

    def test_very_large_config_values(self):
        """Test limiter with very large limits."""
        limiter = RateLimiter(
            RateLimitConfig(
                per_minute=10000,
                per_hour=100000,
                per_day=1000000,
                max_concurrent=1000
            )
        )
        status = limiter.acquire()
        assert status.allowed is True

    def test_multiple_acquire_and_release_cycles(self):
        """Test multiple cycles of acquire and release."""
        limiter = RateLimiter(RateLimitConfig(max_concurrent=2))

        for i in range(5):
            status = limiter.acquire()
            assert status.allowed is True
            status = limiter.acquire()
            assert status.allowed is True

            status = limiter.acquire()
            assert status.allowed is False

            limiter.release()
            limiter.release()

            assert limiter.concurrent_count == 0
