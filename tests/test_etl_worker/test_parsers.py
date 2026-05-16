"""Tests for etl_worker.parsers module."""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from etl_worker.parsers import (
    compute_hash,
    detect_format,
    parse_docx,
    parse_pdf,
    parse_text,
)


# ── parse_text ─────────────────────────────────────────────────────────────────

def test_parse_text_returns_page_dict():
    data = b"Hello world\nSecond line"
    result = parse_text(data)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["page"] == 1
    assert "Hello world" in result[0]["text"]
    assert "Second line" in result[0]["text"]


def test_parse_text_empty():
    result = parse_text(b"")
    assert result == [{"page": 1, "text": ""}]


def test_parse_text_utf8_decoding():
    data = "中文内容".encode("utf-8")
    result = parse_text(data)
    assert result[0]["page"] == 1
    assert "中文" in result[0]["text"]


# ── compute_hash ───────────────────────────────────────────────────────────────

def test_compute_hash_deterministic():
    data = b"same content"
    assert compute_hash(data) == compute_hash(data)


def test_compute_hash_different_data():
    assert compute_hash(b"aaa") != compute_hash(b"bbb")


def test_compute_hash_sha256_length():
    h = compute_hash(b"test")
    assert len(h) == 64  # SHA-256 hex = 64 chars


def test_compute_hash_known_value():
    import hashlib
    data = b"robotkb"
    expected = hashlib.sha256(data).hexdigest()
    assert compute_hash(data) == expected


# ── detect_format ──────────────────────────────────────────────────────────────

def test_detect_format_pdf():
    assert detect_format("manual.pdf") == "pdf"


def test_detect_format_pdf_uppercase():
    assert detect_format("MANUAL.PDF") == "pdf"


def test_detect_format_docx():
    assert detect_format("document.docx") == "docx"


def test_detect_format_txt():
    assert detect_format("readme.txt") == "text"


def test_detect_format_md():
    assert detect_format("notes.md") == "text"


def test_detect_format_unknown():
    assert detect_format("archive.zip") == "text"


def test_detect_format_no_extension():
    assert detect_format("Makefile") == "text"


# ── parse_pdf ──────────────────────────────────────────────────────────────────

def test_parse_pdf_basic():
    """Test parse_pdf with a mock PdfReader to avoid needing a real PDF file."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Page one content"

    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Page two content"

    mock_reader = MagicMock()
    mock_reader.pages = [mock_page, mock_page2]

    with patch("etl_worker.parsers.PdfReader", return_value=mock_reader):
        result = parse_pdf(b"%PDF-1.4 fake")

    assert len(result) == 2
    assert result[0]["page"] == 1
    assert result[0]["text"] == "Page one content"
    assert result[1]["page"] == 2
    assert result[1]["text"] == "Page two content"


def test_parse_pdf_none_text_becomes_empty_string():
    """extract_text() returning None should not crash."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = None

    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]

    with patch("etl_worker.parsers.PdfReader", return_value=mock_reader):
        result = parse_pdf(b"%PDF-1.4 fake")

    assert result[0]["text"] == ""


def test_parse_pdf_empty_document():
    mock_reader = MagicMock()
    mock_reader.pages = []

    with patch("etl_worker.parsers.PdfReader", return_value=mock_reader):
        result = parse_pdf(b"%PDF-1.4 fake")

    assert result == []


# ── parse_docx ─────────────────────────────────────────────────────────────────

def _make_mock_docx_paragraphs(texts: list[str]):
    """Create mock paragraph objects for python-docx."""
    paragraphs = []
    for t in texts:
        p = MagicMock()
        p.text = t
        paragraphs.append(p)
    return paragraphs


def test_parse_docx_basic():
    """Test parse_docx page grouping with mocked DocxDocument."""
    texts = [f"Paragraph {i}" for i in range(5)]
    mock_doc = MagicMock()
    mock_doc.paragraphs = _make_mock_docx_paragraphs(texts)

    with patch("etl_worker.parsers.DocxDocument", return_value=mock_doc):
        result = parse_docx(b"fake docx bytes")

    assert len(result) == 1  # All 5 paragraphs fit in page 1 (batch of 20)
    assert result[0]["page"] == 1
    assert "Paragraph 0" in result[0]["text"]


def test_parse_docx_page_boundary():
    """Paragraphs beyond 20 should appear on page 2."""
    texts = [f"Para {i}" for i in range(25)]
    mock_doc = MagicMock()
    mock_doc.paragraphs = _make_mock_docx_paragraphs(texts)

    with patch("etl_worker.parsers.DocxDocument", return_value=mock_doc):
        result = parse_docx(b"fake docx bytes")

    assert len(result) == 2
    assert result[0]["page"] == 1
    assert result[1]["page"] == 2


def test_parse_docx_empty_document():
    mock_doc = MagicMock()
    mock_doc.paragraphs = []

    with patch("etl_worker.parsers.DocxDocument", return_value=mock_doc):
        result = parse_docx(b"fake docx bytes")

    assert result == [{"page": 1, "text": ""}]


def test_parse_docx_skips_blank_paragraphs():
    """Blank paragraphs should be filtered out (strip() == '')."""
    texts = ["Real content", "", "   ", "More content"]
    mock_doc = MagicMock()
    mock_doc.paragraphs = _make_mock_docx_paragraphs(texts)

    with patch("etl_worker.parsers.DocxDocument", return_value=mock_doc):
        result = parse_docx(b"fake docx bytes")

    # Only "Real content" and "More content" should appear
    combined = "\n".join(r["text"] for r in result)
    assert "Real content" in combined
    assert "More content" in combined
