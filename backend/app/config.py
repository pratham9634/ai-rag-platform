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

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Candidate paths to locate .env whether running from project root or backend folder
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _BACKEND_DIR.parent
_CANDIDATE_ENVS = [
    _BACKEND_DIR / ".env",
    _ROOT_DIR / ".env",
    Path(".env"),
]
_ENV_FILES = [str(p) for p in _CANDIDATE_ENVS if p.is_file()]


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

    # ---------- Persistent Memory & Context Manager ----------
    max_recent_messages: int = Field(
        default=10,
        description="Number of recent messages to inject into context",
    )
    summary_message_threshold: int = Field(
        default=20,
        description="Trigger summarization when message threshold is reached",
    )
    max_memory_results: int = Field(
        default=5,
        description="Maximum semantic long-term user memories retrieved",
    )
    max_history_results: int = Field(
        default=5,
        description="Maximum relevant historical conversation turns retrieved",
    )
    max_rag_results: int = Field(
        default=5,
        description="Maximum RAG document chunks retrieved",
    )
    max_context_tokens: int = Field(
        default=6000,
        description="Maximum tokens allowed across all compiled context blocks",
    )
    memory_similarity_threshold: float = Field(
        default=0.60,
        description="Minimum cosine similarity for memory retrieval",
    )
    memory_dedup_threshold: float = Field(
        default=0.85,
        description="Cosine similarity threshold for superseding existing memories",
    )

    # ---------- OpenRouter ----------
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API key for LLM and embeddings",
    )

    # ---------- LangSmith ----------
    langchain_tracing_v2: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "LANGCHAIN_TRACING_V2",
            "langchain_tracing_v2",
            "LANGSMITH_TRACING_V2",
            "langsmith_tracing_v2",
            "LANGSMITH_TRACING",
            "langsmith_tracing",
        ),
        description="Enable LangSmith tracing",
    )
    langchain_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "LANGCHAIN_API_KEY",
            "langchain_api_key",
            "LANGSMITH_API_KEY",
            "langsmith_api_key",
        ),
        description="LangSmith API key",
    )
    langchain_project: str = Field(
        default="enterprise-rag",
        validation_alias=AliasChoices(
            "LANGCHAIN_PROJECT",
            "langchain_project",
            "LANGSMITH_PROJECT",
            "langsmith_project",
        ),
        description="LangSmith project name",
    )
    langsmith_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        validation_alias=AliasChoices(
            "LANGSMITH_ENDPOINT",
            "langsmith_endpoint",
            "LANGCHAIN_ENDPOINT",
            "langchain_endpoint",
        ),
        description="LangSmith endpoint URL",
    )

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES if _ENV_FILES else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# Singleton instance — imported throughout the app
settings = Settings()
