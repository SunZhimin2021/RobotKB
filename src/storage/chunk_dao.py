from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import StorageUnavailable
from common.schemas import Chunk
from storage.models import ChunkModel, OutboxModel


class ChunkDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_chunk(row: ChunkModel) -> Chunk:
        return Chunk(
            chunk_id=str(row.id),
            document_id=str(row.document_id),
            content=row.content,
            page=row.page or 0,
            section=row.section,
            applicable_chips=row.applicable_chips or [],
            applicable_boards=row.applicable_boards or [],
            ros_versions=row.ros_versions or [],
            source_tier=row.source_tier,
            status=row.status,
        )

    # ── public API ─────────────────────────────────────────────────────────────

    async def bulk_insert(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> list[str]:
        """Insert chunks with their embeddings and write an outbox event atomically."""
        if not chunks:
            return []
        try:
            models: list[ChunkModel] = []
            chunk_ids: list[str] = []

            for chunk, emb in zip(chunks, embeddings):
                chunk_id = str(uuid.uuid4())
                chunk_ids.append(chunk_id)
                models.append(
                    ChunkModel(
                        id=uuid.UUID(chunk_id),
                        document_id=uuid.UUID(chunk.document_id),
                        content=chunk.content,
                        page=chunk.page,
                        section=chunk.section,
                        applicable_chips=chunk.applicable_chips,
                        applicable_boards=chunk.applicable_boards,
                        ros_versions=chunk.ros_versions,
                        source_tier=chunk.source_tier.value if chunk.source_tier else None,
                        status=chunk.status.value,
                        embedding=emb,
                    )
                )

            self._session.add_all(models)

            doc_id = chunks[0].document_id if chunks else ""
            outbox = OutboxModel(
                event_type="chunks.indexed",
                payload={"doc_id": doc_id, "chunk_ids": chunk_ids},
                status="pending",
            )
            self._session.add(outbox)

            await self._session.flush()
            return chunk_ids
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"bulk_insert chunks failed: {exc}") from exc

    async def get(self, chunk_id: str) -> Chunk | None:
        """Fetch a single chunk by id."""
        try:
            row = await self._session.get(ChunkModel, uuid.UUID(chunk_id))
            if row is None:
                return None
            return self._to_chunk(row)
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"get chunk failed: {exc}") from exc

    async def vector_search(
        self,
        query_embedding: list[float],
        hard_chips: list[str] | None = None,
        soft_chips: list[str] | None = None,
        ros_versions: list[str] | None = None,
        statuses: list[str] | None = None,
        top_k: int = 20,
        include_superseded: bool = False,
    ) -> list[dict[str, Any]]:
        """Cosine similarity search using pgvector <=> operator."""
        if statuses is None:
            statuses = ["published"]
        if not include_superseded and "superseded" not in statuses:
            pass  # statuses already excludes superseded

        try:
            # Build query vector string for pgvector
            q_str = f"[{','.join(map(str, query_embedding))}]"

            # Conditions
            conditions = ["status = ANY(:statuses)"]
            params: dict[str, Any] = {
                "q": q_str,
                "statuses": statuses,
                "top_k": top_k,
            }

            if hard_chips:
                conditions.append("applicable_chips && ARRAY[:hard_chips]::text[]")
                params["hard_chips"] = hard_chips

            if ros_versions:
                conditions.append("ros_versions && ARRAY[:ros_versions]::text[]")
                params["ros_versions"] = ros_versions

            where_clause = " AND ".join(conditions)

            raw_sql = text(
                f"""
                SELECT
                    id::text            AS chunk_id,
                    document_id::text   AS document_id,
                    content,
                    page,
                    section,
                    applicable_chips,
                    applicable_boards,
                    ros_versions,
                    source_tier,
                    status,
                    1 - (embedding <=> CAST(:q AS vector)) AS score
                FROM chunks
                WHERE {where_clause}
                ORDER BY embedding <=> CAST(:q AS vector)
                LIMIT :top_k
                """
            )

            result = await self._session.execute(raw_sql, params)
            rows = result.mappings().all()
            return [dict(r) for r in rows]
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"vector_search failed: {exc}") from exc

    async def by_document(self, doc_id: str) -> list[Chunk]:
        """Return all chunks belonging to a document."""
        try:
            stmt = select(ChunkModel).where(
                ChunkModel.document_id == uuid.UUID(doc_id)
            )
            result = await self._session.execute(stmt)
            return [self._to_chunk(r) for r in result.scalars().all()]
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"by_document failed: {exc}") from exc

    async def delete_by_document(self, doc_id: str) -> int:
        """Delete all chunks for a document; returns the row count."""
        try:
            stmt = delete(ChunkModel).where(
                ChunkModel.document_id == uuid.UUID(doc_id)
            )
            result = await self._session.execute(stmt)
            await self._session.flush()
            return result.rowcount
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"delete_by_document failed: {exc}") from exc

    async def sync_meta_from_document(self, doc_id: str, new_status: str) -> None:
        """Propagate document status change to all its chunks."""
        try:
            stmt = (
                update(ChunkModel)
                .where(ChunkModel.document_id == uuid.UUID(doc_id))
                .values(status=new_status)
            )
            await self._session.execute(stmt)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise StorageUnavailable(
                f"sync_meta_from_document failed: {exc}"
            ) from exc
