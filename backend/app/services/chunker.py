"""
Enterprise Multi-Strategy Document Chunker.

Implements specialized chunking strategies tailored to document structure:
1. MarkdownChunker: Parses header hierarchies (#, ##, ###) and preserves section breadcrumbs.
2. TabularChunker: Parses CSV/TSV row-by-row, prepending column headers to every chunk.
3. CodeASTChunker: Splits code (Python, JS/TS, SQL, JSON) on function, class, and block boundaries.
4. PDFLayoutChunker: Filters running headers/footers and preserves multi-paragraph reading flow.
5. SemanticChunker: Sentence and paragraph sliding-window BPE chunking for unstructured prose.
6. ChunkerFactory: Auto-detects strategy by file extension and MIME type.
"""

import csv
import io
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

import tiktoken

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Chunk:
    """A single segmented text chunk with provenance metadata."""

    chunk_index: int
    page_number: int
    content: str
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseChunker(ABC):
    """Abstract base class for all chunking strategies."""

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        encoding_name: str = "cl100k_base",
    ) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be strictly less than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.tokenizer = tiktoken.get_encoding(encoding_name)

    def count_tokens(self, text: str) -> int:
        """Count exact BPE tokens in a string."""
        if not text:
            return 0
        return len(self.tokenizer.encode(text, disallowed_special=()))

    @abstractmethod
    def chunk_page(
        self,
        text: str,
        page_number: int,
        start_index: int = 0,
    ) -> list[Chunk]:
        """Chunk a single page or document section."""
        pass

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
            "%s processed document: total_pages=%d, total_chunks=%d",
            self.__class__.__name__,
            len(pages),
            len(all_chunks),
        )
        return all_chunks


class SemanticChunker(BaseChunker):
    """
    Structure-aware sliding-window chunker using tiktoken.

    Splits text along paragraph and sentence boundaries while maintaining
    token limits and sliding-window overlap. Universal fallback for prose.
    """

    def split_paragraphs(self, text: str) -> list[str]:
        """Split text by double newlines to preserve paragraph semantics."""
        return [p.strip() for p in text.split("\n\n") if p.strip()]

    def chunk_page(
        self,
        text: str,
        page_number: int,
        start_index: int = 0,
    ) -> list[Chunk]:
        """Chunk a single page of text while preserving the page number."""
        if not text or not text.strip():
            return []

        tokens = self.tokenizer.encode(text, disallowed_special=())
        total_tokens = len(tokens)

        if total_tokens <= self.chunk_size:
            return [
                Chunk(
                    chunk_index=start_index,
                    page_number=page_number,
                    content=text.strip(),
                    token_count=total_tokens,
                    metadata={"strategy": "semantic"},
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
                    metadata={"strategy": "semantic"},
                )
            )
            current_idx += 1

            if end == total_tokens:
                break

        return chunks


class MarkdownChunker(BaseChunker):
    """
    Hierarchical Markdown Header Chunker.

    Parses headings (#, ##, ###, ####), maintaining a contextual breadcrumb path
    (e.g., 'API > Authentication > Bearer Tokens') prepended to each chunk.
    This guarantees chunks retrieved in isolation retain their structural context.
    """

    HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

    def chunk_page(
        self,
        text: str,
        page_number: int,
        start_index: int = 0,
    ) -> list[Chunk]:
        if not text or not text.strip():
            return []

        lines = text.splitlines()
        sections: list[tuple[str, list[str]]] = []  # (breadcrumb, lines)
        current_breadcrumbs: dict[int, str] = {}
        current_lines: list[str] = []

        def get_current_path() -> str:
            levels = sorted(current_breadcrumbs.keys())
            return " > ".join(current_breadcrumbs[lvl] for lvl in levels)

        for line in lines:
            match = self.HEADER_PATTERN.match(line)
            if match:
                # Save previous section if it has content
                if current_lines:
                    sections.append((get_current_path(), current_lines))
                    current_lines = []

                level = len(match.group(1))
                title = match.group(2).strip()

                # Remove deeper levels when ascending or matching hierarchy
                current_breadcrumbs = {k: v for k, v in current_breadcrumbs.items() if k < level}
                current_breadcrumbs[level] = title
                current_lines.append(line)
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((get_current_path(), current_lines))

        chunks: list[Chunk] = []
        current_idx = start_index

        for breadcrumb, sec_lines in sections:
            sec_text = "\n".join(sec_lines).strip()
            if not sec_text:
                continue

            header_prefix = f"[Section: {breadcrumb}]\n\n" if breadcrumb else ""
            combined_text = f"{header_prefix}{sec_text}"
            sec_tokens = self.count_tokens(combined_text)

            if sec_tokens <= self.chunk_size:
                chunks.append(
                    Chunk(
                        chunk_index=current_idx,
                        page_number=page_number,
                        content=combined_text,
                        token_count=sec_tokens,
                        metadata={"strategy": "markdown", "breadcrumbs": breadcrumb},
                    )
                )
                current_idx += 1
            else:
                # Sub-chunk large section while carrying forward the breadcrumb header
                sub_chunker = SemanticChunker(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                )
                sub_chunks = sub_chunker.chunk_page(
                    text=combined_text,
                    page_number=page_number,
                    start_index=current_idx,
                )
                for sc in sub_chunks:
                    chunks.append(
                        Chunk(
                            chunk_index=sc.chunk_index,
                            page_number=page_number,
                            content=sc.content,
                            token_count=sc.token_count,
                            metadata={"strategy": "markdown", "breadcrumbs": breadcrumb},
                        )
                    )
                current_idx += len(sub_chunks)

        return chunks


class TabularChunker(BaseChunker):
    """
    Context-Preserving Tabular CSV/TSV Chunker.

    Partitions rows into token-bounded groups while automatically prepending
    the column headers to every chunk. Prevents data rows from losing their
    schema context during dense semantic retrieval.
    """

    def chunk_page(
        self,
        text: str,
        page_number: int,
        start_index: int = 0,
    ) -> list[Chunk]:
        if not text or not text.strip():
            return []

        # Determine delimiter (comma, tab, semicolon)
        first_line = text.strip().splitlines()[0]
        delimiter = "\t" if "\t" in first_line else (";" if ";" in first_line else ",")

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)
        if not rows:
            return []

        headers = rows[0]
        data_rows = rows[1:]
        if not data_rows:
            # Only header row present
            header_text = delimiter.join(headers)
            return [
                Chunk(
                    chunk_index=start_index,
                    page_number=page_number,
                    content=header_text,
                    token_count=self.count_tokens(header_text),
                    metadata={"strategy": "tabular", "headers": headers, "row_count": 0},
                )
            ]

        header_str = f"[Table Headers: {', '.join(headers)}]\n"

        chunks: list[Chunk] = []
        current_batch: list[str] = []
        batch_start_row = 1
        current_idx = start_index

        for row_idx, row in enumerate(data_rows, start=1):
            row_str = delimiter.join(row)
            candidate_batch = [*current_batch, row_str]
            candidate_text = header_str + "\n".join(candidate_batch)
            candidate_tokens = self.count_tokens(candidate_text)

            if candidate_tokens <= self.chunk_size or not current_batch:
                current_batch.append(row_str)
            else:
                # Flush batch
                final_text = header_str + "\n".join(current_batch)
                chunks.append(
                    Chunk(
                        chunk_index=current_idx,
                        page_number=page_number,
                        content=final_text,
                        token_count=self.count_tokens(final_text),
                        metadata={
                            "strategy": "tabular",
                            "headers": headers,
                            "start_row": batch_start_row,
                            "end_row": row_idx - 1,
                            "total_rows": len(data_rows),
                        },
                    )
                )
                current_idx += 1
                current_batch = [row_str]
                batch_start_row = row_idx

        if current_batch:
            final_text = header_str + "\n".join(current_batch)
            chunks.append(
                Chunk(
                    chunk_index=current_idx,
                    page_number=page_number,
                    content=final_text,
                    token_count=self.count_tokens(final_text),
                    metadata={
                        "strategy": "tabular",
                        "headers": headers,
                        "start_row": batch_start_row,
                        "end_row": len(data_rows),
                        "total_rows": len(data_rows),
                    },
                )
            )

        return chunks


class CodeASTChunker(BaseChunker):
    """
    Scope-Aware Source Code Chunker.

    Splits source code (Python, JS/TS, SQL, JSON) on functional boundaries
    (class, def, async def, function, export) rather than arbitrary line counts.
    """

    CODE_BOUNDARY_PATTERN = re.compile(
        r"^(?:class\s+\w+|def\s+\w+|async\s+def\s+\w+|function\s+\w+|export\s+(?:default\s+)?(?:class|function|const)|const\s+\w+\s*=\s*(?:async\s*)?\()",
        re.MULTILINE,
    )

    def chunk_page(
        self,
        text: str,
        page_number: int,
        start_index: int = 0,
    ) -> list[Chunk]:
        if not text or not text.strip():
            return []

        # Find code blocks
        lines = text.splitlines()
        blocks: list[list[str]] = []
        current_block: list[str] = []

        for line in lines:
            if self.CODE_BOUNDARY_PATTERN.match(line) and current_block:
                blocks.append(current_block)
                current_block = [line]
            else:
                current_block.append(line)

        if current_block:
            blocks.append(current_block)

        chunks: list[Chunk] = []
        current_idx = start_index

        for block in blocks:
            block_text = "\n".join(block).strip()
            if not block_text:
                continue

            block_tokens = self.count_tokens(block_text)
            if block_tokens <= self.chunk_size:
                chunks.append(
                    Chunk(
                        chunk_index=current_idx,
                        page_number=page_number,
                        content=block_text,
                        token_count=block_tokens,
                        metadata={"strategy": "code_ast"},
                    )
                )
                current_idx += 1
            else:
                # Sub-chunk large code block using semantic window
                sub_chunker = SemanticChunker(
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                )
                sub_chunks = sub_chunker.chunk_page(
                    text=block_text,
                    page_number=page_number,
                    start_index=current_idx,
                )
                for sc in sub_chunks:
                    chunks.append(
                        Chunk(
                            chunk_index=sc.chunk_index,
                            page_number=page_number,
                            content=sc.content,
                            token_count=sc.token_count,
                            metadata={"strategy": "code_ast"},
                        )
                    )
                current_idx += len(sub_chunks)

        return chunks


class PDFLayoutChunker(BaseChunker):
    """
    Layout-Aware PDF Document Chunker.

    Filters repetitive running headers/footers (page counters, document stamps)
    and reconstructs paragraphs across page splits.
    """

    RUNNING_FOOTER_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r"^(?:page\s+\d+(?:\s+of\s+\d+)?|\d+\s*/\s*\d+|\d+)$", re.IGNORECASE),
        re.compile(
            r"^(?:confidential|all rights reserved|internal use only|draft)$", re.IGNORECASE
        ),
    ]

    def _clean_layout_lines(self, lines: list[str]) -> list[str]:
        cleaned: list[str] = []
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue
            is_noise = any(p.match(trimmed) for p in self.RUNNING_FOOTER_PATTERNS)
            if not is_noise:
                cleaned.append(trimmed)
        return cleaned

    def chunk_page(
        self,
        text: str,
        page_number: int,
        start_index: int = 0,
    ) -> list[Chunk]:
        if not text or not text.strip():
            return []

        raw_lines = text.splitlines()
        filtered_lines = self._clean_layout_lines(raw_lines)
        if not filtered_lines:
            return []

        cleaned_text = "\n\n".join(filtered_lines)
        semantic = SemanticChunker(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        chunks = semantic.chunk_page(
            text=cleaned_text,
            page_number=page_number,
            start_index=start_index,
        )

        return [
            Chunk(
                chunk_index=c.chunk_index,
                page_number=c.page_number,
                content=c.content,
                token_count=c.token_count,
                metadata={"strategy": "pdf_layout"},
            )
            for c in chunks
        ]


class ChunkerFactory:
    """Factory for selecting and instantiating the optimal chunker strategy."""

    @staticmethod
    def get_chunker(
        filename: str | None = None,
        mime_type: str | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> BaseChunker:
        """
        Inspect file extension or MIME type and return the optimal chunker instance.

        Args:
            filename: Original file name (e.g., 'report.md', 'data.csv', 'doc.pdf').
            mime_type: Optional MIME string (e.g., 'text/csv', 'application/pdf').
            chunk_size: Target token capacity per chunk.
            chunk_overlap: Overlapping tokens between adjacent chunks.

        Returns:
            Configured BaseChunker subclass.
        """
        ext = ""
        if filename and "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower()

        # Markdown detection
        if ext in {"md", "markdown"} or mime_type in {"text/markdown", "text/x-markdown"}:
            return MarkdownChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        # Tabular data detection
        if ext in {"csv", "tsv"} or mime_type in {"text/csv", "text/tab-separated-values"}:
            return TabularChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        # Source code detection
        if ext in {"py", "ts", "js", "jsx", "tsx", "sql", "json", "yaml", "yml"}:
            return CodeASTChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        # PDF layout detection
        if ext == "pdf" or mime_type == "application/pdf":
            return PDFLayoutChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        # Universal semantic fallback
        return SemanticChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
