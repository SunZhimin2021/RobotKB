from __future__ import annotations

import re
from enum import Enum

from common.schemas import DocumentCategory, DocumentMeta, DocumentStatus


class ChunkingStrategy(str, Enum):
    PARAGRAPH = "paragraph"
    SECTION = "section"   # datasheet: section + table, no overlap
    CODE = "code"         # function/class boundary, no overlap
    FAULT = "fault"       # (symptom, cause, solution) triples, no overlap


# ── helpers ────────────────────────────────────────────────────────────────────

_SECTION_HEADING_RE = re.compile(
    r"^(#{1,6}\s.+|[A-Z0-9][A-Z0-9 \t]{3,}$|\d+(\.\d+)*\s+[A-Z].{2,})",
    re.MULTILINE,
)

_FAULT_SYMPTOM_RE = re.compile(
    r"(?:故障|症状|问题|现象|Symptom|Problem|Issue)[：:\s]+(.+)",
    re.IGNORECASE,
)
_FAULT_CAUSE_RE = re.compile(
    r"(?:原因|原理|Cause|Root cause)[：:\s]+(.+)",
    re.IGNORECASE,
)
_FAULT_SOLUTION_RE = re.compile(
    r"(?:解决|方案|修复|Solution|Fix|Resolution)[：:\s]+(.+)",
    re.IGNORECASE,
)

# Code block boundary markers (blank lines + indentation shifts)
_CODE_BLOCK_START_RE = re.compile(r"^(def |class |async def |module |function )", re.MULTILINE)


def _words(text: str) -> list[str]:
    """Simple whitespace tokenisation used for token estimation."""
    return text.split()


def _chunk_meta(chunk_dict: dict, doc_meta: DocumentMeta) -> dict:
    """Fill inherited metadata fields from *doc_meta* into a chunk dict."""
    chunk_dict.setdefault("applicable_chips", list(doc_meta.applicable_chips))
    chunk_dict.setdefault("applicable_boards", list(doc_meta.applicable_boards))
    chunk_dict.setdefault("ros_versions", list(doc_meta.ros_versions))
    chunk_dict.setdefault("source_tier", doc_meta.source_tier.value)
    chunk_dict.setdefault("status", doc_meta.status.value)
    return chunk_dict


# ── chunker classes ────────────────────────────────────────────────────────────

class TextChunker:
    """Generic text chunker using paragraph mode.

    Splits text by *max_tokens* (word count) with *overlap_tokens* overlap
    between consecutive chunks.
    """

    def __init__(self, max_tokens: int = 512, overlap_tokens: int = 100) -> None:
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens

    def _split_words(self, text: str) -> list[str]:
        return _words(text)

    def _pages_to_words(self, pages: list[dict]) -> list[tuple[int, str]]:
        """Flatten pages into a list of (page_number, word) pairs."""
        result: list[tuple[int, str]] = []
        for page in pages:
            for word in _words(page["text"]):
                result.append((page["page"], word))
        return result

    def chunk(self, pages: list[dict], doc_meta: DocumentMeta) -> list[dict]:
        """Split pages into overlapping text chunks.

        Returns a list of chunk dicts with content, page, section and inherited
        metadata fields.
        """
        word_page_pairs = self._pages_to_words(pages)
        if not word_page_pairs:
            return []

        chunks: list[dict] = []
        start = 0
        total = len(word_page_pairs)

        while start < total:
            end = min(start + self.max_tokens, total)
            slice_pairs = word_page_pairs[start:end]
            content = " ".join(w for _, w in slice_pairs)
            page_num = slice_pairs[0][0]

            chunk = _chunk_meta(
                {
                    "content": content,
                    "page": page_num,
                    "section": None,
                },
                doc_meta,
            )
            chunks.append(chunk)

            if end >= total:
                break
            # Advance by (max_tokens - overlap_tokens) but at least 1 word
            advance = max(1, self.max_tokens - self.overlap_tokens)
            start += advance

        return chunks


class SectionChunker(TextChunker):
    """Datasheet mode: use Markdown / Word section headings as boundaries.

    No overlap between chunks (overlap_tokens is ignored).
    """

    def chunk(self, pages: list[dict], doc_meta: DocumentMeta) -> list[dict]:
        full_text = "\n".join(p["text"] for p in pages)
        page_for_line = self._build_line_page_map(pages)

        # Split on section headings
        sections = _SECTION_HEADING_RE.split(full_text)

        chunks: list[dict] = []
        current_heading: str | None = None
        current_lines: list[str] = []

        def flush(heading: str | None, lines: list[str]) -> None:
            text = "\n".join(lines).strip()
            if not text:
                return
            # Estimate page number from first word in lines
            page_num = self._estimate_page(lines, page_for_line)
            chunk = _chunk_meta(
                {
                    "content": (f"{heading}\n{text}" if heading else text),
                    "page": page_num,
                    "section": heading,
                },
                doc_meta,
            )
            chunks.append(chunk)

        for part in _SECTION_HEADING_RE.split(full_text):
            if part is None:
                continue
            stripped = part.strip()
            if not stripped:
                continue
            if _SECTION_HEADING_RE.match(stripped):
                flush(current_heading, current_lines)
                current_heading = stripped
                current_lines = []
            else:
                # Further split by max_tokens if the section is very long
                words = _words(stripped)
                pos = 0
                while pos < len(words):
                    batch = words[pos: pos + self.max_tokens]
                    current_lines.append(" ".join(batch))
                    if pos + self.max_tokens < len(words):
                        flush(current_heading, current_lines)
                        current_lines = []
                    pos += self.max_tokens

        flush(current_heading, current_lines)

        # If no headings were found at all, fall back to simple splitting
        if not chunks:
            return super().chunk(pages, doc_meta)

        return chunks

    @staticmethod
    def _build_line_page_map(pages: list[dict]) -> dict[str, int]:
        """Map each line of text to its page number."""
        mapping: dict[str, int] = {}
        for page in pages:
            for line in page["text"].splitlines():
                line = line.strip()
                if line and line not in mapping:
                    mapping[line] = page["page"]
        return mapping

    @staticmethod
    def _estimate_page(lines: list[str], line_page_map: dict[str, int]) -> int:
        for line in lines:
            for part in line.splitlines():
                part = part.strip()
                if part in line_page_map:
                    return line_page_map[part]
        return 1


class CodeChunker(TextChunker):
    """Code mode: split at function/class boundaries (blank lines + indentation).

    No overlap between chunks.
    """

    def chunk(self, pages: list[dict], doc_meta: DocumentMeta) -> list[dict]:
        full_text = "\n".join(p["text"] for p in pages)
        page_for_line = SectionChunker._build_line_page_map(pages)

        # Split into logical blocks: consecutive non-empty lines separated by blank lines
        raw_blocks: list[str] = []
        current_block: list[str] = []

        for line in full_text.splitlines():
            if line.strip():
                current_block.append(line)
            else:
                if current_block:
                    raw_blocks.append("\n".join(current_block))
                    current_block = []
        if current_block:
            raw_blocks.append("\n".join(current_block))

        # Merge small blocks until we hit max_tokens
        chunks: list[dict] = []
        current_words: list[str] = []
        current_page = 1

        for block in raw_blocks:
            block_words = _words(block)
            if current_words and len(current_words) + len(block_words) > self.max_tokens:
                content = " ".join(current_words)
                chunk = _chunk_meta(
                    {"content": content, "page": current_page, "section": None},
                    doc_meta,
                )
                chunks.append(chunk)
                current_words = []

            if not current_words:
                # Estimate page from first line of this block
                for line in block.splitlines():
                    page = page_for_line.get(line.strip(), 1)
                    if page:
                        current_page = page
                        break

            current_words.extend(block_words)

        if current_words:
            content = " ".join(current_words)
            chunk = _chunk_meta(
                {"content": content, "page": current_page, "section": None},
                doc_meta,
            )
            chunks.append(chunk)

        if not chunks:
            return super().chunk(pages, doc_meta)

        return chunks


class FaultChunker(TextChunker):
    """Fault case mode: extract (symptom, cause, solution) triples.

    No overlap between chunks.
    """

    def chunk(self, pages: list[dict], doc_meta: DocumentMeta) -> list[dict]:
        full_text = "\n".join(p["text"] for p in pages)
        page_for_line = SectionChunker._build_line_page_map(pages)

        chunks: list[dict] = []

        # Split on fault-case delimiters (blank lines between cases)
        cases = re.split(r"\n{2,}", full_text)

        for case_text in cases:
            case_text = case_text.strip()
            if not case_text:
                continue

            # Try to detect structured fault triples
            symptom_match = _FAULT_SYMPTOM_RE.search(case_text)
            cause_match = _FAULT_CAUSE_RE.search(case_text)
            solution_match = _FAULT_SOLUTION_RE.search(case_text)

            if symptom_match or cause_match or solution_match:
                # Build a structured representation
                parts: list[str] = []
                if symptom_match:
                    parts.append(f"症状: {symptom_match.group(1).strip()}")
                if cause_match:
                    parts.append(f"原因: {cause_match.group(1).strip()}")
                if solution_match:
                    parts.append(f"解决方案: {solution_match.group(1).strip()}")
                content = "\n".join(parts) if parts else case_text
            else:
                content = case_text

            # Estimate page
            page_num = 1
            for line in case_text.splitlines():
                page = page_for_line.get(line.strip(), 0)
                if page:
                    page_num = page
                    break

            # Split oversized cases by max_tokens (no overlap)
            words = _words(content)
            pos = 0
            while pos < len(words):
                batch_words = words[pos: pos + self.max_tokens]
                batch_content = " ".join(batch_words)
                chunk = _chunk_meta(
                    {"content": batch_content, "page": page_num, "section": None},
                    doc_meta,
                )
                chunks.append(chunk)
                pos += self.max_tokens

        if not chunks:
            return super().chunk(pages, doc_meta)

        return chunks


# ── factory ────────────────────────────────────────────────────────────────────

def get_chunker(category: DocumentCategory) -> TextChunker:
    """Return the appropriate chunker for a document category.

    HARDWARE  → SectionChunker (no overlap)
    SOFTWARE  → SectionChunker (no overlap)
    DEVELOPMENT → TextChunker (paragraph overlap)
    FAULT_HANDLING → FaultChunker (no overlap)
    """
    if category == DocumentCategory.HARDWARE:
        return SectionChunker(max_tokens=512, overlap_tokens=0)
    if category == DocumentCategory.SOFTWARE:
        return SectionChunker(max_tokens=512, overlap_tokens=0)
    if category == DocumentCategory.FAULT_HANDLING:
        return FaultChunker(max_tokens=512, overlap_tokens=0)
    # DEVELOPMENT and anything else
    return TextChunker(max_tokens=512, overlap_tokens=100)
