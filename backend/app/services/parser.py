"""
PDF Parsing Engine using PyMuPDF (fitz).

Extracts clean text and structural metadata page-by-page from raw PDF bytes.
Preserves page coordinates and numbers to ground RAG citations.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class PDFParsingError(Exception):
    """Base exception for PDF parsing failures."""

    pass


class PDFEncryptedError(PDFParsingError):
    """Raised when a PDF is password-protected and cannot be extracted."""

    pass


class InvalidPDFError(PDFParsingError):
    """Raised when the uploaded file is not a valid PDF."""

    pass


@dataclass(frozen=True)
class ParsedPage:
    """Represents a single parsed page from a document."""

    page_number: int  # 1-based index
    text: str
    char_count: int


@dataclass
class ParsedDocument:
    """Represents the complete parsed output of a document."""

    total_pages: int
    pages: list[ParsedPage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    total_characters: int = 0


class PDFParser:
    """High-performance PDF parser using PyMuPDF."""

    @staticmethod
    def validate_magic_bytes(pdf_bytes: bytes) -> None:
        """Verify the byte stream begins with the standard PDF file header."""
        if not pdf_bytes or not pdf_bytes.startswith(b"%PDF-"):
            raise InvalidPDFError(
                "Invalid PDF format: file header does not match %PDF- magic bytes."
            )

    @classmethod
    def clean_text(cls, raw_text: str) -> str:
        """
        Normalize extracted text.

        - Replaces excessive consecutive blank lines with double newlines.
        - Strips null bytes and unusual control characters while keeping standard whitespace.
        """
        # Remove null bytes and non-printable control chars except \n, \t, \r
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", raw_text)
        # Normalize carriage returns
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Collapse 3+ consecutive newlines into 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @classmethod
    def parse_bytes(cls, pdf_bytes: bytes) -> ParsedDocument:
        """
        Parse raw PDF bytes into structured pages.

        Args:
            pdf_bytes: Raw binary content of the PDF file.

        Returns:
            ParsedDocument containing per-page text and document metadata.

        Raises:
            InvalidPDFError: If bytes do not represent a valid PDF.
            PDFEncryptedError: If PDF requires a password.
            PDFParsingError: If unhandled extraction error occurs.
        """
        cls.validate_magic_bytes(pdf_bytes)

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as e:
            raise InvalidPDFError(f"Failed to open PDF document: {e}") from e

        try:
            if doc.is_encrypted:
                raise PDFEncryptedError(
                    "Password-protected PDFs cannot be processed. Please unlock the file first."
                )

            total_pages = len(doc)
            parsed_pages: list[ParsedPage] = []
            total_chars = 0

            for page_index in range(total_pages):
                page = doc[page_index]
                # Extract text using PyMuPDF's fast native text layout
                raw_text = page.get_text("text") or ""
                cleaned = cls.clean_text(raw_text)

                parsed_page = ParsedPage(
                    page_number=page_index + 1,  # 1-indexed for citations
                    text=cleaned,
                    char_count=len(cleaned),
                )
                parsed_pages.append(parsed_page)
                total_chars += len(cleaned)

            # Extract basic document metadata
            doc_metadata = doc.metadata or {}
            sanitized_meta = {
                "title": doc_metadata.get("title", ""),
                "author": doc_metadata.get("author", ""),
                "creator": doc_metadata.get("creator", ""),
                "producer": doc_metadata.get("producer", ""),
            }

            logger.info(
                "Parsed PDF: pages=%d, total_characters=%d",
                total_pages,
                total_chars,
            )

            return ParsedDocument(
                total_pages=total_pages,
                pages=parsed_pages,
                metadata=sanitized_meta,
                total_characters=total_chars,
            )
        finally:
            doc.close()
