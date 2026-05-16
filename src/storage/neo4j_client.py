from __future__ import annotations

from typing import Any

from neo4j import AsyncGraphDatabase

from common.exceptions import StorageUnavailable


class Neo4jClient:
    """Async Neo4j client wrapping the official neo4j driver."""

    def __init__(self, uri: str, user: str, password: str) -> None:
        self._driver = AsyncGraphDatabase.driver(
            uri, auth=(user, password)
        )

    async def run(self, query: str, **params: Any) -> list[dict]:
        """Execute a Cypher query and return results as a list of dicts."""
        try:
            async with self._driver.session() as session:
                result = await session.run(query, **params)
                records = await result.data()
                return records
        except Exception as exc:
            raise StorageUnavailable(f"Neo4j query failed: {exc}") from exc

    async def close(self) -> None:
        """Close the driver connection pool."""
        await self._driver.close()

    # ── domain helpers used by OutboxWorker ───────────────────────────────────

    async def upsert_document_node(
        self,
        doc_id: str,
        title: str,
        chips: list[str],
        category: str,
    ) -> None:
        """Create or update a Document node in the graph."""
        query = """
        MERGE (d:Document {id: $doc_id})
        SET d.title    = $title,
            d.chips    = $chips,
            d.category = $category
        """
        await self.run(query, doc_id=doc_id, title=title, chips=chips, category=category)

    async def remove_document_node(self, doc_id: str) -> None:
        """Remove a Document node (and its relationships) from the graph."""
        query = """
        MATCH (d:Document {id: $doc_id})
        DETACH DELETE d
        """
        await self.run(query, doc_id=doc_id)
