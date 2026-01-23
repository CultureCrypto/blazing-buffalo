"""Track playbook effectiveness with per-project-type metrics and A/B testing."""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict
import json
from pathlib import Path
import random
import math


@dataclass
class EffectivenessMetrics:
    """Effectiveness metrics for a playbook."""
    success_rate: float  # 0.0-1.0
    avg_resolution_time_ms: float
    user_satisfaction: float  # 0.0-1.0, from feedback
    regression_rate: float  # How often fix causes new issues
    sample_size: int


@dataclass
class ABTestResult:
    """A/B test result."""
    variant_a: str
    variant_b: str
    variant_a_success_rate: float
    variant_b_success_rate: float
    sample_size_a: int
    sample_size_b: int
    winner: Optional[str]
    confidence: float
    completed: bool


class EffectivenessTracker:
    """Track playbook effectiveness with per-project-type metrics."""

    DATA_DIR = Path("/home/pook/engineer-team/data/effectiveness")
    MIN_SAMPLE_SIZE = 10
    AB_TEST_MIN_SAMPLES = 20  # Minimum per variant for statistical significance

    def __init__(self):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.metrics: Dict[str, Dict[str, EffectivenessMetrics]] = defaultdict(dict)
        self.executions: List[Dict] = []
        self.ab_tests: Dict[str, ABTestResult] = {}
        self.feedback: Dict[str, List[float]] = defaultdict(list)  # playbook_id:project_type -> [ratings]
        self._load_data()

    def record_execution(self, playbook_id: str, project_type: str,
                         success: bool, duration_ms: int,
                         caused_regression: bool = False,
                         variant: Optional[str] = None) -> None:
        """Record a playbook execution result."""
        execution = {
            "playbook_id": playbook_id,
            "project_type": project_type,
            "success": success,
            "duration_ms": duration_ms,
            "caused_regression": caused_regression,
            "variant": variant,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.executions.append(execution)
        self._update_metrics(playbook_id, project_type)
        self._save_data()

        # Update A/B test if variant specified
        if variant:
            self._update_ab_test(playbook_id, variant, success)

    def record_feedback(self, playbook_id: str, project_type: str,
                        satisfaction: float) -> None:
        """Record user satisfaction feedback (0.0-1.0)."""
        if not 0.0 <= satisfaction <= 1.0:
            raise ValueError("Satisfaction must be between 0.0 and 1.0")

        key = f"{playbook_id}:{project_type}"
        self.feedback[key].append(satisfaction)
        self._update_metrics(playbook_id, project_type)
        self._save_data()

    def get_metrics(self, playbook_id: str,
                    project_type: Optional[str] = None) -> EffectivenessMetrics:
        """Get effectiveness metrics for a playbook."""
        if project_type and project_type in self.metrics.get(playbook_id, {}):
            return self.metrics[playbook_id][project_type]

        # Calculate aggregate if no project type specified
        return self._calculate_aggregate_metrics(playbook_id)

    def start_ab_test(self, playbook_id: str, variant_a: str,
                      variant_b: str) -> str:
        """Start an A/B test for playbook variants."""
        test_id = f"{playbook_id}_ab_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        self.ab_tests[test_id] = ABTestResult(
            variant_a=variant_a,
            variant_b=variant_b,
            variant_a_success_rate=0.0,
            variant_b_success_rate=0.0,
            sample_size_a=0,
            sample_size_b=0,
            winner=None,
            confidence=0.0,
            completed=False
        )
        self._save_data()
        return test_id

    def get_variant(self, test_id: str) -> Optional[str]:
        """Get which variant to use for next execution."""
        test = self.ab_tests.get(test_id)
        if not test or test.completed:
            return test.variant_a if test else None

        # Simple random assignment (50/50)
        return random.choice([test.variant_a, test.variant_b])

    def get_ab_test_result(self, test_id: str) -> Optional[ABTestResult]:
        """Get A/B test result."""
        return self.ab_tests.get(test_id)

    def get_top_playbooks(self, project_type: str,
                          limit: int = 10) -> List[Dict]:
        """Get top performing playbooks for a project type."""
        results = []
        for playbook_id, type_metrics in self.metrics.items():
            if project_type in type_metrics:
                m = type_metrics[project_type]
                # Only include playbooks with sufficient sample size
                if m.sample_size >= self.MIN_SAMPLE_SIZE:
                    results.append({
                        "playbook_id": playbook_id,
                        "success_rate": m.success_rate,
                        "avg_resolution_time_ms": m.avg_resolution_time_ms,
                        "user_satisfaction": m.user_satisfaction,
                        "regression_rate": m.regression_rate,
                        "sample_size": m.sample_size
                    })

        # Sort by composite score: success_rate * (1 - regression_rate) * user_satisfaction
        def score(x):
            return x['success_rate'] * (1 - x['regression_rate']) * x['user_satisfaction']

        return sorted(results, key=score, reverse=True)[:limit]

    def _update_metrics(self, playbook_id: str, project_type: str) -> None:
        """Recalculate metrics for a playbook/project-type."""
        relevant = [
            e for e in self.executions
            if e['playbook_id'] == playbook_id
            and e['project_type'] == project_type
        ]

        if not relevant:
            return

        successes = sum(1 for e in relevant if e['success'])
        total = len(relevant)
        regressions = sum(1 for e in relevant if e.get('caused_regression', False))
        avg_duration = sum(e['duration_ms'] for e in relevant) / total

        # Get average satisfaction from feedback
        key = f"{playbook_id}:{project_type}"
        feedback_list = self.feedback.get(key, [])
        avg_satisfaction = sum(feedback_list) / len(feedback_list) if feedback_list else 0.8

        self.metrics[playbook_id][project_type] = EffectivenessMetrics(
            success_rate=successes / total,
            avg_resolution_time_ms=avg_duration,
            user_satisfaction=avg_satisfaction,
            regression_rate=regressions / total if total > 0 else 0.0,
            sample_size=total
        )

    def _update_ab_test(self, playbook_id: str, variant: str,
                        success: bool) -> None:
        """Update A/B test statistics."""
        for test_id, test in self.ab_tests.items():
            if playbook_id in test_id and not test.completed:
                if variant == test.variant_a:
                    test.sample_size_a += 1
                    # Update success rate incrementally
                    old_rate = test.variant_a_success_rate
                    n = test.sample_size_a
                    test.variant_a_success_rate = old_rate + (1 if success else 0 - old_rate) / n

                elif variant == test.variant_b:
                    test.sample_size_b += 1
                    old_rate = test.variant_b_success_rate
                    n = test.sample_size_b
                    test.variant_b_success_rate = old_rate + (1 if success else 0 - old_rate) / n

                # Check if test complete
                if test.sample_size_a >= self.AB_TEST_MIN_SAMPLES and \
                   test.sample_size_b >= self.AB_TEST_MIN_SAMPLES:
                    self._conclude_ab_test(test_id)

                self._save_data()

    def _conclude_ab_test(self, test_id: str) -> None:
        """Conclude an A/B test and determine winner with statistical significance."""
        test = self.ab_tests[test_id]

        # Calculate z-score for proportion difference
        p1 = test.variant_a_success_rate
        p2 = test.variant_b_success_rate
        n1 = test.sample_size_a
        n2 = test.sample_size_b

        # Pooled proportion
        p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)

        # Standard error
        se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))

        if se > 0:
            z_score = abs(p1 - p2) / se
            # Confidence level (approximate, for z > 1.96 => 95% confidence)
            confidence = min(0.99, max(0.0, (z_score - 1.96) / 2.0))
        else:
            z_score = 0
            confidence = 0.0

        test.confidence = confidence

        # Determine winner if difference is significant (z > 1.96 for 95% confidence)
        if z_score > 1.96:
            if p1 > p2:
                test.winner = test.variant_a
            else:
                test.winner = test.variant_b
        else:
            test.winner = "inconclusive"

        test.completed = True

    def _calculate_aggregate_metrics(self, playbook_id: str) -> EffectivenessMetrics:
        """Calculate aggregate metrics across all project types."""
        all_metrics = list(self.metrics.get(playbook_id, {}).values())
        if not all_metrics:
            return EffectivenessMetrics(0.0, 0.0, 0.0, 0.0, 0)

        total_samples = sum(m.sample_size for m in all_metrics)
        if total_samples == 0:
            return EffectivenessMetrics(0.0, 0.0, 0.0, 0.0, 0)

        # Weighted average
        success_rate = sum(m.success_rate * m.sample_size for m in all_metrics) / total_samples
        avg_time = sum(m.avg_resolution_time_ms * m.sample_size for m in all_metrics) / total_samples
        satisfaction = sum(m.user_satisfaction * m.sample_size for m in all_metrics) / total_samples
        regression = sum(m.regression_rate * m.sample_size for m in all_metrics) / total_samples

        return EffectivenessMetrics(
            success_rate=success_rate,
            avg_resolution_time_ms=avg_time,
            user_satisfaction=satisfaction,
            regression_rate=regression,
            sample_size=total_samples
        )

    def _load_data(self) -> None:
        """Load persisted data."""
        executions_file = self.DATA_DIR / "executions.json"
        if executions_file.exists():
            with open(executions_file) as f:
                self.executions = json.load(f)
                # Rebuild metrics from executions
                for exec_data in self.executions:
                    self._update_metrics(exec_data['playbook_id'], exec_data['project_type'])

        feedback_file = self.DATA_DIR / "feedback.json"
        if feedback_file.exists():
            with open(feedback_file) as f:
                self.feedback = defaultdict(list, json.load(f))

        ab_tests_file = self.DATA_DIR / "ab_tests.json"
        if ab_tests_file.exists():
            with open(ab_tests_file) as f:
                data = json.load(f)
                self.ab_tests = {
                    k: ABTestResult(**v) for k, v in data.items()
                }

    def _save_data(self) -> None:
        """Persist data."""
        with open(self.DATA_DIR / "executions.json", 'w') as f:
            json.dump(self.executions, f, indent=2)

        with open(self.DATA_DIR / "feedback.json", 'w') as f:
            json.dump(dict(self.feedback), f, indent=2)

        with open(self.DATA_DIR / "ab_tests.json", 'w') as f:
            data = {k: asdict(v) for k, v in self.ab_tests.items()}
            json.dump(data, f, indent=2)
