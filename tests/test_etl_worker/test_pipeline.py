"""Tests for etl_worker.pipeline.ETLPipeline (all external deps mocked)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.schemas import DocumentCategory, DocumentMeta, DocumentStatus, SourceTier
from etl_worker.pipeline import ETLPipeline


# ── helpers / fixtures ─────────────────────────────────────────────────────────

def _make_meta(
    chips: list[str] | None = None,
    boards: list[str] | None = None,
    status: DocumentStatus = DocumentStatus.PENDING,
    category: DocumentCategory = DocumentCategory.DEVELOPMENT,
) -> DocumentMeta:
    return DocumentMeta(
        title="Test Document",
        category=category,
        source_tier=SourceTier.OFFICIAL,
        applicable_chips=chips or ["rk3588"],
        applicable_boards=boards or ["rock5b"],
        ros_versions=["Humble"],
        status=status,
    )


def _consistent_ner_result() -> dict:
    return {
        "consistent": True,
        "extracted_chips": ["rk3588"],
        "extracted_boards": ["rock5b"],
        "missing_in_declaration": [],
        "false_positives": [],
    }


def _inconsistent_ner_result() -> dict:
    return {
        "consistent": False,
        "extracted_chips": ["rk3588s"],
        "extracted_boards": [],
        "missing_in_declaration": ["rk3588s"],
        "false_positives": ["rk3588"],
    }


@pytest.fixture
def mock_doc_dao():
    dao = AsyncMock()
    dao.create = AsyncMock(return_value="doc-1234")
    dao.find_by_hash = AsyncMock(return_value=None)
    dao.mark_superseded = AsyncMock()
    dao.update_meta = AsyncMock()
    return dao


@pytest.fixture
def mock_chunk_dao():
    dao = AsyncMock()
    dao.bulk_insert = AsyncMock(return_value=["chunk-1", "chunk-2"])
    return dao


@pytest.fixture
def mock_minio():
    m = AsyncMock()
    m.upload = AsyncMock(return_value="raw/doc-1234/test.txt")
    return m


@pytest.fixture
def mock_embedder():
    e = AsyncMock()
    # Return a fixed-dimension embedding vector for each text
    e.embed = AsyncMock(side_effect=lambda texts: [[0.1] * 128 for _ in texts])
    return e


@pytest.fixture
def mock_ner_verifier():
    v = MagicMock()
    v.verify = MagicMock(return_value=_consistent_ner_result())
    return v


@pytest.fixture
def pipeline(mock_doc_dao, mock_chunk_dao, mock_minio, mock_embedder, mock_ner_verifier):
    return ETLPipeline(
        doc_dao=mock_doc_dao,
        chunk_dao=mock_chunk_dao,
        minio=mock_minio,
        embedder=mock_embedder,
        ner_verifier=mock_ner_verifier,
    )


# ── test_process_new_document ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_process_new_document(pipeline, mock_doc_dao, mock_chunk_dao, mock_minio, mock_embedder):
    """New document (no duplicate) should go through the full pipeline."""
    file_data = b"Hello world this is a test document with enough words to create chunks"
    meta = _make_meta()

    result = await pipeline.process_document(file_data, "test.txt", meta)

    # Basic structure
    assert "doc_id" in result
    assert "chunk_count" in result
    assert "status" in result
    assert "ner_result" in result
    assert "superseded" in result

    # No supersession
    assert result["superseded"] is None

    # Document was created
    mock_doc_dao.create.assert_called_once()

    # File was uploaded to MinIO
    mock_minio.upload.assert_called_once()
    upload_args = mock_minio.upload.call_args[0]
    assert "raw/doc-1234/test.txt" == upload_args[0]

    # Embedder was called
    mock_embedder.embed.assert_called()

    # Chunks were inserted
    mock_chunk_dao.bulk_insert.assert_called_once()

    # Metadata was updated with chunk_count
    mock_doc_dao.update_meta.assert_called_once()
    update_args = mock_doc_dao.update_meta.call_args[0]
    assert "chunk_count" in update_args[1]


@pytest.mark.asyncio
async def test_process_new_document_returns_correct_doc_id(pipeline, mock_doc_dao):
    """Returned doc_id should match what doc_dao.create returns."""
    mock_doc_dao.create = AsyncMock(return_value="custom-doc-id-abc")
    file_data = b"some content"
    result = await pipeline.process_document(file_data, "doc.txt", _make_meta())
    assert result["doc_id"] == "custom-doc-id-abc"


# ── test_duplicate_document_supersedes ────────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_document_supersedes(
    pipeline, mock_doc_dao, mock_ner_verifier
):
    """If the same hash already exists with status=published, call mark_superseded."""
    existing_meta = _make_meta(status=DocumentStatus.PUBLISHED)
    # Simulate existing published doc
    mock_doc_dao.find_by_hash = AsyncMock(return_value=existing_meta)
    mock_doc_dao.create = AsyncMock(return_value="new-doc-id")

    # Mock that we can retrieve the old doc_id
    # We need to simulate that the DAO's internal model has an id
    # For the test, we patch _get_existing_doc_id directly
    with patch.object(
        pipeline, "_get_existing_doc_id", AsyncMock(return_value="old-doc-id")
    ):
        result = await pipeline.process_document(
            b"same content", "same.txt", _make_meta()
        )

    mock_doc_dao.mark_superseded.assert_called_once_with("old-doc-id", "new-doc-id")
    assert result["superseded"] == "old-doc-id"


@pytest.mark.asyncio
async def test_no_supersession_if_not_published(pipeline, mock_doc_dao):
    """Existing document with non-published status should NOT trigger mark_superseded."""
    # Hash exists but status is PENDING (not PUBLISHED)
    existing_meta = _make_meta(status=DocumentStatus.PENDING)
    mock_doc_dao.find_by_hash = AsyncMock(return_value=existing_meta)

    result = await pipeline.process_document(b"content", "file.txt", _make_meta())

    mock_doc_dao.mark_superseded.assert_not_called()
    assert result["superseded"] is None


# ── test_ner_inconsistency_sets_reviewing ──────────────────────────────────────

@pytest.mark.asyncio
async def test_ner_inconsistency_sets_reviewing(pipeline, mock_ner_verifier, mock_doc_dao):
    """NER inconsistency should set document status to 'reviewing'."""
    mock_ner_verifier.verify = MagicMock(return_value=_inconsistent_ner_result())

    file_data = b"This document mentions RK3588S chip details."
    meta = _make_meta(chips=["rk3588"])

    result = await pipeline.process_document(file_data, "test.txt", meta)

    assert result["status"] == DocumentStatus.REVIEWING.value

    # update_meta should have been called with status=reviewing
    update_call = mock_doc_dao.update_meta.call_args[0]
    assert update_call[1]["status"] == DocumentStatus.REVIEWING.value


@pytest.mark.asyncio
async def test_ner_consistent_keeps_original_status(pipeline, mock_ner_verifier, mock_doc_dao):
    """When NER is consistent, original status should be preserved."""
    mock_ner_verifier.verify = MagicMock(return_value=_consistent_ner_result())

    meta = _make_meta(status=DocumentStatus.PENDING)
    result = await pipeline.process_document(b"RK3588 content", "test.txt", meta)

    # Status should remain PENDING (not changed to REVIEWING)
    assert result["status"] == DocumentStatus.PENDING.value


# ── test_batch_embedding ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_embedding(mock_doc_dao, mock_chunk_dao, mock_minio, mock_ner_verifier):
    """With batch_size=2, a document producing 5+ chunks should call embed multiple times."""
    embedder = AsyncMock()
    embedder.embed = AsyncMock(side_effect=lambda texts: [[0.0] * 64 for _ in texts])

    pipeline = ETLPipeline(
        doc_dao=mock_doc_dao,
        chunk_dao=mock_chunk_dao,
        minio=mock_minio,
        embedder=embedder,
        ner_verifier=mock_ner_verifier,
    )

    # Create a long document that will produce at least 5 chunks at max_tokens=5
    words = [f"w{i}" for i in range(50)]
    file_data = " ".join(words).encode()
    meta = _make_meta()

    from etl_worker.chunkers import TextChunker
    small_chunker = TextChunker(max_tokens=5, overlap_tokens=0)

    with patch("etl_worker.pipeline.get_chunker", return_value=small_chunker):
        result = await pipeline.process_document(
            file_data, "long.txt", meta, batch_size=2
        )

    # With 50 words / 5 max_tokens = 10 chunks, and batch_size=2 → 5 embed calls
    assert embedder.embed.call_count >= 5
    assert result["chunk_count"] == 10


@pytest.mark.asyncio
async def test_batch_embedding_single_batch(mock_doc_dao, mock_chunk_dao, mock_minio, mock_ner_verifier):
    """A short document with few chunks should call embed exactly once."""
    embedder = AsyncMock()
    embedder.embed = AsyncMock(side_effect=lambda texts: [[0.0] * 64 for _ in texts])

    pipeline = ETLPipeline(
        doc_dao=mock_doc_dao,
        chunk_dao=mock_chunk_dao,
        minio=mock_minio,
        embedder=embedder,
        ner_verifier=mock_ner_verifier,
    )

    file_data = b"short document with just a few words"
    result = await pipeline.process_document(file_data, "short.txt", _make_meta(), batch_size=16)

    # Short text → single chunk → single embed call
    assert embedder.embed.call_count == 1


# ── test_minio_upload_path ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_minio_upload_path(pipeline, mock_minio, mock_doc_dao):
    """MinIO object name should include doc_id and filename."""
    mock_doc_dao.create = AsyncMock(return_value="abc-123")
    with patch("etl_worker.pipeline.parse_pdf", return_value=[{"page": 1, "text": "content"}]):
        await pipeline.process_document(b"data", "report.pdf", _make_meta())

    call_args = mock_minio.upload.call_args[0]
    assert call_args[0] == "raw/abc-123/report.pdf"
    assert call_args[2] == "application/pdf"


@pytest.mark.asyncio
async def test_minio_upload_docx_content_type(pipeline, mock_minio, mock_doc_dao):
    mock_doc_dao.create = AsyncMock(return_value="xyz-456")
    with patch("etl_worker.pipeline.parse_docx", return_value=[{"page": 1, "text": "content"}]):
        await pipeline.process_document(b"docx data", "doc.docx", _make_meta())
    call_args = mock_minio.upload.call_args[0]
    assert "wordprocessingml" in call_args[2]


# ── test chunk_count in result ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chunk_count_in_result(pipeline):
    """chunk_count in result should match number of chunks created."""
    file_data = b"word " * 100  # 100 words
    result = await pipeline.process_document(file_data, "test.txt", _make_meta())

    assert result["chunk_count"] > 0
    assert isinstance(result["chunk_count"], int)
