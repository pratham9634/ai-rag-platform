"""
Hybrid Retrieval Engine.

Combines Dense Semantic Search (pgvector cosine similarity) with Sparse Lexical Search
(PostgreSQL Full-Text Search) using Reciprocal Rank Fusion (RRF) and Cross-Encoder Reranking.
Enforces strict multi-tenant isolation on all queries.
"""

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import DocumentChunk
from app.services.embeddings import EmbeddingService
from app.services.reranker import RerankerService, RerankResult

logger = logging.getLogger(__name__)

# RRF smoothing constant (standard IR benchmark default)
RRF_K = 60


class RetrievalService:
    """Orchestrates hybrid retrieval, reciprocal rank fusion, and reranking."""

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        reranker_service: RerankerService | None = None,
    ) -> None:
        self.embedding_service = embedding_service or EmbeddingService()
        self.reranker_service = reranker_service or RerankerService()

    @staticmethod
    def reciprocal_rank_fusion(
        dense_results: list[dict[str, Any]],
        sparse_results: list[dict[str, Any]],
        k: int = RRF_K,
    ) -> list[dict[str, Any]]:
        """
        Merge ranked lists from dense and sparse search using Reciprocal Rank Fusion.

        Formula: Score(d) = SUM( 1 / (k + rank_i(d)) )

        Args:
            dense_results: Ranked list from dense vector search.
            sparse_results: Ranked list from lexical keyword search.
            k: Smoothing constant to avoid dominance by top ranks.

        Returns:
            Unified list of chunk candidates sorted by descending RRF score.
        """
        scores: dict[str, float] = defaultdict(float)
        chunk_map: dict[str, dict[str, Any]] = {}

        # Accumulate dense ranks
        for rank, item in enumerate(dense_results):
            cid = str(item["id"])
            scores[cid] += 1.0 / (k + (rank + 1))
            chunk_map[cid] = item

        # Accumulate sparse ranks
        for rank, item in enumerate(sparse_results):
            cid = str(item["id"])
            scores[cid] += 1.0 / (k + (rank + 1))
            if cid not in chunk_map:
                chunk_map[cid] = item

        # Build fused list
        fused: list[dict[str, Any]] = []
        for cid, rrf_score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            entry = dict(chunk_map[cid])
            entry["score"] = rrf_score
            fused.append(entry)

        return fused

    async def search_dense(
        self,
        db: AsyncSession,
        tenant_id: str,
        query_embedding: list[float],
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Perform dense semantic search using pgvector cosine distance.

        Strict tenant filter: WHERE tenant_id = :tenant_id
        """
        # Distance operator <=> is cosine distance; similarity = 1 - distance
        try:
            query = (
                select(
                    DocumentChunk.id,
                    DocumentChunk.document_id,
                    DocumentChunk.page_number,
                    DocumentChunk.content,
                    (1 - DocumentChunk.embedding.cosine_distance(query_embedding)).label(
                        "similarity"
                    ),
                )
                .where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.embedding.is_not(None),
                )
                .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
                .limit(limit)
            )

            result = await db.execute(query)
            rows = result.all()

            return [
                {
                    "id": row.id,
                    "document_id": row.document_id,
                    "page_number": row.page_number,
                    "content": row.content,
                    "similarity": float(row.similarity) if row.similarity is not None else 0.0,
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning(
                "Dense search error (possibly table empty or pgvector uninitialized): %s",
                str(e),
            )
            return []

    async def search_sparse(
        self,
        db: AsyncSession,
        tenant_id: str,
        query_text: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Perform sparse lexical search using PostgreSQL Full-Text Search.

        Falls back to ILIKE if full-text index is not yet built.
        Strict tenant filter: WHERE tenant_id = :tenant_id
        """
        try:
            # First try PostgreSQL FTS websearch_to_tsquery
            fts_query = text(
                """
                SELECT id, document_id, page_number, content,
                       ts_rank_cd(tsv, websearch_to_tsquery('english', :q)) AS rank
                FROM document_chunks
                WHERE tenant_id = :tenant_id
                  AND tsv @@ websearch_to_tsquery('english', :q)
                ORDER BY rank DESC
                LIMIT :limit
                """
            )
            result = await db.execute(
                fts_query,
                {"tenant_id": tenant_id, "q": query_text, "limit": limit},
            )
            rows = result.all()

            if rows:
                return [
                    {
                        "id": row.id,
                        "document_id": row.document_id,
                        "page_number": row.page_number,
                        "content": row.content,
                        "rank": float(row.rank),
                    }
                    for row in rows
                ]
        except Exception:
            logger.debug("PostgreSQL FTS unavailable; falling back to ILIKE query")

        # Fallback to ILIKE keyword search
        try:
            query = (
                select(
                    DocumentChunk.id,
                    DocumentChunk.document_id,
                    DocumentChunk.page_number,
                    DocumentChunk.content,
                )
                .where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.content.ilike(f"%{query_text}%"),
                )
                .limit(limit)
            )
            result = await db.execute(query)
            rows = result.all()

            return [
                {
                    "id": row.id,
                    "document_id": row.document_id,
                    "page_number": row.page_number,
                    "content": row.content,
                    "rank": 1.0,
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning("Sparse lexical search error: %s", str(e))
            return []

    async def hybrid_search(
        self,
        db: AsyncSession,
        tenant_id: str,
        query: str,
        top_k: int = 5,
        api_key_override: str | None = None,
    ) -> list[RerankResult]:
        """
        Execute full hybrid search pipeline:
        1. Embed user query into dense vector.
        2. Concurrently fetch top-20 dense and top-20 sparse candidates.
        3. Merge candidate pools via Reciprocal Rank Fusion (RRF).
        4. Cross-encode and rerank top candidates.
        5. Return the top_k grounded chunks.
        """
        if not query or not query.strip():
            return []

        # 1. Generate query embedding
        query_embedding = await self.embedding_service.generate_embedding(
            query, api_key_override=api_key_override
        )

        # 2. Retrieve dense and sparse candidates
        dense_candidates = await self.search_dense(
            db=db,
            tenant_id=tenant_id,
            query_embedding=query_embedding,
            limit=20,
        )

        sparse_candidates = await self.search_sparse(
            db=db,
            tenant_id=tenant_id,
            query_text=query,
            limit=20,
        )

        # 3. Fuse rankings via RRF
        fused_candidates = self.reciprocal_rank_fusion(
            dense_results=dense_candidates,
            sparse_results=sparse_candidates,
        )

        # 4. Rerank top candidates for final precision
        reranked = self.reranker_service.rerank(
            query=query,
            candidates=fused_candidates,
            top_k=top_k,
        )

        logger.info(
            "Hybrid search completed: tenant=%s, dense=%d, sparse=%d, fused=%d, top_k=%d",
            tenant_id,
            len(dense_candidates),
            len(sparse_candidates),
            len(fused_candidates),
            len(reranked),
        )

        return reranked
