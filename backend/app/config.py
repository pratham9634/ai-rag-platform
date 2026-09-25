"""
Enterprise RAG Platform — Application Configuration

Uses Pydantic Settings to load configuration from environment variables.
All secrets come from .env (never hardcoded, never committed).

Why Pydantic Settings?
- Type-safe configuration with validation
- Automatic loading from environment variables
- Clear documentation of what the app needs
- Fails fast if required config is missing
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ---------- App ----------
    environment: str = Field(default="development", description="Runtime environment")
    log_level: str = Field(default="INFO", description="Logging level")
    backend_cors_origins: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of allowed CORS origins",
    )

    # ---------- Clerk ----------
    clerk_secret_key: str = Field(
        default="",
        description="Clerk secret key for JWT verification (server-only)",
    )

    # ---------- Supabase ----------
    supabase_url: str = Field(default="", description="Supabase project URL")
    supabase_service_role_key: str = Field(
        default="",
        description="Supabase service role key (server-only, bypasses RLS)",
    )
    database_url: str = Field(
        default="",
        description="PostgreSQL connection string for SQLAlchemy",
    )
    supabase_storage_bucket: str = Field(
        default="documents",
        description="Supabase Storage bucket name for uploaded files",
    )

    # ---------- Redis ----------
    redis_url: str = Field(
        default="redis://redis:6379/0",
        description="Redis connection URL",
    )

    # ---------- OpenRouter ----------
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key for LLM and embeddings",
    )

    # ---------- LangSmith ----------
    langchain_tracing_v2: bool = Field(
        default=False,
        description="Enable LangSmith tracing",
    )
    langchain_api_key: str = Field(
        default="",
        description="LangSmith API key",
    )
    langchain_project: str = Field(
        default="enterprise-rag",
        description="LangSmith project name",
    )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton instance — imported throughout the app
settings = Settings()
