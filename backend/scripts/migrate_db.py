"""
Database Migration Script: Document Schema Extension.

Adds file_hash, page_count, and expires_at columns and indexes to documents table.
"""

import asyncio
import logging
from typing import Any

from sqlalchemy import text

from app.database.session import async_session_factory

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("migrate_db")


async def migrate() -> None:
    """Execute schema updates for document metadata and retention fields."""
    async with async_session_factory() as db:
        cols_query = text(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'documents';"
        )
        res = await db.execute(cols_query)
        existing: list[Any] = [r[0] for r in res.fetchall()]
        logger.info("Existing columns in 'documents': %s", existing)

        if "file_hash" not in existing:
            logger.info("Adding column 'file_hash' to documents...")
            await db.execute(text("ALTER TABLE documents ADD COLUMN file_hash VARCHAR(64);"))

        if "page_count" not in existing:
            logger.info("Adding column 'page_count' to documents...")
            await db.execute(text("ALTER TABLE documents ADD COLUMN page_count INTEGER;"))

        if "expires_at" not in existing:
            logger.info("Adding column 'expires_at' to documents...")
            await db.execute(text("ALTER TABLE documents ADD COLUMN expires_at TIMESTAMPTZ;"))

        # Add indexes
        logger.info("Ensuring indexes on documents...")
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_documents_file_hash "
                "ON documents(tenant_id, file_hash);"
            )
        )
        await db.execute(
            text("CREATE INDEX IF NOT EXISTS idx_documents_expires_at ON documents(expires_at);")
        )

        await db.commit()
        logger.info("Database schema migration successful!")


if __name__ == "__main__":
    asyncio.run(migrate())
