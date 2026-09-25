"""
Database Session Management.

Configures an asynchronous SQLAlchemy engine and session factory for PostgreSQL (Supabase).
Provides FastAPI dependency injection for database sessions.
"""

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

logger = logging.getLogger(__name__)


def get_async_database_url(url: str) -> str:
    """
    Ensure the database URL uses the asyncpg driver.

    Supabase provides URLs like:
        postgresql://postgres:...@db....supabase.co:5432/postgres
    SQLAlchemy async requires:
        postgresql+asyncpg://postgres:...@db....supabase.co:5432/postgres
    """
    if not url:
        return ""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


# Create async engine with connection pooling
async_db_url = get_async_database_url(settings.database_url)

# Only create pool if URL is configured
engine = (
    create_async_engine(
        async_db_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=settings.environment == "development",
    )
    if async_db_url
    else None
)

async_session_factory = (
    async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    if engine
    else None
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding an async database session.

    Transactions are scoped to the request:
    - Commits automatically on successful request completion.
    - Rolls back on unhandled exceptions.
    - Closes session when request completes.
    """
    if not async_session_factory:
        raise RuntimeError("DATABASE_URL is not configured. Database is unavailable.")

    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
