"""
Unit tests for Jina AI Cross-Encoder Neural Reranker Service.

Tests local fallback, asynchronous API invocation, mocked Jina response mapping,
and graceful degradation under network failure.
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.reranker import RerankerService


def test_local_fallback_scoring_without_api_key() -> None:
    """When Jina API key is absent, local cross-attention scoring should run."""
    reranker = RerankerService(api_key="")
    query = "kubernetes pod scaling"

    doc_rel = "Kubernetes provides horizontal pod autoscaling based on CPU utilization."
    doc_irrel = "The recipe requires two cups of flour and one teaspoon of salt."

    score_rel = reranker.score_pair(query, doc_rel)
    score_irrel = reranker.score_pair(query, doc_irrel)

    assert score_rel > score_irrel
    assert score_rel > 0.2
    assert score_irrel == 0.0


def test_sync_rerank_preserves_top_k_order() -> None:
    """Synchronous rerank should output candidates ordered by relevance score."""
    reranker = RerankerService(api_key="")
    query = "tenant isolation"

    candidates: list[dict[str, Any]] = [
        {
            "id": "1",
            "document_id": "d1",
            "page_number": 1,
            "content": "Unrelated apples and oranges",
        },
        {
            "id": "2",
            "document_id": "d2",
            "page_number": 2,
            "content": "Strict tenant isolation in multi-tenant RAG",
        },
    ]

    results = reranker.rerank(query=query, candidates=candidates, top_k=2)

    assert len(results) == 2
    assert results[0].chunk_id == "2"
    assert results[0].relevance_score > results[1].relevance_score


@pytest.mark.asyncio
async def test_jina_api_mocked_success() -> None:
    """When Jina API succeeds, neural scores should be mapped back to candidates."""
    reranker = RerankerService(api_key="mock_jina_key")
    query = "financial revenue forecast"

    candidates = [
        {
            "id": "chunk-1",
            "document_id": "doc-1",
            "page_number": 1,
            "content": "Q3 Revenue reached 50M.",
        },
        {
            "id": "chunk-2",
            "document_id": "doc-2",
            "page_number": 2,
            "content": "Holiday party schedule.",
        },
    ]

    mock_response = {
        "model": "jina-reranker-v2-base-multilingual",
        "results": [
            {"index": 0, "relevance_score": 0.942},
            {"index": 1, "relevance_score": 0.081},
        ],
    }

    mock_http_response = httpx.Response(
        status_code=200,
        json=mock_response,
        request=httpx.Request("POST", "https://api.jina.ai/v1/rerank"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_http_response
        results = await reranker.rerank_async(query, candidates, top_k=2)

        assert len(results) == 2
        assert results[0].chunk_id == "chunk-1"
        assert results[0].relevance_score == 0.942
        assert results[1].chunk_id == "chunk-2"
        assert results[1].relevance_score == 0.081


@pytest.mark.asyncio
async def test_jina_api_network_error_triggers_fallback() -> None:
    """Network failure during Jina API call must gracefully fall back to local heuristic."""
    reranker = RerankerService(api_key="mock_jina_key")
    query = "multi-tenant security"

    candidates = [
        {
            "id": "chunk-sec",
            "document_id": "doc-1",
            "page_number": 1,
            "content": "Multi-tenant security measures.",
        },
        {
            "id": "chunk-food",
            "document_id": "doc-2",
            "page_number": 2,
            "content": "Pizza delivery menu.",
        },
    ]

    with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        results = await reranker.rerank_async(query, candidates, top_k=2)

        assert len(results) == 2
        # Local fallback should score security higher than food
        assert results[0].chunk_id == "chunk-sec"
        assert results[0].relevance_score > results[1].relevance_score
