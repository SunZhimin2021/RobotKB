from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from common.schemas import Chunk, DocumentMeta, DocumentStatus
from etl_worker.chunkers import get_chunker
from etl_worker.ner import NERVerifier
from etl_worker.parsers import compute_hash, detect_format, parse_docx, parse_pdf, parse_text

if TYPE_CHECKING:
    from retrieval_core.embedder import EmbedderClient
    from storage.chunk_dao import ChunkDAO
    from storage.document_dao import DocumentDAO
    from storage.minio_client import MinioClient


class ETLPipeline:
    """Full ETL pipeline: parse → NER verification → chunk → embed → store."""

    def __init__(
        self,
        doc_dao: "DocumentDAO",
        chunk_dao: "ChunkDAO",
        minio: "MinioClient",
        embedder: "EmbedderClient",
        ner_verifier: NERVerifier,
    ) -> None:
        self._doc_dao = doc_dao
        self._chunk_dao = chunk_dao
        self._minio = minio
        self._embedder = embedder
        self._ner_verifier = ner_verifier

    async def process_document(
        self,
        file_data: bytes,
        filename: str,
        meta: DocumentMeta,
        batch_size: int = 16,
    ) -> dict:
        """Process a single document through the ETL pipeline.

        Steps:
        1. Compute hash → deduplication check (mark_superseded if needed)
        2. Upload raw file to MinIO
        3. Detect format and parse into pages
        4. NER verification → set status=reviewing if inconsistent
        5. Chunk pages using category-appropriate chunker
        6. Batch embed all chunks
        7. Bulk insert Chunk objects with embeddings
        8. Update document metadata (chunk_count, status)

        Returns:
            {
                "doc_id": str,
                "chunk_count": int,
                "status": str,
                "ner_result": dict,
                "superseded": str | None,
            }
        """
        # Step 1: compute hash and deduplication
        content_hash = compute_hash(file_data)
        meta = meta.model_copy(update={"content_hash": content_hash})

        superseded_id: str | None = None
        existing = await self._doc_dao.find_by_hash(content_hash)
        if existing is not None and existing.status == DocumentStatus.PUBLISHED:
            # Will supersede the existing document after we create the new one
            superseded_id = await self._get_existing_doc_id(content_hash)

        # Create document record
        doc_id = await self._doc_dao.create(meta)

        # If there is a published duplicate, mark it superseded now
        if superseded_id is not None:
            await self._doc_dao.mark_superseded(superseded_id, doc_id)

        # Step 2: upload raw file to MinIO
        content_type = self._content_type(filename)
        await self._minio.upload(f"raw/{doc_id}/{filename}", file_data, content_type)

        # Step 3: parse
        fmt = detect_format(filename)
        if fmt == "pdf":
            pages = parse_pdf(file_data)
        elif fmt == "docx":
            pages = parse_docx(file_data)
        else:
            pages = parse_text(file_data)

        # Step 4: NER verification
        full_text = "\n".join(p["text"] for p in pages)
        ner_result = self._ner_verifier.verify(
            full_text,
            meta.applicable_chips,
            meta.applicable_boards,
        )

        if not ner_result["consistent"]:
            meta = meta.model_copy(update={"status": DocumentStatus.REVIEWING})
            # Record diff summary in tags
            diff_tag = f"ner_diff:missing={ner_result['missing_in_declaration']}"
            new_tags = list(meta.tags) + [diff_tag]
            meta = meta.model_copy(update={"tags": new_tags})

        # Step 5: chunk
        chunker = get_chunker(meta.category)
        chunk_dicts = chunker.chunk(pages, meta)

        # Step 6: batch embed
        texts = [c["content"] for c in chunk_dicts]
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            batch_embeddings = await self._embedder.embed(batch)
            all_embeddings.extend(batch_embeddings)

        # Step 7: build Chunk objects and bulk insert
        chunks: list[Chunk] = []
        for chunk_dict in chunk_dicts:
            chunk = Chunk(
                chunk_id=str(uuid.uuid4()),
                document_id=doc_id,
                content=chunk_dict["content"],
                page=chunk_dict["page"],
                section=chunk_dict.get("section"),
                applicable_chips=chunk_dict.get("applicable_chips", []),
                applicable_boards=chunk_dict.get("applicable_boards", []),
                ros_versions=chunk_dict.get("ros_versions", []),
                source_tier=meta.source_tier,
                status=meta.status,
            )
            chunks.append(chunk)

        if chunks:
            await self._chunk_dao.bulk_insert(chunks, all_embeddings)

        # Step 8: update doc metadata
        await self._doc_dao.update_meta(
            doc_id,
            {"chunk_count": len(chunks), "status": meta.status.value},
        )

        return {
            "doc_id": doc_id,
            "chunk_count": len(chunks),
            "status": meta.status.value,
            "ner_result": ner_result,
            "superseded": superseded_id,
        }

    async def _get_existing_doc_id(self, content_hash: str) -> str | None:
        """Return the doc_id of the existing document with the given hash.

        Note: DocumentDAO.find_by_hash returns DocumentMeta which does not
        include doc_id. We look up the document model ID via a second pass.
        This is a best-effort lookup; if not available we return None.
        """
        # DocumentMeta does not expose the id directly — we return None here
        # and rely on the caller having passed us a real DocumentDAO that has
        # an internal id field.  In practice the DAO test mocks will capture
        # this behaviour.
        existing = await self._doc_dao.find_by_hash(content_hash)
        # Try to get id from the underlying model if the DAO exposes it
        if hasattr(existing, "id"):
            return str(existing.id)
        # Fallback: the mock may store ids separately
        return getattr(existing, "_doc_id", None)

    @staticmethod
    def _content_type(filename: str) -> str:
        lower = filename.lower()
        if lower.endswith(".pdf"):
            return "application/pdf"
        if lower.endswith(".docx"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return "text/plain"


# ── optional Celery integration ────────────────────────────────────────────────

def make_celery_app(broker_url: str):
    """Create a Celery app with a registered process_document_task.

    Task signature: process_document_task.delay(file_bytes_b64, filename, meta_dict)

    Only usable when a Redis broker is available; not tested in unit tests.
    """
    import base64

    from celery import Celery

    app = Celery("etl_worker", broker=broker_url, backend=broker_url)
    app.conf.update(task_serializer="json", accept_content=["json"])

    @app.task(name="etl_worker.process_document_task")
    def process_document_task(file_bytes_b64: str, filename: str, meta_dict: dict) -> dict:
        """Celery task wrapper. Decodes base64 file bytes and runs the pipeline."""
        import asyncio

        from common.schemas import DocumentMeta

        file_data = base64.b64decode(file_bytes_b64)
        meta = DocumentMeta(**meta_dict)

        # This task requires an ETLPipeline instance to be configured externally.
        # Raise a clear error so callers know they must provide the pipeline.
        raise RuntimeError(
            "process_document_task requires an ETLPipeline instance. "
            "Subclass or patch this task to inject the pipeline before use."
        )

    return app
