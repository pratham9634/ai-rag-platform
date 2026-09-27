"""
Unit tests for Hybrid Retrieval, RRF Fusion, and Reranking.
"""

from typing import Any

from app.services.reranker import RerankerService
from app.services.retrieval import RetrievalService


def test_reciprocal_rank_fusion_boosts_dual_matches() -> None:
    """Chunks appearing in both dense and sparse results must score higher than single matches."""
    dense_results = [
        {"id": "chunk-1", "document_id": "doc-a", "page_number": 1, "content": "RAG architecture"},
        {"id": "chunk-2", "document_id": "doc-b", "page_number": 2, "content": "Vector database"},
    ]
    sparse_results = [
        {"id": "chunk-1", "document_id": "doc-a", "page_number": 1, "content": "RAG architecture"},
        {"id": "chunk-3", "document_id": "doc-c", "page_number": 3, "content": "Lexical keyword"},
    ]

    fused = RetrievalService.reciprocal_rank_fusion(dense_results, sparse_results, k=60)

    # chunk-1 appears in both lists, so it must be rank 1 with the highest RRF score
    assert len(fused) == 3
    assert fused[0]["id"] == "chunk-1"
    assert fused[0]["score"] > fused[1]["score"]
    assert fused[0]["score"] > fused[2]["score"]


def test_reranker_scores_relevant_document_higher() -> None:
    """Reranker must assign significantly higher score to document with query keywords."""
    reranker = RerankerService()
    query = "tenant isolation and multi-tenancy"

    relevant_doc = "This platform enforces strict tenant isolation using server-derived tenant_id."
    irrelevant_doc = "Photosynthesis is the process used by plants to convert light into energy."

    score_rel = reranker.score_pair(query, relevant_doc)
    score_irrel = reranker.score_pair(query, irrelevant_doc)

    assert score_rel > score_irrel
    assert score_rel > 0.2
    assert score_irrel == 0.0


def test_reranker_truncates_to_top_k() -> None:
    """Reranker must return exactly top_k results sorted descending by score."""
    reranker = RerankerService()
    query = "database connection pooling"

    candidates: list[dict[str, Any]] = [
        {
            "id": f"chunk-{i}",
            "document_id": "doc-1",
            "page_number": i,
            "content": f"Text chunk {i} about database",
        }
        for i in range(10)
    ]

    results = reranker.rerank(query=query, candidates=candidates, top_k=3)

    assert len(results) == 3
    # Check descending score order
    assert results[0].relevance_score >= results[1].relevance_score >= results[2].relevance_score
