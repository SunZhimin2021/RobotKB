from __future__ import annotations

from typing import Any

import httpx

from common.exceptions import StorageUnavailable


class MeiliClient:
    """Thin async wrapper around the Meilisearch REST API using httpx."""

    _INDEX = "chunks"

    def __init__(self, url: str, api_key: str) -> None:
        self._base = url.rstrip("/")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers=headers,
            timeout=30.0,
        )

    # ── helpers ────────────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        try:
            resp = await self._client.request(method, path, **kwargs)
            resp.raise_for_status()
            if resp.content:
                return resp.json()
            return None
        except httpx.HTTPStatusError as exc:
            raise StorageUnavailable(
                f"Meilisearch HTTP error {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise StorageUnavailable(
                f"Meilisearch request error: {exc}"
            ) from exc

    # ── public API ─────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        filter_expr: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Perform a full-text search against the chunks index."""
        body: dict[str, Any] = {"q": query, "limit": limit}
        if filter_expr:
            body["filter"] = filter_expr

        data = await self._request(
            "POST",
            f"/indexes/{self._INDEX}/search",
            json=body,
        )
        return data.get("hits", []) if data else []

    async def index_chunks(self, chunks: list[dict]) -> None:
        """Add or replace documents in the chunks index."""
        if not chunks:
            return
        await self._request(
            "POST",
            f"/indexes/{self._INDEX}/documents",
            json=chunks,
        )

    async def delete_by_document(self, doc_id: str) -> None:
        """Delete all chunks belonging to a document using filter-based deletion."""
        await self._request(
            "POST",
            f"/indexes/{self._INDEX}/documents/delete",
            json={"filter": f"document_id = {doc_id!r}"},
        )

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()
