"""
Unit tests for Multi-Strategy Chunker.

Tests token counting, sliding-window overlap, page preservation,
Markdown breadcrumbs, Tabular column preservation, Code AST boundaries,
PDF layout filtering, and ChunkerFactory strategy resolution.
"""

import pytest

from app.services.chunker import (
    ChunkerFactory,
    CodeASTChunker,
    MarkdownChunker,
    PDFLayoutChunker,
    SemanticChunker,
    TabularChunker,
)


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


# ── Markdown Chunker Tests ───────────────────────────────────────────
def test_markdown_chunker_preserves_breadcrumbs() -> None:
    """MarkdownChunker must prepend header breadcrumbs to chunk content and metadata."""
    md_text = (
        "# System Architecture\n"
        "Overview of system.\n\n"
        "## Ingestion Pipeline\n"
        "Details of Celery workers.\n\n"
        "### RabbitMQ Broker\n"
        "Durable AMQP queue setup."
    )
    chunker = MarkdownChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk_page(md_text, page_number=1)

    assert len(chunks) >= 3
    # Check that breadcrumbs appear in chunk content or metadata
    last_chunk = chunks[-1]
    assert "RabbitMQ Broker" in last_chunk.content
    assert "breadcrumbs" in last_chunk.metadata
    assert "Ingestion Pipeline" in last_chunk.metadata["breadcrumbs"]


# ── Tabular Chunker Tests ────────────────────────────────────────────
def test_tabular_chunker_prepends_column_headers() -> None:
    """TabularChunker must prepend table headers to every partitioned batch of rows."""
    csv_text = (
        "id,name,role,salary\n"
        "1,Alice,Engineer,120000\n"
        "2,Bob,Architect,160000\n"
        "3,Charlie,Product,130000"
    )
    chunker = TabularChunker(chunk_size=40, chunk_overlap=0)
    chunks = chunker.chunk_page(csv_text, page_number=1)

    assert len(chunks) >= 1
    for chunk in chunks:
        assert "[Table Headers: id, name, role, salary]" in chunk.content
        assert chunk.metadata["strategy"] == "tabular"
        assert chunk.metadata["headers"] == ["id", "name", "role", "salary"]


# ── Code AST Chunker Tests ───────────────────────────────────────────
def test_code_ast_chunker_splits_on_functions() -> None:
    """CodeASTChunker should isolate top-level function/class definitions."""
    code_text = (
        "def calculate_total(a, b):\n"
        "    return a + b\n\n"
        "class DataProcessor:\n"
        "    def process(self, data):\n"
        "        return data.strip()\n"
    )
    chunker = CodeASTChunker(chunk_size=100, chunk_overlap=10)
    chunks = chunker.chunk_page(code_text, page_number=1)

    assert len(chunks) == 2
    assert "def calculate_total" in chunks[0].content
    assert "class DataProcessor" in chunks[1].content
    assert all(c.metadata["strategy"] == "code_ast" for c in chunks)


# ── PDF Layout Chunker Tests ─────────────────────────────────────────
def test_pdf_layout_chunker_filters_running_footers() -> None:
    """PDFLayoutChunker should filter out running footers like 'Page 1 of 5' and 'CONFIDENTIAL'."""
    pdf_text = (
        "CONFIDENTIAL\nMain section heading and content describing cloud architecture.\nPage 1 of 5"
    )
    chunker = PDFLayoutChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk_page(pdf_text, page_number=1)

    assert len(chunks) == 1
    assert "CONFIDENTIAL" not in chunks[0].content
    assert "Page 1 of 5" not in chunks[0].content
    assert "Main section heading" in chunks[0].content


# ── ChunkerFactory Tests ─────────────────────────────────────────────
def test_chunker_factory_resolves_correct_strategies() -> None:
    """ChunkerFactory must resolve proper subclass based on filename/mime_type."""
    assert isinstance(ChunkerFactory.get_chunker(filename="docs.md"), MarkdownChunker)
    assert isinstance(ChunkerFactory.get_chunker(filename="data.csv"), TabularChunker)
    assert isinstance(ChunkerFactory.get_chunker(filename="module.py"), CodeASTChunker)
    assert isinstance(ChunkerFactory.get_chunker(filename="manual.pdf"), PDFLayoutChunker)
    assert isinstance(ChunkerFactory.get_chunker(filename="notes.txt"), SemanticChunker)
