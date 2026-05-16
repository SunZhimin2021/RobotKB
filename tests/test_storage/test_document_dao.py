"""Unit tests for DocumentDAO — no real database connection."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from common.schemas import DocumentCategory, DocumentMeta, DocumentStatus, SourceTier
from storage.document_dao import DocumentDAO


# ── fixtures ───────────────────────────────────────────────────────────────────

def _make_meta(**kwargs) -> DocumentMeta:
    defaults = dict(
        title="Test Document",
        category=DocumentCategory.SOFTWARE,
        source_tier=SourceTier.OFFICIAL,
        applicable_chips=["rk3588"],
        applicable_boards=["rock5b"],
        ros_versions=["humble"],
        tags=["test"],
        doc_version="1.0",
        status=DocumentStatus.PENDING,
        content_hash="abc123",
        chunk_count=5,
        author="tester",
        vendor=None,
        valid_until=None,
    )
    defaults.update(kwargs)
    return DocumentMeta(**defaults)


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _make_doc_row(meta: DocumentMeta, doc_id: str | None = None) -> MagicMock:
    """Build a mock DocumentModel row from a DocumentMeta."""
    row = MagicMock()
    row.id = uuid.UUID(doc_id) if doc_id else uuid.uuid4()
    row.title = meta.title
    row.category = meta.category.value
    row.source_tier = meta.source_tier.value
    row.applicable_chips = meta.applicable_chips
    row.applicable_boards = meta.applicable_boards
    row.ros_versions = meta.ros_versions
    row.tags = meta.tags
    row.doc_version = meta.doc_version
    row.status = meta.status.value
    row.content_hash = meta.content_hash
    row.chunk_count = meta.chunk_count or 0
    row.author = meta.author
    row.vendor = meta.vendor
    row.valid_until = None
    return row


# ── tests ──────────────────────────────────────────────────────────────────────

class TestDocumentCreate:
    async def test_create_returns_uuid(self):
        """create() should return a valid UUID string."""
        session = _make_session()
        dao = DocumentDAO(session)
        meta = _make_meta()

        result = await dao.create(meta)

        assert isinstance(result, str)
        parsed = uuid.UUID(result)  # raises if not valid UUID
        assert str(parsed) == result

    async def test_create_writes_outbox(self):
        """create() must add an OutboxModel to the same session."""
        session = _make_session()
        dao = DocumentDAO(session)
        meta = _make_meta()

        await dao.create(meta)

        # session.add should be called at least twice: DocumentModel + OutboxModel
        assert session.add.call_count >= 2

        # Inspect added objects for the outbox entry
        added_objects = [call.args[0] for call in session.add.call_args_list]
        from storage.models import OutboxModel
        outbox_objects = [o for o in added_objects if isinstance(o, OutboxModel)]
        assert len(outbox_objects) == 1
        assert outbox_objects[0].event_type == "document.created"

    async def test_create_calls_flush(self):
        """create() must call session.flush() to materialise within the transaction."""
        session = _make_session()
        dao = DocumentDAO(session)

        await dao.create(_make_meta())

        session.flush.assert_awaited_once()


class TestFindByHash:
    async def test_find_by_hash_not_found(self):
        """find_by_hash returns None when the hash does not exist."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        dao = DocumentDAO(session)
        result = await dao.find_by_hash("nonexistent_hash")

        assert result is None

    async def test_find_by_hash_found(self):
        """find_by_hash returns DocumentMeta when the document exists."""
        meta = _make_meta(content_hash="deadbeef")
        row = _make_doc_row(meta)

        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = row
        session.execute = AsyncMock(return_value=mock_result)

        dao = DocumentDAO(session)
        result = await dao.find_by_hash("deadbeef")

        assert result is not None
        assert result.content_hash == "deadbeef"
        assert result.title == meta.title


class TestMarkSuperseded:
    async def test_mark_superseded_sets_status(self):
        """mark_superseded writes an outbox event with correct type and doc_ids."""
        session = _make_session()
        mock_result = MagicMock()
        session.execute = AsyncMock(return_value=mock_result)

        dao = DocumentDAO(session)
        old_id = str(uuid.uuid4())
        new_id = str(uuid.uuid4())

        await dao.mark_superseded(old_id, new_id)

        # Verify outbox entry was added
        added_objects = [call.args[0] for call in session.add.call_args_list]
        from storage.models import OutboxModel
        outbox_objects = [o for o in added_objects if isinstance(o, OutboxModel)]
        assert len(outbox_objects) == 1
        outbox = outbox_objects[0]
        assert outbox.event_type == "document.superseded"
        assert outbox.payload["old_doc_id"] == old_id
        assert outbox.payload["new_doc_id"] == new_id

    async def test_mark_superseded_executes_update(self):
        """mark_superseded calls session.execute with an UPDATE statement."""
        session = _make_session()
        mock_result = MagicMock()
        session.execute = AsyncMock(return_value=mock_result)

        dao = DocumentDAO(session)
        old_id = str(uuid.uuid4())
        new_id = str(uuid.uuid4())

        await dao.mark_superseded(old_id, new_id)

        session.execute.assert_awaited()


class TestList:
    async def test_list_filters_by_status(self):
        """list(status='published') must pass a WHERE condition to session."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        dao = DocumentDAO(session)
        result = await dao.list(status="published")

        # session.execute must have been called (with a Select statement)
        session.execute.assert_awaited_once()
        assert result == []

    async def test_list_returns_document_metas(self):
        """list() maps ORM rows to DocumentMeta objects."""
        meta = _make_meta(status=DocumentStatus.PUBLISHED)
        row = _make_doc_row(meta)

        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [row]
        session.execute = AsyncMock(return_value=mock_result)

        dao = DocumentDAO(session)
        results = await dao.list()

        assert len(results) == 1
        assert results[0].title == meta.title

    async def test_list_no_filters(self):
        """list() with no filters still calls session.execute."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        dao = DocumentDAO(session)
        await dao.list()

        session.execute.assert_awaited_once()


class TestGet:
    async def test_get_returns_none_for_missing_doc(self):
        """get() returns None when document does not exist."""
        session = _make_session()
        session.get = AsyncMock(return_value=None)

        dao = DocumentDAO(session)
        result = await dao.get(str(uuid.uuid4()))

        assert result is None

    async def test_get_returns_document_meta(self):
        """get() returns a DocumentMeta for an existing document."""
        meta = _make_meta()
        doc_id = str(uuid.uuid4())
        row = _make_doc_row(meta, doc_id=doc_id)

        session = _make_session()
        session.get = AsyncMock(return_value=row)

        dao = DocumentDAO(session)
        result = await dao.get(doc_id)

        assert result is not None
        assert result.title == meta.title
        assert result.content_hash == meta.content_hash


class TestSoftDelete:
    async def test_soft_delete_executes_update(self):
        """soft_delete calls session.execute and flush."""
        session = _make_session()
        mock_result = MagicMock()
        session.execute = AsyncMock(return_value=mock_result)

        dao = DocumentDAO(session)
        doc_id = str(uuid.uuid4())
        await dao.soft_delete(doc_id)

        session.execute.assert_awaited_once()
        session.flush.assert_awaited_once()
