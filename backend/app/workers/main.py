"""
Standalone Background Worker Process Entrypoint.

Executed via:
    python -m app.workers.main

Responsibilities:
1. Bootstraps worker logging and secret scrubbing.
2. Validates database and Redis connectivity.
3. Runs scheduled 7-Day TTL document expiration and vector cleanup daemon.
4. Manages graceful shutdown on SIGINT / SIGTERM signals.
"""

import asyncio
import contextlib
import logging
import signal
import sys

from app.auth.sanitizer import install_log_sanitizer
from app.config import settings
from app.database.session import async_session_factory
from app.workers.cleanup_service import start_periodic_cleanup_loop

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | [WORKER] %(name)s | %(message)s",
)
install_log_sanitizer()
logger = logging.getLogger("worker_main")


async def main() -> None:
    """Initialize and run standalone background worker process."""
    logger.info("Initializing Enterprise RAG Standalone Background Worker...")
    logger.info("Environment: %s | Redis URL: %s", settings.environment, settings.redis_url)

    if not async_session_factory:
        logger.error("FATAL: DATABASE_URL is not configured. Worker cannot start.")
        sys.exit(1)

    from app.services.redis_client import check_redis_health

    redis_healthy = await check_redis_health()
    if redis_healthy:
        logger.info("Redis connectivity confirmed healthy.")
    else:
        logger.info("Redis not responding or unconfigured; running in standalone mode.")

    stop_event = asyncio.Event()

    # Register OS termination signals
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    # Start automated 7-day TTL cleanup daemon (runs every 1 hour)
    cleanup_task = asyncio.create_task(start_periodic_cleanup_loop(interval_seconds=3600))

    logger.info("Worker process initialized and listening for jobs. Press Ctrl+C to exit.")

    try:
        await stop_event.wait()
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Termination requested.")
    finally:
        logger.info("Shutting down worker services gracefully...")
        cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)
        logger.info("Worker process terminated cleanly.")


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
