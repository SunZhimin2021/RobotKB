from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from common.exceptions import StorageUnavailable
from storage.meili_client import MeiliClient
from storage.models import DeadLetterModel, OutboxModel
from storage.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50


class OutboxWorker:
    """Polls the outbox table and fans events out to Meilisearch and Neo4j."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        meili: MeiliClient,
        neo4j: Neo4jClient,
        poll_interval: float = 1.0,
        max_retry: int = 3,
    ) -> None:
        self._factory = session_factory
        self._meili = meili
        self._neo4j = neo4j
        self._poll_interval = poll_interval
        self._max_retry = max_retry

    # ── public ─────────────────────────────────────────────────────────────────

    async def run_once(self) -> int:
        """Fetch and process one batch of pending outbox events.

        Returns the number of events processed.
        """
        async with self._factory() as session:
            stmt = (
                select(OutboxModel)
                .where(
                    OutboxModel.status.in_(["pending", "retry"]),
                    OutboxModel.retry_count < self._max_retry,
                )
                .order_by(OutboxModel.id)
                .limit(_BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            events = result.scalars().all()

            if not events:
                return 0

            processed = 0
            for event in events:
                try:
                    await self._process_event(
                        event.id, event.event_type, event.payload
                    )
                    event.status = "done"
                    event.processed_at = datetime.now(timezone.utc)
                    processed += 1
                except Exception as exc:
                    logger.warning(
                        "Outbox event %s failed (attempt %d): %s",
                        event.id,
                        event.retry_count + 1,
                        exc,
                    )
                    event.retry_count += 1
                    if event.retry_count >= self._max_retry:
                        event.status = "dead"
                        dead = DeadLetterModel(
                            outbox_id=event.id,
                            error=str(exc),
                            payload=event.payload,
                        )
                        session.add(dead)
                    else:
                        event.status = "retry"

            await session.commit()
            return processed

    async def start(self) -> None:
        """Run forever, polling in a loop."""
        logger.info("OutboxWorker started (poll_interval=%.1fs)", self._poll_interval)
        while True:
            try:
                count = await self.run_once()
                if count:
                    logger.debug("OutboxWorker processed %d events", count)
            except Exception as exc:
                logger.error("OutboxWorker run_once error: %s", exc)
            await asyncio.sleep(self._poll_interval)

    # ── private ────────────────────────────────────────────────────────────────

    async def _process_event(
        self, event_id: int, event_type: str, payload: dict[str, Any]
    ) -> None:
        if event_type in ("document.created", "document.updated"):
            doc_id = payload.get("doc_id", "")
            title = payload.get("title", "")
            chips = payload.get("chips", [])
            category = payload.get("category", "")
            await self._neo4j.upsert_document_node(doc_id, title, chips, category)

        elif event_type == "chunks.indexed":
            # The ChunkDAO payload has doc_id + chunk_ids; nothing to push to
            # Meilisearch here because we don't have the full chunk content in
            # the outbox payload.  The caller is expected to call
            # meili.index_chunks separately after bulk_insert.
            # If the full chunks dict list is provided, index them.
            chunks_data = payload.get("chunks", [])
            if chunks_data:
                await self._meili.index_chunks(chunks_data)

        elif event_type == "document.superseded":
            old_doc_id = payload.get("old_doc_id", "")
            # Update Meilisearch documents to reflect superseded status
            # We cannot do a targeted field-update in Meilisearch without
            # fetching the documents first, so we delete them instead.
            try:
                await self._meili.delete_by_document(old_doc_id)
            except StorageUnavailable as exc:
                logger.warning(
                    "Could not delete superseded doc %s from Meili: %s",
                    old_doc_id,
                    exc,
                )
                raise

        else:
            logger.debug("OutboxWorker: unknown event_type=%s, skipping", event_type)
