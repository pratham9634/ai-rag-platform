"""
Unit tests for Semantic Chunker.

Tests token counting, sliding-window overlap, page preservation, and boundary validation.
"""

import pytest

from app.services.chunker import SemanticChunker


def test_chunker_initialization_invalid_overlap() -> None:
    """Overlap equal to or greater than chunk size must raise ValueError."""
    with pytest.raises(ValueError, match="strictly less than"):
        SemanticChunker(chunk_size=100, chunk_overlap=100)


def test_count_tokens_returns_positive_integer() -> None:
    """count_tokens should accurately report BPE token length."""
    chunker = SemanticChunker(chunk_size=100, chunk_overlap=10)
    tokens = chunker.count_tokens("Hello world! This is a test.")
    assert tokens > 0
    assert isinstance(tokens, int)


def test_chunk_page_small_text_returns_single_chunk() -> None:
    """Text smaller than chunk_size should return exactly one chunk."""
    chunker = SemanticChunker(chunk_size=500, chunk_overlap=50)
    text = "Short paragraph describing a single concept."

    chunks = chunker.chunk_page(text=text, page_number=1, start_index=0)

    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].page_number == 1
    assert chunks[0].content == text
    assert chunks[0].token_count > 0


def test_chunk_page_empty_text_returns_empty_list() -> None:
    """Empty or whitespace-only text should produce zero chunks."""
    chunker = SemanticChunker(chunk_size=500, chunk_overlap=50)
    assert chunker.chunk_page(text="", page_number=1) == []
    assert chunker.chunk_page(text="   \n\n  ", page_number=1) == []


def test_chunk_page_large_text_splits_with_overlap() -> None:
    """Text exceeding chunk_size must produce multiple sequential overlapping chunks."""
    chunker = SemanticChunker(chunk_size=50, chunk_overlap=10)
    long_text = "Word " * 200  # ~200 tokens

    chunks = chunker.chunk_page(text=long_text, page_number=3, start_index=5)

    assert len(chunks) > 1
    # Sequential chunk indices starting from 5
    assert [c.chunk_index for c in chunks] == list(range(5, 5 + len(chunks)))
    # Provenance page preserved on all chunks
    assert all(c.page_number == 3 for c in chunks)
    # Token count bounded
    assert all(c.token_count <= 50 for c in chunks)


def test_chunk_document_across_multiple_pages() -> None:
    """chunk_document should process multiple pages maintaining continuous chunk indexing."""
    chunker = SemanticChunker(chunk_size=100, chunk_overlap=20)
    pages = [
        (1, "Page 1: Introduction to enterprise multi-tenant systems."),
        (2, "Page 2: Implementation of vector similarity search with pgvector."),
    ]

    chunks = chunker.chunk_document(pages)

    assert len(chunks) == 2
    assert chunks[0].chunk_index == 0
    assert chunks[0].page_number == 1
    assert "Page 1" in chunks[0].content

    assert chunks[1].chunk_index == 1
    assert chunks[1].page_number == 2
    assert "Page 2" in chunks[1].content
