"""
Metrics endpoint addition for mistake_routes.py

Add this to the end of mistake_routes.py:
"""


@router.get("/metrics")
async def get_metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus text exposition format for:
    - Mistake detection counts by category/severity
    - Playbook execution statistics
    - RCA pipeline performance
    - Circuit breaker states
    - Taxonomy clustering metrics
    - System health indicators

    This endpoint is typically scraped by Prometheus server.
    """
    from fastapi import Response
    from lib.metrics import metrics_endpoint, CONTENT_TYPE_LATEST

    return Response(
        content=metrics_endpoint(),
        media_type=CONTENT_TYPE_LATEST
    )
