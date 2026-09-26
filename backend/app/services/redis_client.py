"""
Enterprise RAG Platform — Redis Service Client.

Provides async Redis connection pooling, health probes, and support for both
local development (redis://) and managed cloud TLS (rediss://, e.g. Upstash).
"""

import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_pool: aioredis.Redis | None = None


def get_redis_client() -> aioredis.Redis | None:
    """
    Get or initialize the shared async Redis client singleton.

    Supports both redis:// and secure rediss:// (TLS) URLs.
    """
    global _redis_pool
    if _redis_pool is not None:
        return _redis_pool

    url = settings.redis_url.strip()
    if not url:
        return None

    try:
        # For cloud TLS (rediss://), disable strict cert verification for Upstash/render
        if url.startswith("rediss://"):
            _redis_pool = aioredis.from_url(  # type: ignore[no-untyped-call]
                url,
                encoding="utf-8",
                decode_responses=True,
                ssl_cert_reqs=None,
            )
        else:
            _redis_pool = aioredis.from_url(  # type: ignore[no-untyped-call]
                url,
                encoding="utf-8",
                decode_responses=True,
            )
        return _redis_pool
    except Exception as exc:
        logger.warning("Failed to initialize Redis client pool: %s", exc)
        return None


async def check_redis_health() -> bool:
    """
    Check if Redis is accessible and responding to PING.

    Returns True if healthy, False if unreachable or unconfigured.
    """
    client = get_redis_client()
    if client is None:
        return False
    try:
        response = await client.ping()
        return bool(response)
    except Exception as exc:
        logger.debug("Redis health check ping failed: %s", exc)
        return False


async def close_redis_client() -> None:
    """Gracefully close the Redis client connection pool."""
    global _redis_pool
    if _redis_pool is not None:
        try:
            await _redis_pool.aclose()
        except Exception as exc:
            logger.debug("Error while closing Redis connection: %s", exc)
        finally:
            _redis_pool = None
