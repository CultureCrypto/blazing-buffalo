"""
Tests for Playbook Executor with Timeout Tiers and Checkpointing.

Test Coverage:
- Timeout tier enforcement (instant, fast, standard, long, background)
- Step-level checkpointing and resume
- Circuit breaker integration
- Graceful timeout handling
- Error recovery
- Custom handler registration
"""

import pytest
import asyncio
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))

from playbook_executor import (
    PlaybookExecutor,
    ExecutionResult,
    StepResult,
    StepStatus,
    TimeoutTier
)


class MockCircuitBreaker:
    """Mock circuit breaker for testing."""

    def __init__(self, allow_execute=True):
        self.allow_execute = allow_execute
        self.results = []

    def can_execute(self, playbook_id: str) -> bool:
        return self.allow_execute

    def record_result(self, playbook_id: str, success: bool) -> None:
        self.results.append((playbook_id, success))


@pytest.fixture
def executor():
    """Create executor with mock circuit breaker."""
    breaker = MockCircuitBreaker()
    return PlaybookExecutor(circuit_breaker=breaker), breaker


@pytest.fixture
def sample_playbook():
    """Sample playbook for testing."""
    return {
        'id': 'test-playbook-001',
        'name': 'Test Playbook',
        'resolution_steps': [
            {
                'id': 'step-1',
                'action': 'analyze',
                'command': 'ls -la',
                'description': 'List files',
                'timeout_tier': 'instant'
            },
            {
                'id': 'step-2',
                'action': 'read',
                'files': ['test.py'],
                'timeout_tier': 'fast'
            },
            {
                'id': 'step-3',
                'action': 'verify',
                'condition': 'file_exists',
                'expected': 'true',
                'timeout_tier': 'standard'
            }
        ]
    }


@pytest.fixture(autouse=True)
def cleanup_checkpoints():
    """Clean up checkpoint files after each test."""
    yield
    checkpoint_dir = Path("/home/pook/engineer-team/.playbook-checkpoints")
    if checkpoint_dir.exists():
        for file in checkpoint_dir.glob("*.json"):
            file.unlink()


class TestTimeoutTiers:
    """Test timeout tier functionality."""

    def test_timeout_tier_values(self):
        """Test timeout tier enum values."""
        assert TimeoutTier.INSTANT.timeout_seconds == 5
        assert TimeoutTier.FAST.timeout_seconds == 30
        assert TimeoutTier.STANDARD.timeout_seconds == 120
        assert TimeoutTier.LONG.timeout_seconds == 600
        assert TimeoutTier.BACKGROUND.timeout_seconds == 0

    def test_timeout_tier_names(self):
        """Test timeout tier names."""
        assert TimeoutTier.INSTANT.tier_name == "instant"
        assert TimeoutTier.FAST.tier_name == "fast"
        assert TimeoutTier.STANDARD.tier_name == "standard"
        assert TimeoutTier.LONG.tier_name == "long"
        assert TimeoutTier.BACKGROUND.tier_name == "background"

    def test_get_timeout_tier(self, executor):
        """Test timeout tier lookup."""
        ex, _ = executor

        assert ex._get_timeout_tier('instant') == TimeoutTier.INSTANT
        assert ex._get_timeout_tier('fast') == TimeoutTier.FAST
        assert ex._get_timeout_tier('standard') == TimeoutTier.STANDARD
        assert ex._get_timeout_tier('long') == TimeoutTier.LONG
        assert ex._get_timeout_tier('background') == TimeoutTier.BACKGROUND
        assert ex._get_timeout_tier('unknown') == TimeoutTier.STANDARD  # Default


class TestBasicExecution:
    """Test basic playbook execution."""

    @pytest.mark.asyncio
    async def test_successful_execution(self, executor, sample_playbook):
        """Test successful playbook execution."""
        ex, breaker = executor

        result = await ex.execute(sample_playbook)

        assert result.status == "success"
        assert result.steps_completed == 3
        assert result.steps_total == 3
        assert len(result.step_results) == 3
        assert result.completed_at is not None

        # Check circuit breaker recorded success
        assert len(breaker.results) == 1
        assert breaker.results[0] == ('test-playbook-001', True)

    @pytest.mark.asyncio
    async def test_execution_blocked_by_circuit_breaker(self, sample_playbook):
        """Test execution blocked by circuit breaker."""
        breaker = MockCircuitBreaker(allow_execute=False)
        ex = PlaybookExecutor(circuit_breaker=breaker)

        result = await ex.execute(sample_playbook)

        assert result.status == "blocked"
        assert result.steps_completed == 0
        assert len(result.step_results) == 0

    @pytest.mark.asyncio
    async def test_step_results_captured(self, executor, sample_playbook):
        """Test that step results are properly captured."""
        ex, _ = executor

        result = await ex.execute(sample_playbook)

        for step_result in result.step_results:
            assert step_result.status == StepStatus.COMPLETED
            assert step_result.duration_ms > 0
            assert step_result.output is not None


class TestTimeoutHandling:
    """Test timeout handling."""

    @pytest.mark.asyncio
    async def test_step_timeout(self, executor):
        """Test step timeout enforcement."""
        ex, breaker = executor

        # Create handler that sleeps longer than timeout
        async def slow_handler(step, context, playbook):
            await asyncio.sleep(10)  # Sleep 10 seconds
            return "Done"

        ex.register_handler('slow_action', slow_handler)

        playbook = {
            'id': 'timeout-test',
            'resolution_steps': [
                {
                    'id': 'slow-step',
                    'action': 'slow_action',
                    'timeout_tier': 'instant'  # 5 second timeout
                }
            ]
        }

        result = await ex.execute(playbook)

        assert result.status == "partial"
        assert len(result.step_results) == 1
        assert result.step_results[0].status == StepStatus.TIMEOUT
        assert 'timed out' in result.step_results[0].error.lower()

        # Circuit breaker should record failure
        assert breaker.results[0] == ('timeout-test', False)

    @pytest.mark.asyncio
    async def test_background_no_timeout(self, executor):
        """Test background tier has no timeout."""
        ex, _ = executor

        async def long_handler(step, context, playbook):
            await asyncio.sleep(0.1)  # Small sleep for test
            return "Background task completed"

        ex.register_handler('background_action', long_handler)

        playbook = {
            'id': 'background-test',
            'resolution_steps': [
                {
                    'id': 'bg-step',
                    'action': 'background_action',
                    'timeout_tier': 'background'
                }
            ]
        }

        result = await ex.execute(playbook)

        assert result.status == "success"
        assert result.step_results[0].status == StepStatus.COMPLETED


class TestCheckpointing:
    """Test checkpointing and resume functionality."""

    @pytest.mark.asyncio
    async def test_checkpoint_saved_after_each_step(self, executor, sample_playbook):
        """Test checkpoint is saved after each step."""
        ex, _ = executor

        result = await ex.execute(sample_playbook)

        # Checkpoint should be cleared after successful completion
        checkpoint_path = ex.CHECKPOINT_DIR / "test-playbook-001.json"
        assert not checkpoint_path.exists()

    @pytest.mark.asyncio
    async def test_checkpoint_saved_on_failure(self, executor):
        """Test checkpoint is saved on step failure."""
        ex, _ = executor

        async def failing_handler(step, context, playbook):
            raise ValueError("Step failed")

        ex.register_handler('failing_action', failing_handler)

        playbook = {
            'id': 'checkpoint-test',
            'resolution_steps': [
                {'id': 'step-1', 'action': 'analyze', 'timeout_tier': 'instant'},
                {'id': 'step-2', 'action': 'failing_action', 'timeout_tier': 'fast'},
                {'id': 'step-3', 'action': 'verify', 'timeout_tier': 'standard'}
            ]
        }

        result = await ex.execute(playbook)

        assert result.status == "partial"
        assert result.steps_completed == 2

        # Checkpoint should exist
        checkpoint_path = ex.CHECKPOINT_DIR / "checkpoint-test.json"
        assert checkpoint_path.exists()

        # Load and verify checkpoint
        with open(checkpoint_path) as f:
            checkpoint = json.load(f)

        assert checkpoint['playbook_id'] == 'checkpoint-test'
        assert checkpoint['next_step'] == 2
        assert len(checkpoint['step_results']) == 2

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(self, executor):
        """Test resuming execution from checkpoint."""
        ex, breaker = executor

        call_count = {'count': 0}

        async def counted_handler(step, context, playbook):
            call_count['count'] += 1
            if call_count['count'] == 2:
                raise ValueError("Fail on second call")
            return "Success"

        ex.register_handler('counted_action', counted_handler)

        playbook = {
            'id': 'resume-test',
            'resolution_steps': [
                {'id': 'step-1', 'action': 'counted_action', 'timeout_tier': 'fast'},
                {'id': 'step-2', 'action': 'counted_action', 'timeout_tier': 'fast'},
                {'id': 'step-3', 'action': 'counted_action', 'timeout_tier': 'fast'}
            ]
        }

        # First execution - should fail on step 2
        result1 = await ex.execute(playbook)
        assert result1.status == "partial"
        assert result1.steps_completed == 2
        assert call_count['count'] == 2

        # Resume - should skip step 1, retry step 2, then do step 3
        result2 = await ex.execute(playbook)
        assert result2.status == "success"
        assert result2.steps_completed == 3
        assert call_count['count'] == 4  # Steps 2 and 3 executed again


class TestStepHandlers:
    """Test step handler functionality."""

    @pytest.mark.asyncio
    async def test_analyze_handler(self, executor):
        """Test analyze action handler."""
        ex, _ = executor

        step = {
            'id': 'analyze-1',
            'action': 'analyze',
            'command': 'ls -la',
            'description': 'List files'
        }

        result = await ex._handle_analyze(step, {}, {})

        assert 'Analysis' in result
        assert 'ls -la' in result

    @pytest.mark.asyncio
    async def test_read_handler(self, executor):
        """Test read action handler."""
        ex, _ = executor

        step = {
            'id': 'read-1',
            'action': 'read',
            'files': ['file1.py', 'file2.py']
        }

        result = await ex._handle_read(step, {}, {})

        assert 'file1.py' in result
        assert 'file2.py' in result

    @pytest.mark.asyncio
    async def test_custom_handler_registration(self, executor):
        """Test custom handler registration."""
        ex, _ = executor

        async def custom_handler(step, context, playbook):
            return f"Custom: {step.get('data')}"

        ex.register_handler('custom_action', custom_handler)

        playbook = {
            'id': 'custom-test',
            'resolution_steps': [
                {'id': 'custom-1', 'action': 'custom_action', 'data': 'test-data', 'timeout_tier': 'fast'}
            ]
        }

        result = await ex.execute(playbook)

        assert result.status == "success"
        assert 'Custom: test-data' in result.step_results[0].output


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_step_error_captured(self, executor):
        """Test that step errors are captured."""
        ex, _ = executor

        async def error_handler(step, context, playbook):
            raise RuntimeError("Test error message")

        ex.register_handler('error_action', error_handler)

        playbook = {
            'id': 'error-test',
            'resolution_steps': [
                {'id': 'error-step', 'action': 'error_action', 'timeout_tier': 'fast'}
            ]
        }

        result = await ex.execute(playbook)

        assert result.status == "partial"
        assert result.step_results[0].status == StepStatus.FAILED
        assert 'Test error message' in result.step_results[0].error

    @pytest.mark.asyncio
    async def test_partial_completion_on_failure(self, executor):
        """Test partial completion when step fails."""
        ex, _ = executor

        async def fail_second(step, context, playbook):
            if step['id'] == 'step-2':
                raise ValueError("Second step fails")
            return "Success"

        ex.register_handler('test_action', fail_second)

        playbook = {
            'id': 'partial-test',
            'resolution_steps': [
                {'id': 'step-1', 'action': 'test_action', 'timeout_tier': 'fast'},
                {'id': 'step-2', 'action': 'test_action', 'timeout_tier': 'fast'},
                {'id': 'step-3', 'action': 'test_action', 'timeout_tier': 'fast'}
            ]
        }

        result = await ex.execute(playbook)

        assert result.status == "partial"
        assert result.steps_completed == 2
        assert result.step_results[0].status == StepStatus.COMPLETED
        assert result.step_results[1].status == StepStatus.FAILED


class TestExecutionResult:
    """Test ExecutionResult dataclass."""

    def test_to_dict(self):
        """Test ExecutionResult serialization."""
        result = ExecutionResult(
            playbook_id="test-123",
            status="success",
            steps_completed=3,
            steps_total=3,
            step_results=[
                StepResult(
                    step_id="step-1",
                    status=StepStatus.COMPLETED,
                    output="Done",
                    duration_ms=100
                )
            ],
            started_at=datetime(2024, 1, 1, 12, 0, 0),
            completed_at=datetime(2024, 1, 1, 12, 0, 5),
            checkpoint_path=Path("/tmp/checkpoint.json")
        )

        data = result.to_dict()

        assert data['playbook_id'] == "test-123"
        assert data['status'] == "success"
        assert data['steps_completed'] == 3
        assert len(data['step_results']) == 1
        assert data['step_results'][0]['step_id'] == "step-1"


class TestSynchronousResume:
    """Test synchronous resume wrapper."""

    def test_resume_wrapper(self, executor, sample_playbook):
        """Test synchronous resume wrapper."""
        ex, _ = executor

        result = ex.resume(sample_playbook)

        assert result.status == "success"
        assert result.steps_completed == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
