"""Async dynamic batcher for the embedding service.

Collects incoming embed requests into micro-batches and runs them together
to amortize GPU launch overhead.

Flow:
  1. Caller puts (texts, type, future) into _queue.
  2. Background loop accumulates items up to max_batch_size OR max_wait_ms.
  3. Batch is run under _gpu_semaphore in a thread pool executor.
  4. Results are distributed back via per-request asyncio.Future.
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from embedding_service.model import BgeM3Model, _gpu_semaphore
from embedding_service.schemas import EmbedType, SparseVector

logger = logging.getLogger("robotkb.embedding.batcher")


class EmbedJob:
    __slots__ = ("texts", "embed_type", "future")

    def __init__(self, texts: list[str], embed_type: EmbedType) -> None:
        self.texts = texts
        self.embed_type = embed_type
        self.future: asyncio.Future = asyncio.get_event_loop().create_future()


class DynamicBatcher:
    def __init__(
        self,
        model: BgeM3Model,
        max_batch_size: int,
        max_wait_ms: int,
    ) -> None:
        self._model = model
        self._max_batch_size = max_batch_size
        self._max_wait_s = max_wait_ms / 1000.0
        self._queue: asyncio.Queue[EmbedJob] = asyncio.Queue()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="embed")
        self._running = False

    async def start(self) -> None:
        self._running = True
        asyncio.create_task(self._loop())
        logger.info("EmbedBatcher started", extra={"max_batch": self._max_batch_size})

    async def stop(self) -> None:
        self._running = False
        self._executor.shutdown(wait=False)

    async def submit(self, texts: list[str], embed_type: EmbedType) -> EmbedJob:
        job = EmbedJob(texts, embed_type)
        await self._queue.put(job)
        return job

    # ------------------------------------------------------------------
    # Internal batch loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while self._running:
            batch: list[EmbedJob] = []

            # Wait for the first item (blocking)
            try:
                first = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            batch.append(first)

            # Drain up to max_batch_size within max_wait_ms
            deadline = time.monotonic() + self._max_wait_s
            while len(batch) < self._max_batch_size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                    batch.append(item)
                except asyncio.TimeoutError:
                    break

            await self._run_batch(batch)

    async def _run_batch(self, batch: list[EmbedJob]) -> None:
        # Group by embed_type so we run each type once
        by_type: dict[EmbedType, list[tuple[int, list[str]]]] = {}
        offset = 0
        for job in batch:
            et = job.embed_type
            if et not in by_type:
                by_type[et] = []
            by_type[et].append((offset, job.texts))
            offset += len(job.texts)

        # Flatten all texts in insertion order for bulk inference
        all_texts: list[str] = []
        for job in batch:
            all_texts.extend(job.texts)

        loop = asyncio.get_event_loop()
        try:
            async with _gpu_semaphore:
                results = await loop.run_in_executor(
                    self._executor,
                    self._infer_all,
                    all_texts,
                    list(by_type.keys()),
                )
        except Exception as exc:
            for job in batch:
                if not job.future.done():
                    job.future.set_exception(exc)
            return

        # Distribute results back to each job's future
        text_offset = 0
        dense_all, sparse_all = results
        for job in batch:
            n = len(job.texts)
            sliced_dense = dense_all[text_offset : text_offset + n] if dense_all else None
            sliced_sparse = sparse_all[text_offset : text_offset + n] if sparse_all else None

            payload: dict = {}
            if sliced_dense is not None:
                payload["dense"] = sliced_dense
            if sliced_sparse is not None:
                payload["sparse"] = [
                    SparseVector(
                        indices=list(sv.keys()),
                        values=list(sv.values()),
                    )
                    for sv in sliced_sparse
                ]
            job.future.set_result(payload)
            text_offset += n

    def _infer_all(
        self,
        texts: list[str],
        types: list[EmbedType],
    ) -> tuple[list[list[float]] | None, list[dict[int, float]] | None]:
        need_dense = any(t in (EmbedType.DENSE, EmbedType.BOTH) for t in types)
        need_sparse = any(t in (EmbedType.SPARSE, EmbedType.BOTH) for t in types)

        dense = self._model.embed_dense(texts) if need_dense else None
        sparse = self._model.embed_sparse(texts) if need_sparse else None
        return dense, sparse
