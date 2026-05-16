"""Unit tests for ChunkDAO — no real database connection."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.schemas import Chunk, DocumentStatus, SourceTier
from storage.chunk_dao import ChunkDAO


# ── fixtures ───────────────────────────────────────────────────────────────────

def _make_chunk(document_id: str | None = None, **kwargs) -> Chunk:
    defaults = dict(
        chunk_id=str(uuid.uuid4()),
        document_id=document_id or str(uuid.uuid4()),
        content="Sample chunk content",
        page=1,
        section="Introduction",
        applicable_chips=["rk3588"],
        applicable_boards=["rock5b"],
        ros_versions=["humble"],
        source_tier=SourceTier.OFFICIAL,
        status=DocumentStatus.PUBLISHED,
    )
    defaults.update(kwargs)
    return Chunk(**defaults)


def _make_embedding(dim: int = 1024) -> list[float]:
    return [0.1] * dim


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _make_chunk_row(chunk: Chunk) -> MagicMock:
    row = MagicMock()
    row.id = uuid.UUID(chunk.chunk_id)
    row.document_id = uuid.UUID(chunk.document_id)
    row.content = chunk.content
    row.page = chunk.page
    row.section = chunk.section
    row.applicable_chips = chunk.applicable_chips
    row.applicable_boards = chunk.applicable_boards
    row.ros_versions = chunk.ros_versions
    row.source_tier = chunk.source_tier.value if chunk.source_tier else None
    row.status = chunk.status.value
    return row


# ── tests ──────────────────────────────────────────────────────────────────────

class TestBulkInsert:
    async def test_bulk_insert_returns_ids(self):
        """bulk_insert returns the same number of ids as input chunks."""
        session = _make_session()
        dao = ChunkDAO(session)

        doc_id = str(uuid.uuid4())
        chunks = [_make_chunk(document_id=doc_id) for _ in range(3)]
        embeddings = [_make_embedding() for _ in range(3)]

        result = await dao.bulk_insert(chunks, embeddings)

        assert len(result) == 3
        for chunk_id in result:
            uuid.UUID(chunk_id)  # validates UUID format

    async def test_bulk_insert_writes_outbox_event(self):
        """bulk_insert must add an OutboxModel with event_type='chunks.indexed'."""
        session = _make_session()
        dao = ChunkDAO(session)

        doc_id = str(uuid.uuid4())
        chunks = [_make_chunk(document_id=doc_id)]
        embeddings = [_make_embedding()]

        await dao.bulk_insert(chunks, embeddings)

        added_objects = [call.args[0] for call in session.add.call_args_list]
        from storage.models import OutboxModel
        outbox_objects = [o for o in added_objects if isinstance(o, OutboxModel)]
        assert len(outbox_objects) == 1
        assert outbox_objects[0].event_type == "chunks.indexed"
        assert outbox_objects[0].payload["doc_id"] == doc_id

    async def test_bulk_insert_empty_returns_empty(self):
        """bulk_insert with no chunks returns empty list without touching DB."""
        session = _make_session()
        dao = ChunkDAO(session)

        result = await dao.bulk_insert([], [])

        assert result == []
        session.add_all.assert_not_called()
        session.flush.assert_not_awaited()

    async def test_bulk_insert_calls_add_all(self):
        """bulk_insert uses session.add_all for the chunk models."""
        session = _make_session()
        dao = ChunkDAO(session)

        doc_id = str(uuid.uuid4())
        chunks = [_make_chunk(document_id=doc_id) for _ in range(2)]
        embeddings = [_make_embedding() for _ in range(2)]

        await dao.bulk_insert(chunks, embeddings)

        session.add_all.assert_called_once()
        models_inserted = session.add_all.call_args.args[0]
        assert len(models_inserted) == 2


class TestVectorSearch:
    async def test_vector_search_hard_chip_filter(self):
        """vector_search with hard_chips must include '&&' array overlap condition."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        dao = ChunkDAO(session)
        query_emb = _make_embedding()

        await dao.vector_search(
            query_embedding=query_emb,
            hard_chips=["rk3588"],
        )

        # Verify execute was called and the SQL contains '&&' operator
        session.execute.assert_awaited_once()
        call_args = session.execute.call_args
        sql_text = str(call_args.args[0])
        assert "&&" in sql_text, f"Expected '&&' in SQL, got:\n{sql_text}"

    async def test_vector_search_empty_result(self):
        """vector_search returns [] when no rows match."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        dao = ChunkDAO(session)
        result = await dao.vector_search(query_embedding=_make_embedding())

        assert result == []

    async def test_vector_search_returns_dicts(self):
        """vector_search returns list of dicts with expected keys."""
        row = {
            "chunk_id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "content": "test content",
            "page": 1,
            "section": None,
            "applicable_chips": ["rk3588"],
            "applicable_boards": [],
            "ros_versions": ["humble"],
            "source_tier": "official",
            "status": "published",
            "score": 0.95,
        }

        session = _make_session()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = [row]
        session.execute = AsyncMock(return_value=mock_result)

        dao = ChunkDAO(session)
        results = await dao.vector_search(query_embedding=_make_embedding())

        assert len(results) == 1
        assert results[0]["chunk_id"] == row["chunk_id"]

    async def test_vector_search_uses_cosine_operator(self):
        """vector_search SQL must use the <=> operator for cosine distance."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.mappings.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        dao = ChunkDAO(session)
        await dao.vector_search(query_embedding=_make_embedding())

        call_args = session.execute.call_args
        sql_text = str(call_args.args[0])
        assert "<=>" in sql_text, f"Expected '<=>' operator in SQL, got:\n{sql_text}"


class TestDeleteByDocument:
    async def test_delete_by_document_returns_count(self):
        """delete_by_document returns the rowcount from the DELETE statement."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.rowcount = 7
        session.execute = AsyncMock(return_value=mock_result)

        dao = ChunkDAO(session)
        count = await dao.delete_by_document(str(uuid.uuid4()))

        assert count == 7

    async def test_delete_by_document_zero_when_none(self):
        """delete_by_document returns 0 when no chunks exist for the document."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        session.execute = AsyncMock(return_value=mock_result)

        dao = ChunkDAO(session)
        count = await dao.delete_by_document(str(uuid.uuid4()))

        assert count == 0

    async def test_delete_by_document_calls_flush(self):
        """delete_by_document must flush after the DELETE."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        session.execute = AsyncMock(return_value=mock_result)

        dao = ChunkDAO(session)
        await dao.delete_by_document(str(uuid.uuid4()))

        session.flush.assert_awaited_once()


class TestGet:
    async def test_get_returns_none_for_missing_chunk(self):
        """get() returns None when chunk does not exist."""
        session = _make_session()
        session.get = AsyncMock(return_value=None)

        dao = ChunkDAO(session)
        result = await dao.get(str(uuid.uuid4()))

        assert result is None

    async def test_get_returns_chunk(self):
        """get() maps an ORM row to a Chunk pydantic model."""
        chunk = _make_chunk()
        row = _make_chunk_row(chunk)

        session = _make_session()
        session.get = AsyncMock(return_value=row)

        dao = ChunkDAO(session)
        result = await dao.get(chunk.chunk_id)

        assert result is not None
        assert result.content == chunk.content
        assert result.document_id == chunk.document_id


class TestByDocument:
    async def test_by_document_returns_all_chunks(self):
        """by_document returns all Chunk objects for the given document_id."""
        doc_id = str(uuid.uuid4())
        chunks = [_make_chunk(document_id=doc_id) for _ in range(4)]
        rows = [_make_chunk_row(c) for c in chunks]

        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = rows
        session.execute = AsyncMock(return_value=mock_result)

        dao = ChunkDAO(session)
        results = await dao.by_document(doc_id)

        assert len(results) == 4

    async def test_by_document_empty(self):
        """by_document returns [] when document has no chunks."""
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        dao = ChunkDAO(session)
        results = await dao.by_document(str(uuid.uuid4()))

        assert results == []
