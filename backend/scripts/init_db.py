"""
Database Schema Initializer.

Connects to the database configured in DATABASE_URL, enables the pgvector extension,
and creates all required tables (documents, document_chunks) with HNSW and GIN indexes.

Usage:
    From project root:
        python backend/scripts/init_db.py
    From backend directory:
        python scripts/init_db.py
"""

import asyncio
import logging
import os
import sys

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text

from app.database.models import Base
from app.database.session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("init_db")


async def init_database() -> None:
    """Connect to PostgreSQL, enable pgvector, and create all schema tables."""
    if not engine:
        logger.error(
            "DATABASE_URL is not configured or is still using placeholder values.\n"
            "Please check your .env file and ensure DATABASE_URL is set."
        )
        sys.exit(1)

    masked_url = str(engine.url).split("@")[-1] if "@" in str(engine.url) else "configured database"
    logger.info("Connecting to PostgreSQL at: %s", masked_url)

    async with engine.begin() as conn:
        # 1. Enable pgvector extension (if on PostgreSQL)
        if "postgresql" in str(engine.url):
            try:
                logger.info("Enabling pgvector extension: CREATE EXTENSION IF NOT EXISTS vector;")
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                logger.info("✅ pgvector extension enabled successfully.")
            except Exception as e:
                logger.warning(
                    "Could not enable pgvector extension automatically (%s).\n"
                    "Ensure 'vector' is enabled in Supabase dashboard (Database -> Extensions).",
                    e,
                )

        # 2. Create tables and indexes
        logger.info("Creating tables: %s", list(Base.metadata.tables.keys()))
        await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ All tables and indexes created successfully!")

    await engine.dispose()
    logger.info("Database initialization complete.")


if __name__ == "__main__":
    asyncio.run(init_database())
