"""
Health check API router.

Provides a /health endpoint that returns the status of the application
and its dependencies. This is essential for:
- Docker health checks
- Load balancer health probes
- Monitoring and alerting
- Deployment readiness checks
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns basic application status. In later phases, this will also
    check connectivity to Supabase, Redis, and other dependencies.

    Returns:
        dict: Health status with service name and status.
    """
    return {
        "status": "healthy",
        "service": "enterprise-rag-api",
        "version": "0.1.0",
    }
