from __future__ import annotations

import httpx


class RerankerClient:
    """Async client for OpenAI-compatible rerank API (POST /v1/rerank)."""

    def __init__(self, url: str, model: str) -> None:
        self._url = url.rstrip("/") + "/v1/rerank"
        self._model = model
        self._client = httpx.AsyncClient(timeout=30.0)

    async def rerank(
        self, query: str, passages: list[str], top_n: int
    ) -> list[dict]:
        """Rerank passages against query.

        Returns list of {"index": int, "score": float} sorted by score descending.
        index corresponds to position in the input passages list.
        """
        if not passages:
            return []
        resp = await self._client.post(
            self._url,
            json={
                "model": self._model,
                "query": query,
                "documents": passages,
                "top_n": top_n,
            },
        )
        resp.raise_for_status()
        results = resp.json()["results"]
        return [
            {"index": r["index"], "score": r["relevance_score"]}
            for r in sorted(results, key=lambda x: x["relevance_score"], reverse=True)
        ]

    async def close(self) -> None:
        await self._client.aclose()
