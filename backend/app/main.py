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

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.retrieval import router as retrieval_router
from app.auth.sanitizer import install_log_sanitizer, sanitize_text
from app.config import settings
from app.observability.tracer import configure_langsmith_tracing
from app.workers.cleanup_service import start_periodic_cleanup_loop

# ── Logging & Secret Scrubbing ───────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
install_log_sanitizer()
logger = logging.getLogger(__name__)


# ── Application Lifecycle ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifecycle manager.

    Startup: Initialize connections (Redis, DB, etc.) and security filters.
    Shutdown: Clean up connections gracefully.
    """
    # ── Startup ──
    install_log_sanitizer()
    configure_langsmith_tracing()
    logger.info(
        "Starting Enterprise RAG API | env=%s",
        settings.environment,
    )
    cleanup_task = None
    if settings.environment != "test":
        cleanup_task = asyncio.create_task(start_periodic_cleanup_loop(interval_seconds=3600))

    yield

    # ── Shutdown ──
    if cleanup_task:
        cleanup_task.cancel()
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


# ── Safe Error Handlers (Security Hardening) ──────────────────────────
@app.exception_handler(HTTPException)
async def sanitized_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Sanitize any potential keys or sensitive strings in HTTP errors."""
    sanitized_detail = sanitize_text(str(exc.detail)) if isinstance(exc.detail, str) else exc.detail
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": sanitized_detail},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all unhandled exception handler.
    Prevents leakage of internal stack traces, DB connection strings, or system paths.
    """
    logger.error("Unhandled server exception: %s", sanitize_text(str(exc)), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred. Please contact support.",
            "code": "INTERNAL_SERVER_ERROR",
        },
    )


# ── CORS Middleware ──────────────────────────────────────────────────
# Why CORS?
# The frontend (Next.js on :3000) makes requests to the backend (:8000).
# Browsers block cross-origin requests by default. CORS headers tell the
# browser which origins are allowed.
#
# Security: We restrict to specific origins — no wildcard (*) in production.
cors_origins = [
    origin.strip() for origin in settings.backend_cors_origins.split(",") if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)


# ── Routers ──────────────────────────────────────────────────────────
@app.get("/", tags=["root"])
async def root() -> dict[str, str]:
    """Root welcome endpoint providing service status and documentation links."""
    return {
        "service": "Enterprise RAG Platform API",
        "version": "0.1.0",
        "status": "online",
        "docs_url": "/docs",
        "health_url": "/health",
    }


app.include_router(health_router)
app.include_router(documents_router)
app.include_router(retrieval_router)
app.include_router(chat_router)
