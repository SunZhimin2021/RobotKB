from __future__ import annotations

import hashlib
import io

from docx import Document as DocxDocument
from pypdf import PdfReader


def parse_pdf(data: bytes) -> list[dict]:
    """Parse PDF using pypdf.

    Returns: [{"page": int, "text": str}] one entry per page.
    """
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": page_num, "text": text})
    return pages


def parse_docx(data: bytes) -> list[dict]:
    """Parse Word document using python-docx.

    Groups paragraphs in batches of 20 (paragraph_index // 20 + 1 = page).
    Returns: [{"page": int, "text": str}]
    """
    doc = DocxDocument(io.BytesIO(data))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

    # Group into virtual pages of 20 paragraphs each
    page_map: dict[int, list[str]] = {}
    for idx, text in enumerate(paragraphs):
        page_num = idx // 20 + 1
        page_map.setdefault(page_num, []).append(text)

    if not page_map:
        return [{"page": 1, "text": ""}]

    return [
        {"page": page_num, "text": "\n".join(texts)}
        for page_num, texts in sorted(page_map.items())
    ]


def parse_text(data: bytes) -> list[dict]:
    """Parse plain text. The whole content is treated as page 1."""
    text = data.decode("utf-8", errors="replace")
    return [{"page": 1, "text": text}]


def compute_hash(data: bytes) -> str:
    """Return the SHA-256 hex digest of *data*."""
    return hashlib.sha256(data).hexdigest()


def detect_format(filename: str) -> str:
    """Return 'pdf', 'docx', or 'text' based on the file extension."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".docx"):
        return "docx"
    return "text"
