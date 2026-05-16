from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import StorageUnavailable
from common.schemas import DocumentMeta, DocumentStatus
from storage.models import DocumentModel, OutboxModel


class DocumentDAO:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _to_meta(row: DocumentModel) -> DocumentMeta:
        return DocumentMeta(
            title=row.title,
            category=row.category,
            source_tier=row.source_tier,
            applicable_chips=row.applicable_chips or [],
            applicable_boards=row.applicable_boards or [],
            ros_versions=row.ros_versions or [],
            tags=row.tags or [],
            doc_version=row.doc_version or None,
            status=row.status,
            content_hash=row.content_hash,
            chunk_count=row.chunk_count,
            author=row.author,
            vendor=row.vendor,
            valid_until=row.valid_until.isoformat() if row.valid_until else None,
        )

    def _make_outbox(self, event_type: str, payload: dict) -> OutboxModel:
        return OutboxModel(event_type=event_type, payload=payload, status="pending")

    # ── public API ─────────────────────────────────────────────────────────────

    async def create(self, meta: DocumentMeta) -> str:
        """Insert a new document and write an outbox event atomically."""
        try:
            doc_id = str(uuid.uuid4())
            valid_until: datetime | None = None
            if meta.valid_until:
                valid_until = datetime.fromisoformat(meta.valid_until)

            doc = DocumentModel(
                id=uuid.UUID(doc_id),
                title=meta.title,
                category=meta.category.value,
                source_tier=meta.source_tier.value,
                applicable_chips=meta.applicable_chips,
                applicable_boards=meta.applicable_boards,
                ros_versions=meta.ros_versions,
                tags=meta.tags,
                doc_version=meta.doc_version or "",
                status=meta.status.value,
                content_hash=meta.content_hash or "",
                chunk_count=meta.chunk_count or 0,
                author=meta.author,
                vendor=meta.vendor,
                valid_until=valid_until,
            )
            self._session.add(doc)

            outbox = self._make_outbox(
                "document.created",
                {
                    "doc_id": doc_id,
                    "title": meta.title,
                    "category": meta.category.value,
                    "chips": meta.applicable_chips,
                },
            )
            self._session.add(outbox)

            await self._session.flush()
            return doc_id
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"create document failed: {exc}") from exc

    async def get(self, doc_id: str) -> DocumentMeta | None:
        """Fetch a document by primary key."""
        try:
            result = await self._session.get(DocumentModel, uuid.UUID(doc_id))
            if result is None:
                return None
            return self._to_meta(result)
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"get document failed: {exc}") from exc

    async def update_meta(self, doc_id: str, updates: dict[str, Any]) -> None:
        """Update document fields and write an outbox event atomically."""
        try:
            stmt = (
                update(DocumentModel)
                .where(DocumentModel.id == uuid.UUID(doc_id))
                .values(**updates)
            )
            await self._session.execute(stmt)

            outbox = self._make_outbox(
                "document.updated",
                {"doc_id": doc_id, "updates": list(updates.keys())},
            )
            self._session.add(outbox)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"update document failed: {exc}") from exc

    async def list(
        self,
        status: str | None = None,
        category: str | None = None,
        chip: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DocumentMeta]:
        """List documents with optional filters."""
        try:
            stmt = select(DocumentModel)
            if status is not None:
                stmt = stmt.where(DocumentModel.status == status)
            if category is not None:
                stmt = stmt.where(DocumentModel.category == category)
            if chip is not None:
                from sqlalchemy import cast, literal
                from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
                from sqlalchemy import String as SA_String
                stmt = stmt.where(
                    DocumentModel.applicable_chips.overlap(
                        cast([chip], PG_ARRAY(SA_String))
                    )
                )
            stmt = stmt.limit(limit).offset(offset)
            result = await self._session.execute(stmt)
            rows = result.scalars().all()
            return [self._to_meta(r) for r in rows]
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"list documents failed: {exc}") from exc

    async def find_by_hash(self, content_hash: str) -> DocumentMeta | None:
        """Return the document with the given content_hash, or None."""
        try:
            stmt = select(DocumentModel).where(
                DocumentModel.content_hash == content_hash
            )
            result = await self._session.execute(stmt)
            row = result.scalars().first()
            if row is None:
                return None
            return self._to_meta(row)
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"find_by_hash failed: {exc}") from exc

    async def mark_superseded(self, old_doc_id: str, new_doc_id: str) -> None:
        """Mark old_doc_id as superseded by new_doc_id atomically."""
        try:
            stmt = (
                update(DocumentModel)
                .where(DocumentModel.id == uuid.UUID(old_doc_id))
                .values(
                    status=DocumentStatus.SUPERSEDED.value,
                    superseded_by=uuid.UUID(new_doc_id),
                )
            )
            await self._session.execute(stmt)

            outbox = self._make_outbox(
                "document.superseded",
                {"old_doc_id": old_doc_id, "new_doc_id": new_doc_id},
            )
            self._session.add(outbox)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"mark_superseded failed: {exc}") from exc

    async def soft_delete(self, doc_id: str) -> None:
        """Logically delete by setting status to superseded."""
        try:
            stmt = (
                update(DocumentModel)
                .where(DocumentModel.id == uuid.UUID(doc_id))
                .values(status=DocumentStatus.SUPERSEDED.value)
            )
            await self._session.execute(stmt)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise StorageUnavailable(f"soft_delete failed: {exc}") from exc
