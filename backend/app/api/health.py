"""
Health check and Observability Metrics API router.

Provides:
- /health: Liveness probe for Docker and Kubernetes container monitoring.
- /health/ready: Readiness probe checking database connectivity.
- /health/metrics: Real-time operational metrics, error rates, and latency percentiles.
"""

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.database.session import async_session_factory
from app.observability.tracer import metrics_tracker

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """
    Liveness probe endpoint.

    Returns immediate 200 OK to indicate the ASGI process is running.
    """
    return {
        "status": "healthy",
        "service": "enterprise-rag-api",
        "version": "1.0.0",
    }


@router.get("/health/ready")
async def readiness_check() -> dict[str, Any]:
    """
    Readiness probe endpoint.

    Verifies active database connection before routing traffic.
    """
    db_healthy = False
    if async_session_factory:
        try:
            async with async_session_factory() as session:
                result = await session.execute(text("SELECT 1"))
                db_healthy = result.scalar() == 1
        except Exception:
            db_healthy = False

    return {
        "status": "ready" if db_healthy else "degraded",
        "database": "connected" if db_healthy else "disconnected",
    }


@router.get("/health/metrics")
async def metrics_summary() -> dict[str, Any]:
    """
    Operational SLA and latency percentiles endpoint.

    Returns P50, P90, P99 query latency, uptime, and request counters.
    """
    return metrics_tracker.get_summary()
