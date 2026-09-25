"""
Retrieval API Router.

Provides hybrid search endpoints for querying indexed documents with citations.
Enforces multi-tenant data isolation and supports BYOK API key overrides.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.documents import get_current_tenant_id
from app.database.session import get_db
from app.services.retrieval import RetrievalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])

# Singleton service instance
retrieval_service = RetrievalService()


# ── Schemas ──────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    """Hybrid retrieval search request."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language question or search query",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of highest-relevance chunks to return",
    )


class ChunkResultResponse(BaseModel):
    """A single retrieved and reranked context chunk."""

    chunk_id: str
    document_id: str
    page_number: int
    content: str
    relevance_score: float
    original_rank: int


class SearchResponse(BaseModel):
    """Hybrid search results response."""

    query: str
    total_results: int
    results: list[ChunkResultResponse]


# ── Endpoints ────────────────────────────────────────────────────────
@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Hybrid search across tenant documents",
)
async def hybrid_search_endpoint(
    request: SearchRequest,
    tenant_id: Annotated[str, Depends(get_current_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_openrouter_key: Annotated[
        str | None,
        Header(
            description="Optional user BYOK OpenRouter API key override",
        ),
    ] = None,
) -> Any:
    """
    Execute hybrid search over the active tenant's document chunks.

    Pipeline:
    1. Vectorizes query using dense embedding model.
    2. Executes dual-route retrieval (pgvector cosine + PostgreSQL FTS).
    3. Merges candidate rankings via Reciprocal Rank Fusion (RRF).
    4. Reranks candidates using Cross-Encoder contextual scoring.
    5. Returns top_k chunks with exact page numbers for citation grounding.
    """
    clean_query = request.query.strip()
    if not clean_query:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty or blank.",
        )

    try:
        ranked_chunks = await retrieval_service.hybrid_search(
            db=db,
            tenant_id=tenant_id,
            query=clean_query,
            top_k=request.top_k,
            api_key_override=x_openrouter_key,
        )

        return SearchResponse(
            query=clean_query,
            total_results=len(ranked_chunks),
            results=[
                ChunkResultResponse(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    page_number=r.page_number,
                    content=r.content,
                    relevance_score=r.relevance_score,
                    original_rank=r.original_rank,
                )
                for r in ranked_chunks
            ],
        )
    except Exception as e:
        logger.exception("Error executing hybrid search")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute search: {e}",
        ) from e
