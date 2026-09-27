"""
Unit tests for Embedding Service.

Tests vector dimension, unit normalization, deterministic reproducibility, and batching.
"""

import math

import pytest

from app.services.embeddings import EmbeddingService


@pytest.mark.asyncio
async def test_embedding_dimension_and_normalization() -> None:
    """Generated embedding must have exactly 1536 dimensions and unit L2 norm."""
    service = EmbeddingService()
    vector = await service.generate_embedding("Test sentence for embedding validation.")

    assert len(vector) == 1536
    assert isinstance(vector[0], float)

    # Compute Euclidean L2 norm
    l2_norm = math.sqrt(sum(x * x for x in vector))
    assert pytest.approx(l2_norm, abs=1e-5) == 1.0


@pytest.mark.asyncio
async def test_deterministic_reproducibility() -> None:
    """Identical input texts must produce identical fallback embedding vectors."""
    service = EmbeddingService(api_key="sk-dummy")
    text = "Enterprise RAG multi-tenant architecture."

    v1 = await service.generate_embedding(text)
    v2 = await service.generate_embedding(text)

    assert v1 == v2


@pytest.mark.asyncio
async def test_distinct_texts_produce_different_embeddings() -> None:
    """Different inputs must produce distinct vectors."""
    service = EmbeddingService()
    v1 = await service.generate_embedding("PostgreSQL pgvector search")
    v2 = await service.generate_embedding("Cooking chocolate chip cookies")

    assert v1 != v2


@pytest.mark.asyncio
async def test_batch_embeddings_generation() -> None:
    """Batch generation should return one 1536-dim vector per input string."""
    service = EmbeddingService()
    texts = ["First document text", "Second document text", "Third document text"]

    batch = await service.generate_embeddings_batch(texts)

    assert len(batch) == 3
    for vec in batch:
        assert len(vec) == 1536
        assert pytest.approx(math.sqrt(sum(x * x for x in vec)), abs=1e-5) == 1.0
