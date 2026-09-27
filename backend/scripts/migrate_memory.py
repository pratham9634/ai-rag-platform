"""
Database Migration Script: Persistent Memory & Summarization Schema.

Extends the schema with:
1. `conversations` table extensions: `user_id`, `summary`, `summary_version`
2. `messages` table extensions: `user_id`
3. `user_memories` table creation with 1536-dim pgvector HNSW indexing
"""

import asyncio
import logging
from typing import Any

from sqlalchemy import text

from app.database.session import async_session_factory

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
logger = logging.getLogger("migrate_memory")


async def migrate_memory_schema() -> None:
    """Apply schema migrations for conversation summary and persistent user memories."""
    if not async_session_factory:
        logger.error("DATABASE_URL is not configured. Aborting migration.")
        return

    async with async_session_factory() as db:
        # 1. Enable pgvector extension
        logger.info("Ensuring pgvector extension is enabled...")
        try:
            await db.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            logger.info("pgvector extension verified.")
        except Exception as e:
            logger.warning("Could not create pgvector extension: %s", e)

        # 2. Update 'conversations' table
        conv_cols_res = await db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'conversations';"
            )
        )
        existing_conv_cols: list[Any] = [r[0] for r in conv_cols_res.fetchall()]

        if "user_id" not in existing_conv_cols:
            logger.info("Adding 'user_id' to conversations...")
            await db.execute(
                text(
                    "ALTER TABLE conversations "
                    "ADD COLUMN user_id VARCHAR(255) NOT NULL DEFAULT 'unknown_user';"
                )
            )

        if "summary" not in existing_conv_cols:
            logger.info("Adding 'summary' to conversations...")
            await db.execute(text("ALTER TABLE conversations ADD COLUMN summary TEXT;"))

        if "summary_version" not in existing_conv_cols:
            logger.info("Adding 'summary_version' to conversations...")
            await db.execute(
                text(
                    "ALTER TABLE conversations "
                    "ADD COLUMN summary_version INTEGER NOT NULL DEFAULT 0;"
                )
            )

        logger.info("Ensuring indexes on conversations...")
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_conversations_user_updated "
                "ON conversations(user_id, updated_at);"
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_conversations_tenant_user "
                "ON conversations(tenant_id, user_id);"
            )
        )

        # 3. Update 'messages' table
        msg_cols_res = await db.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'messages';"
            )
        )
        existing_msg_cols: list[Any] = [r[0] for r in msg_cols_res.fetchall()]

        if "user_id" not in existing_msg_cols:
            logger.info("Adding 'user_id' to messages...")
            await db.execute(
                text(
                    "ALTER TABLE messages "
                    "ADD COLUMN user_id VARCHAR(255) NOT NULL DEFAULT 'unknown_user';"
                )
            )

        logger.info("Ensuring indexes on messages...")
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_messages_user_conv "
                "ON messages(user_id, conversation_id);"
            )
        )

        # 4. Create 'user_memories' table
        logger.info("Ensuring user_memories table exists...")
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS user_memories (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id VARCHAR(255) NOT NULL,
                    user_id VARCHAR(255) NOT NULL,
                    memory_type VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    embedding vector(1536),
                    importance DOUBLE PRECISION NOT NULL DEFAULT 0.5,
                    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                    source_conversation_id UUID,
                    source_message_id UUID,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        )

        logger.info("Ensuring indexes on user_memories...")
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_memories_user_active "
                "ON user_memories(user_id, is_active);"
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_memories_tenant_user_active "
                "ON user_memories(tenant_id, user_id, is_active);"
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_user_memories_type "
                "ON user_memories(user_id, memory_type);"
            )
        )
        await db.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_user_memories_embedding_hnsw
                ON user_memories
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
                """
            )
        )

        await db.commit()
        logger.info("Persistent Memory & Summarization schema migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(migrate_memory_schema())
