"""
Automated 7-Day TTL Data Retention & Cleanup Service.

Periodically purges expired documents and their associated pgvector embeddings
to maintain database efficiency, cost boundaries, and privacy compliance (GDPR/SOC2).
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Document, DocumentChunk
from app.database.session import async_session_factory

logger = logging.getLogger(__name__)


async def cleanup_expired_documents(db: AsyncSession) -> dict[str, int]:
    """
    Identify and atomically delete all documents whose expires_at <= NOW().

    Cascades deletion to all child DocumentChunk vector embeddings.
    Returns a dictionary of cleanup statistics.
    """
    now = datetime.now(UTC)

    # 1. Query for expired documents
    stmt = select(Document.id).where(
        Document.expires_at.is_not(None),
        Document.expires_at <= now,
    )
    result = await db.execute(stmt)
    expired_ids = list(result.scalars().all())

    if not expired_ids:
        logger.debug("TTL Cleanup: 0 expired documents found.")
        return {"expired_documents": 0, "deleted_chunks": 0}

    # 2. Count child chunks for audit metrics before deletion
    chunk_count_stmt = select(DocumentChunk.id).where(DocumentChunk.document_id.in_(expired_ids))
    chunk_res = await db.execute(chunk_count_stmt)
    chunk_count = len(list(chunk_res.scalars().all()))

    # 3. Delete expired documents (CASCADE removes chunks in PostgreSQL)
    del_stmt = delete(Document).where(Document.id.in_(expired_ids))
    await db.execute(del_stmt)
    await db.commit()

    logger.info(
        "TTL Cleanup SUCCESS: Purged %d expired documents and %d vector chunks.",
        len(expired_ids),
        chunk_count,
    )
    return {
        "expired_documents": len(expired_ids),
        "deleted_chunks": chunk_count,
    }


async def start_periodic_cleanup_loop(interval_seconds: int = 3600) -> None:
    """
    Background daemon task executing document expiration checks periodically.

    Defaults to running every 1 hour (3600 seconds).
    """
    logger.info("TTL Cleanup Daemon started (check interval: %d seconds).", interval_seconds)
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            if async_session_factory:
                async with async_session_factory() as db:
                    stats = await cleanup_expired_documents(db)
                    if stats["expired_documents"] > 0:
                        logger.info("Scheduled TTL Cleanup purged: %s", stats)
        except asyncio.CancelledError:
            logger.info("TTL Cleanup Daemon received cancellation. Shutting down.")
            break
        except Exception as e:
            logger.exception("Error in TTL cleanup loop: %s", e)
