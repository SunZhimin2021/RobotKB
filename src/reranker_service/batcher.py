"""Async dynamic batcher for the reranker service.

Each job carries one (query, passages) request. Batching merges multiple
(query, passage) pairs into a single ONNX inference call.
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from embedding_service.model import _gpu_semaphore
from reranker_service.model import BgeRerankerModel

logger = logging.getLogger("robotkb.reranker.batcher")


class RerankJob:
    __slots__ = ("query", "passages", "top_n", "future", "_n_passages")

    def __init__(self, query: str, passages: list[str], top_n: int) -> None:
        self.query = query
        self.passages = passages
        self.top_n = top_n
        self._n_passages = len(passages)
        self.future: asyncio.Future = asyncio.get_event_loop().create_future()


class DynamicRerankerBatcher:
    def __init__(
        self,
        model: BgeRerankerModel,
        max_batch_size: int,
        max_wait_ms: int,
    ) -> None:
        self._model = model
        self._max_batch_size = max_batch_size  # pairs, not requests
        self._max_wait_s = max_wait_ms / 1000.0
        self._queue: asyncio.Queue[RerankJob] = asyncio.Queue()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rerank")
        self._running = False

    async def start(self) -> None:
        self._running = True
        asyncio.create_task(self._loop())
        logger.info("RerankerBatcher started", extra={"max_batch": self._max_batch_size})

    async def stop(self) -> None:
        self._running = False
        self._executor.shutdown(wait=False)

    async def submit(self, query: str, passages: list[str], top_n: int) -> RerankJob:
        job = RerankJob(query, passages, top_n)
        await self._queue.put(job)
        return job

    async def _loop(self) -> None:
        while self._running:
            batch: list[RerankJob] = []
            pair_count = 0

            try:
                first = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            batch.append(first)
            pair_count += first._n_passages

            deadline = time.monotonic() + self._max_wait_s
            while pair_count < self._max_batch_size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    item = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                    batch.append(item)
                    pair_count += item._n_passages
                except asyncio.TimeoutError:
                    break

            await self._run_batch(batch)

    async def _run_batch(self, batch: list[RerankJob]) -> None:
        loop = asyncio.get_event_loop()
        try:
            async with _gpu_semaphore:
                results: list[list[float]] = await loop.run_in_executor(
                    self._executor,
                    self._infer_batch,
                    batch,
                )
        except Exception as exc:
            for job in batch:
                if not job.future.done():
                    job.future.set_exception(exc)
            return

        for job, scores in zip(batch, results):
            top_n = min(job.top_n, len(scores))
            ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_n]
            job.future.set_result({"scores": scores, "ranked_indices": ranked})

    def _infer_batch(self, batch: list[RerankJob]) -> list[list[float]]:
        return [self._model.rerank(job.query, job.passages) for job in batch]
