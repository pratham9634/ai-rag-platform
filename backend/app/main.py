"""
Enterprise RAG Platform — FastAPI Application Entry Point

This is the main FastAPI application that serves as the backend for the
Enterprise RAG Platform. It handles:
- API routing
- CORS configuration
- Middleware setup
- Application lifecycle events

Architecture:
    Next.js Frontend → FastAPI Backend → Supabase / Redis / OpenRouter
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.health import router as health_router

# ── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Application Lifecycle ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle manager.

    Startup: Initialize connections (Redis, DB, etc.)
    Shutdown: Clean up connections gracefully.

    Using lifespan instead of deprecated @app.on_event("startup")
    because lifespan is the modern FastAPI pattern that properly
    manages async resources and ensures cleanup on shutdown.
    """
    # ── Startup ──
    logger.info(
        "Starting Enterprise RAG API | env=%s",
        settings.environment,
    )
    yield
    # ── Shutdown ──
    logger.info("Shutting down Enterprise RAG API")


# ── FastAPI App ──────────────────────────────────────────────────────
app = FastAPI(
    title="Enterprise RAG Platform",
    description="Multi-tenant Agentic RAG platform with hybrid retrieval, "
    "reranking, BYOK, and tenant isolation.",
    version="0.1.0",
    lifespan=lifespan,
    # Don't expose docs in production
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url="/redoc" if settings.environment != "production" else None,
)


# ── CORS Middleware ──────────────────────────────────────────────────
# Why CORS?
# The frontend (Next.js on :3000) makes requests to the backend (:8000).
# Browsers block cross-origin requests by default. CORS headers tell the
# browser which origins are allowed.
#
# Security: We restrict to specific origins — no wildcard (*) in production.
cors_origins = [
    origin.strip()
    for origin in settings.backend_cors_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)


# ── Routers ──────────────────────────────────────────────────────────
app.include_router(health_router)
