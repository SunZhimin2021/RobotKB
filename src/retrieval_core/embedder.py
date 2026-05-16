from __future__ import annotations

import httpx


class EmbedderClient:
    """Async client for OpenAI-compatible embedding API (POST /v1/embeddings)."""

    def __init__(self, url: str, model: str) -> None:
        self._url = url.rstrip("/") + "/v1/embeddings"
        self._model = model
        self._client = httpx.AsyncClient(timeout=30.0)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch embed texts, return [N, dim] list of embeddings."""
        resp = await self._client.post(
            self._url,
            json={"model": self._model, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]

    async def close(self) -> None:
        await self._client.aclose()
