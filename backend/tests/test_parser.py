"""
Unit tests for PDF Parser.

Tests magic-byte validation, text sanitization, and PyMuPDF page extraction.
"""

import fitz  # PyMuPDF
import pytest

from app.services.parser import InvalidPDFError, PDFParser


def create_sample_pdf_bytes(pages_text: list[str]) -> bytes:
    """Helper to generate an in-memory PDF with known text on each page."""
    doc = fitz.open()
    for text in pages_text:
        page = doc.new_page()
        page.insert_text((50, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def test_magic_bytes_valid() -> None:
    """Valid PDF starting with %PDF- should pass validation."""
    valid_header = b"%PDF-1.7\nSample content"
    PDFParser.validate_magic_bytes(valid_header)


def test_magic_bytes_invalid_raises_error() -> None:
    """Non-PDF binary stream must raise InvalidPDFError."""
    with pytest.raises(InvalidPDFError, match="Invalid PDF format"):
        PDFParser.validate_magic_bytes(b"GIF89a\x01\x00")


def test_magic_bytes_empty_raises_error() -> None:
    """Empty byte array must raise InvalidPDFError."""
    with pytest.raises(InvalidPDFError, match="Invalid PDF format"):
        PDFParser.validate_magic_bytes(b"")


def test_clean_text_normalizes_whitespace() -> None:
    """clean_text should strip control chars and collapse 3+ newlines to 2."""
    raw = "Paragraph 1\x00\n\n\n\nParagraph 2\r\n\r\nParagraph 3"
    cleaned = PDFParser.clean_text(raw)
    assert "\x00" not in cleaned
    assert "\n\n\n" not in cleaned
    assert "Paragraph 1\n\nParagraph 2\n\nParagraph 3" in cleaned


def test_parse_bytes_extracts_all_pages() -> None:
    """PDFParser should extract text with accurate 1-indexed page numbers."""
    page_1_text = "First page content for document citation testing."
    page_2_text = "Second page containing subsequent section details."

    pdf_bytes = create_sample_pdf_bytes([page_1_text, page_2_text])
    parsed = PDFParser.parse_bytes(pdf_bytes)

    assert parsed.total_pages == 2
    assert len(parsed.pages) == 2

    assert parsed.pages[0].page_number == 1
    assert "First page content" in parsed.pages[0].text

    assert parsed.pages[1].page_number == 2
    assert "Second page" in parsed.pages[1].text
