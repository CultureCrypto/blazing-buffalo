"""
Prometheus Metrics for Blazing Buffalo Mistake Learning System.

Provides comprehensive observability metrics for:
- Mistake detection and classification
- Playbook execution and lifecycle
- RCA pipeline performance
- Circuit breaker states
- Taxonomy clustering
- System health

Usage:
    from lib.metrics import (
        mistakes_detected_total,
        track_rca_latency,
        track_playbook_execution,
        init_metrics
    )

    # Initialize on startup
    init_metrics()

    # Use decorators
    @track_rca_latency
    async def analyze_mistake(mistake):
        ...

    @track_playbook_execution("fix-import-error")
    async def execute_playbook():
        ...

    # Direct metric updates
    mistakes_detected_total.labels(
        category="tool_misuse",
        severity="high",
        detection_method="pattern_match"
    ).inc()
"""

from prometheus_client import Counter, Histogram, Gauge, Info
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from functools import wraps
import time
from typing import Callable, Any
import asyncio


# ============================================================================
# COUNTERS - Monotonically increasing values
# ============================================================================

mistakes_detected_total = Counter(
    'blazing_buffalo_mistakes_detected_total',
    'Total mistakes detected across all categories',
    ['category', 'severity', 'detection_method']
)

playbook_executions_total = Counter(
    'blazing_buffalo_playbook_executions_total',
    'Total playbook executions by outcome',
    ['playbook_id', 'status']  # status: success, failed, timeout, partial
)

playbook_steps_total = Counter(
    'blazing_buffalo_playbook_steps_total',
    'Total playbook steps executed',
    ['playbook_id', 'step_type', 'status']  # step_type: Read, Edit, Bash, etc.
)

rca_analyses_total = Counter(
    'blazing_buffalo_rca_analyses_total',
    'Total RCA analyses performed',
    ['root_cause_category', 'model']  # model: claude, gemini, glm
)

rca_convergence_total = Counter(
    'blazing_buffalo_rca_convergence_total',
    'RCA model convergence outcomes',
    ['converged']  # converged: true, false
)

taxonomy_cluster_assignments_total = Counter(
    'blazing_buffalo_taxonomy_cluster_assignments_total',
    'Total mistake-to-cluster assignments',
    ['cluster_label']
)

circuit_breaker_trips_total = Counter(
    'blazing_buffalo_circuit_breaker_trips_total',
    'Total circuit breaker state changes',
    ['playbook_id', 'from_state', 'to_state']
)


# ============================================================================
# HISTOGRAMS - Distribution of observed values
# ============================================================================

rca_latency_seconds = Histogram(
    'blazing_buffalo_rca_latency_seconds',
    'RCA pipeline end-to-end latency',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

playbook_duration_seconds = Histogram(
    'blazing_buffalo_playbook_duration_seconds',
    'Playbook execution duration from start to completion',
    ['playbook_id'],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600]
)

playbook_step_duration_seconds = Histogram(
    'blazing_buffalo_playbook_step_duration_seconds',
    'Individual playbook step execution time',
    ['step_type', 'timeout_tier'],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120, 300, 600]
)

similar_mistake_search_latency_seconds = Histogram(
    'blazing_buffalo_similar_mistake_search_latency_seconds',
    'Qdrant vector search latency for similar mistakes',
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0]
)

taxonomy_clustering_latency_seconds = Histogram(
    'blazing_buffalo_taxonomy_clustering_latency_seconds',
    'HDBSCAN clustering operation latency',
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)


# ============================================================================
# GAUGES - Values that can go up or down
# ============================================================================

circuit_breaker_state = Gauge(
    'blazing_buffalo_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half_open)',
    ['playbook_id']
)

active_playbook_executions = Gauge(
    'blazing_buffalo_active_playbook_executions',
    'Currently executing playbooks'
)

playbook_success_rate = Gauge(
    'blazing_buffalo_playbook_success_rate',
    'Playbook success rate over last 100 executions (0.0-1.0)',
    ['playbook_id']
)

playbook_error_budget_remaining = Gauge(
    'blazing_buffalo_playbook_error_budget_remaining',
    'Circuit breaker error budget remaining (0.0-1.0)',
    ['playbook_id']
)

taxonomy_cluster_count = Gauge(
    'blazing_buffalo_taxonomy_clusters_total',
    'Number of active taxonomy clusters'
)

taxonomy_cluster_size = Gauge(
    'blazing_buffalo_taxonomy_cluster_size',
    'Number of mistakes in each cluster',
    ['cluster_label']
)

neo4j_connection_pool_active = Gauge(
    'blazing_buffalo_neo4j_connection_pool_active',
    'Active Neo4j connections'
)

qdrant_collection_vectors = Gauge(
    'blazing_buffalo_qdrant_collection_vectors',
    'Total vectors in Qdrant collection',
    ['collection_name']
)


# ============================================================================
# INFO - Static labels about the system
# ============================================================================

system_info = Info(
    'blazing_buffalo_system',
    'System metadata and version information'
)


# ============================================================================
# DECORATORS - Easy instrumentation helpers
# ============================================================================

def track_rca_latency(func: Callable) -> Callable:
    """
    Decorator to track RCA pipeline latency.

    Usage:
        @track_rca_latency
        async def run_rca_pipeline(mistake_id: str):
            ...
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            rca_latency_seconds.observe(time.time() - start)

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            rca_latency_seconds.observe(time.time() - start)

    # Return appropriate wrapper based on function type
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def track_playbook_execution(playbook_id: str):
    """
    Decorator to track playbook execution metrics.

    Tracks:
    - Active executions (increments/decrements)
    - Total executions by status
    - Execution duration

    Usage:
        @track_playbook_execution("fix-import-error")
        async def execute_playbook(context):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            active_playbook_executions.inc()
            start = time.time()
            status = "failed"  # Default to failed
            try:
                result = await func(*args, **kwargs)

                # Determine status from result
                if hasattr(result, 'status'):
                    status = result.status
                else:
                    status = "success"

                return result
            except asyncio.TimeoutError:
                status = "timeout"
                raise
            except Exception:
                status = "failed"
                raise
            finally:
                active_playbook_executions.dec()
                playbook_executions_total.labels(
                    playbook_id=playbook_id,
                    status=status
                ).inc()
                playbook_duration_seconds.labels(
                    playbook_id=playbook_id
                ).observe(time.time() - start)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            active_playbook_executions.inc()
            start = time.time()
            status = "failed"
            try:
                result = func(*args, **kwargs)
                if hasattr(result, 'status'):
                    status = result.status
                else:
                    status = "success"
                return result
            except Exception:
                status = "failed"
                raise
            finally:
                active_playbook_executions.dec()
                playbook_executions_total.labels(
                    playbook_id=playbook_id,
                    status=status
                ).inc()
                playbook_duration_seconds.labels(
                    playbook_id=playbook_id
                ).observe(time.time() - start)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


def track_step_execution(step_type: str, timeout_tier: str = "standard"):
    """
    Decorator to track individual playbook step execution.

    Usage:
        @track_step_execution("Read", "instant")
        async def execute_read_step(filepath):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            status = "failed"
            try:
                result = await func(*args, **kwargs)
                status = "success"
                return result
            except Exception:
                status = "failed"
                raise
            finally:
                playbook_step_duration_seconds.labels(
                    step_type=step_type,
                    timeout_tier=timeout_tier
                ).observe(time.time() - start)
                playbook_steps_total.labels(
                    playbook_id=kwargs.get('playbook_id', 'unknown'),
                    step_type=step_type,
                    status=status
                ).inc()

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            status = "failed"
            try:
                result = func(*args, **kwargs)
                status = "success"
                return result
            except Exception:
                status = "failed"
                raise
            finally:
                playbook_step_duration_seconds.labels(
                    step_type=step_type,
                    timeout_tier=timeout_tier
                ).observe(time.time() - start)
                playbook_steps_total.labels(
                    playbook_id=kwargs.get('playbook_id', 'unknown'),
                    step_type=step_type,
                    status=status
                ).inc()

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def update_circuit_breaker_state(playbook_id: str, state: str):
    """
    Update circuit breaker state gauge.

    Args:
        playbook_id: Playbook identifier
        state: "closed", "open", or "half_open"
    """
    state_map = {
        "closed": 0,
        "open": 1,
        "half_open": 2
    }
    circuit_breaker_state.labels(playbook_id=playbook_id).set(
        state_map.get(state, 0)
    )


def update_playbook_success_rate(playbook_id: str, success_rate: float):
    """
    Update playbook success rate gauge.

    Args:
        playbook_id: Playbook identifier
        success_rate: Success rate from 0.0 to 1.0
    """
    playbook_success_rate.labels(playbook_id=playbook_id).set(success_rate)


def update_error_budget(playbook_id: str, budget_remaining: float):
    """
    Update circuit breaker error budget gauge.

    Args:
        playbook_id: Playbook identifier
        budget_remaining: Budget from 0.0 (depleted) to 1.0 (full)
    """
    playbook_error_budget_remaining.labels(playbook_id=playbook_id).set(
        budget_remaining
    )


def record_mistake_detection(
    category: str,
    severity: str,
    detection_method: str = "manual"
):
    """
    Record a mistake detection event.

    Args:
        category: Mistake category (knowledge_gap, tool_misuse, etc.)
        severity: low, medium, high, critical
        detection_method: manual, pattern_match, taxonomy_cluster, etc.
    """
    mistakes_detected_total.labels(
        category=category,
        severity=severity,
        detection_method=detection_method
    ).inc()


def record_rca_analysis(root_cause_category: str, model: str, converged: bool):
    """
    Record an RCA analysis completion.

    Args:
        root_cause_category: Category from RootCauseCategory enum
        model: claude, gemini, or glm
        converged: Whether models converged on same root cause
    """
    rca_analyses_total.labels(
        root_cause_category=root_cause_category,
        model=model
    ).inc()

    rca_convergence_total.labels(
        converged=str(converged).lower()
    ).inc()


def record_circuit_breaker_trip(
    playbook_id: str,
    from_state: str,
    to_state: str
):
    """
    Record a circuit breaker state transition.

    Args:
        playbook_id: Playbook identifier
        from_state: Previous state (closed, open, half_open)
        to_state: New state
    """
    circuit_breaker_trips_total.labels(
        playbook_id=playbook_id,
        from_state=from_state,
        to_state=to_state
    ).inc()

    update_circuit_breaker_state(playbook_id, to_state)


def update_taxonomy_metrics(cluster_count: int, cluster_sizes: dict):
    """
    Update taxonomy clustering metrics.

    Args:
        cluster_count: Total number of clusters
        cluster_sizes: Dict mapping cluster_label -> size
    """
    taxonomy_cluster_count.set(cluster_count)

    for label, size in cluster_sizes.items():
        taxonomy_cluster_size.labels(cluster_label=label).set(size)


# ============================================================================
# METRICS ENDPOINT
# ============================================================================

def metrics_endpoint() -> bytes:
    """
    Generate Prometheus metrics in text exposition format.

    Returns:
        bytes: Metrics in Prometheus text format

    Usage with FastAPI:
        from fastapi import Response
        from lib.metrics import metrics_endpoint, CONTENT_TYPE_LATEST

        @app.get("/metrics")
        async def get_metrics():
            return Response(
                content=metrics_endpoint(),
                media_type=CONTENT_TYPE_LATEST
            )
    """
    return generate_latest()


# ============================================================================
# INITIALIZATION
# ============================================================================

def init_metrics(version: str = "1.0.0", environment: str = "production"):
    """
    Initialize metrics system with static metadata.

    Call this once on application startup.

    Args:
        version: Application version
        environment: deployment environment (production, staging, dev)
    """
    system_info.info({
        'version': version,
        'component': 'blazing_buffalo',
        'environment': environment
    })

    # Initialize all circuit breaker states to closed
    # These will be updated as circuit breakers are created
    active_playbook_executions.set(0)


# Export commonly used items
__all__ = [
    # Counters
    'mistakes_detected_total',
    'playbook_executions_total',
    'playbook_steps_total',
    'rca_analyses_total',
    'rca_convergence_total',
    'taxonomy_cluster_assignments_total',
    'circuit_breaker_trips_total',

    # Histograms
    'rca_latency_seconds',
    'playbook_duration_seconds',
    'playbook_step_duration_seconds',
    'similar_mistake_search_latency_seconds',
    'taxonomy_clustering_latency_seconds',

    # Gauges
    'circuit_breaker_state',
    'active_playbook_executions',
    'playbook_success_rate',
    'playbook_error_budget_remaining',
    'taxonomy_cluster_count',
    'taxonomy_cluster_size',
    'neo4j_connection_pool_active',
    'qdrant_collection_vectors',

    # Info
    'system_info',

    # Decorators
    'track_rca_latency',
    'track_playbook_execution',
    'track_step_execution',

    # Helpers
    'update_circuit_breaker_state',
    'update_playbook_success_rate',
    'update_error_budget',
    'record_mistake_detection',
    'record_rca_analysis',
    'record_circuit_breaker_trip',
    'update_taxonomy_metrics',

    # Endpoint
    'metrics_endpoint',
    'CONTENT_TYPE_LATEST',
    'init_metrics',
]
