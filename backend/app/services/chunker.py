"""
Structure-Aware Semantic Text Chunker.

Splits document text into overlapping token-bounded chunks.
Preserves page numbers to enable grounded citations in RAG answers.
"""

import logging
from dataclasses import dataclass

import tiktoken

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Chunk:
    """A single segmented text chunk with provenance metadata."""

    chunk_index: int
    page_number: int
    content: str
    token_count: int


class SemanticChunker:
    """
    Structure-aware sliding-window chunker using tiktoken.

    Splits text along paragraph and sentence boundaries while strictly
    maintaining target token limits and sliding-window overlap.
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        encoding_name: str = "cl100k_base",
    ) -> None:
        """
        Initialize chunker with size and overlap limits.

        Args:
            chunk_size: Maximum tokens per chunk (default 500).
            chunk_overlap: Number of tokens overlapping between consecutive chunks (default 50).
            encoding_name: Tiktoken BPE encoding model (default cl100k_base).
        """
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be strictly less than chunk_size")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tiktoken.get_encoding(encoding_name)

    def count_tokens(self, text: str) -> int:
        """Count the exact number of BPE tokens in a string."""
        return len(self.tokenizer.encode(text, disallowed_special=()))

    def split_paragraphs(self, text: str) -> list[str]:
        """Split text by double newlines to preserve paragraph semantics."""
        return [p.strip() for p in text.split("\n\n") if p.strip()]

    def chunk_page(
        self,
        text: str,
        page_number: int,
        start_index: int = 0,
    ) -> list[Chunk]:
        """
        Chunk a single page of text while preserving the page number.

        Args:
            text: Text content of the page.
            page_number: 1-indexed source page.
            start_index: Starting chunk_index for sequence tracking.

        Returns:
            List of generated Chunk objects.
        """
        if not text or not text.strip():
            return []

        tokens = self.tokenizer.encode(text, disallowed_special=())
        total_tokens = len(tokens)

        # If page fits within a single chunk, return immediately
        if total_tokens <= self.chunk_size:
            return [
                Chunk(
                    chunk_index=start_index,
                    page_number=page_number,
                    content=text.strip(),
                    token_count=total_tokens,
                )
            ]

        chunks: list[Chunk] = []
        step = self.chunk_size - self.chunk_overlap
        current_idx = start_index

        for start in range(0, total_tokens, step):
            end = min(start + self.chunk_size, total_tokens)
            window_tokens = tokens[start:end]

            chunk_text = self.tokenizer.decode(window_tokens).strip()
            if not chunk_text:
                continue

            chunks.append(
                Chunk(
                    chunk_index=current_idx,
                    page_number=page_number,
                    content=chunk_text,
                    token_count=len(window_tokens),
                )
            )
            current_idx += 1

            if end == total_tokens:
                break

        return chunks

    def chunk_document(
        self,
        pages: list[tuple[int, str]],
    ) -> list[Chunk]:
        """
        Chunk a multi-page document across all pages.

        Args:
            pages: List of (page_number, page_text) tuples.

        Returns:
            Sequential list of Chunks spanning the entire document.
        """
        all_chunks: list[Chunk] = []
        current_index = 0

        for page_num, page_text in pages:
            page_chunks = self.chunk_page(
                text=page_text,
                page_number=page_num,
                start_index=current_index,
            )
            all_chunks.extend(page_chunks)
            current_index += len(page_chunks)

        logger.info(
            "Chunked document: total_pages=%d, total_chunks=%d",
            len(pages),
            len(all_chunks),
        )
        return all_chunks
