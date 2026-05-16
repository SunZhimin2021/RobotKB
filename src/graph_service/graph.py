"""GraphService — Neo4j knowledge graph query service."""
from __future__ import annotations

from common.exceptions import StorageUnavailable
from storage.neo4j_client import Neo4jClient


class GraphService:
    """Neo4j 知识图谱查询服务。"""

    def __init__(self, neo4j: Neo4jClient) -> None:
        self._neo4j = neo4j

    # ── chip family ────────────────────────────────────────────────────────────

    async def chip_family_chain(self, chip_id: str) -> list[str]:
        """返回 chip_id 的整个族树（含自身），从叶到根，去重，自身排首位。

        若 chip_id 不存在，返回 []。
        查询深度限制 *0..10 防止环路。
        """
        try:
            query = """
            MATCH path = (c:Chip {id: $chip_id})-[:BELONGS_TO_FAMILY|DERIVED_FROM*0..10]->(ancestor:Chip)
            RETURN [node IN nodes(path) | node.id] AS chain
            """
            rows = await self._neo4j.run(query, chip_id=chip_id)
        except StorageUnavailable:
            raise
        except Exception as exc:
            raise StorageUnavailable(f"chip_family_chain failed: {exc}") from exc

        if not rows:
            return []

        seen: set[str] = set()
        result: list[str] = []
        for row in rows:
            for node_id in row["chain"]:
                if node_id not in seen:
                    seen.add(node_id)
                    result.append(node_id)

        # Ensure chip_id itself is first
        if chip_id in result and result[0] != chip_id:
            result.remove(chip_id)
            result.insert(0, chip_id)

        return result

    # ── boards ─────────────────────────────────────────────────────────────────

    async def boards_for_chip(self, chip_id: str) -> list[str]:
        """返回使用该芯片（或其族树中任何芯片）的 board id 列表。"""
        family = await self.chip_family_chain(chip_id)
        if not family:
            return []

        try:
            query = """
            MATCH (b:Board)-[:USES_CHIP]->(c:Chip)
            WHERE c.id IN $chip_ids
            RETURN DISTINCT b.id AS board_id
            """
            rows = await self._neo4j.run(query, chip_ids=family)
        except StorageUnavailable:
            raise
        except Exception as exc:
            raise StorageUnavailable(f"boards_for_chip failed: {exc}") from exc

        return [row["board_id"] for row in rows]

    # ── faults ─────────────────────────────────────────────────────────────────

    async def faults_for_chip(
        self,
        chip_id: str,
        symptom_tags: list[str] | None = None,
    ) -> list[dict]:
        """返回与该芯片相关的故障模式。

        返回格式: [{"fault_id": str, "description": str,
                    "symptom_tags": list, "related_doc_ids": list[str]}]
        若 symptom_tags 不为 None，过滤包含任一 tag 的故障。
        """
        family = await self.chip_family_chain(chip_id)
        chip_ids = family if family else [chip_id]

        try:
            query = """
            MATCH (f:FaultPattern)-[:OCCURS_ON]->(target)
            WHERE (target:Chip AND target.id IN $chip_ids)
               OR (target:Board AND EXISTS {
                   MATCH (target)-[:USES_CHIP]->(c:Chip) WHERE c.id IN $chip_ids
               })
            OPTIONAL MATCH (f)-[:RELATED_TO]->(doc:Document)
            RETURN f.id AS fault_id,
                   f.description AS description,
                   f.symptom_tags AS symptom_tags,
                   collect(doc.id) AS related_doc_ids
            """
            rows = await self._neo4j.run(query, chip_ids=chip_ids)
        except StorageUnavailable:
            raise
        except Exception as exc:
            raise StorageUnavailable(f"faults_for_chip failed: {exc}") from exc

        results: list[dict] = []
        for row in rows:
            tags: list[str] = row.get("symptom_tags") or []
            if symptom_tags is not None:
                filter_set = set(symptom_tags)
                if not filter_set.intersection(tags):
                    continue
            results.append(
                {
                    "fault_id": row["fault_id"],
                    "description": row.get("description") or "",
                    "symptom_tags": tags,
                    "related_doc_ids": [d for d in (row.get("related_doc_ids") or []) if d],
                }
            )
        return results

    # ── compatibility impact ───────────────────────────────────────────────────

    async def preview_compatibility_impact(
        self, chip_id: str, change_type: str = "chip_update"
    ) -> dict:
        """预览变更影响：查询依赖该芯片的文档数量和模块列表。

        返回: {"affected_boards": list[str], "affected_modules": list[str],
               "affected_document_count": int}
        """
        family = await self.chip_family_chain(chip_id)
        chip_ids = family if family else [chip_id]

        try:
            # Boards that use any chip in the family
            board_query = """
            MATCH (b:Board)-[:USES_CHIP]->(c:Chip)
            WHERE c.id IN $chip_ids
            RETURN DISTINCT b.id AS board_id
            """
            board_rows = await self._neo4j.run(board_query, chip_ids=chip_ids)
            affected_boards = [r["board_id"] for r in board_rows]

            # Modules supported by those boards
            module_query = """
            MATCH (b:Board)-[:SUPPORTS_MODULE]->(m:Module)
            WHERE b.id IN $board_ids
            RETURN DISTINCT m.id AS module_id
            """
            board_ids = affected_boards
            if board_ids:
                module_rows = await self._neo4j.run(module_query, board_ids=board_ids)
            else:
                module_rows = []
            affected_modules = [r["module_id"] for r in module_rows]

            # Documents that reference any chip in the family
            doc_query = """
            MATCH (d:Document)
            WHERE ANY(c IN d.chips WHERE c IN $chip_ids)
            RETURN count(d) AS doc_count
            """
            doc_rows = await self._neo4j.run(doc_query, chip_ids=chip_ids)
            doc_count: int = doc_rows[0]["doc_count"] if doc_rows else 0

        except StorageUnavailable:
            raise
        except Exception as exc:
            raise StorageUnavailable(f"preview_compatibility_impact failed: {exc}") from exc

        return {
            "affected_boards": affected_boards,
            "affected_modules": affected_modules,
            "affected_document_count": doc_count,
        }

    # ── upserts ────────────────────────────────────────────────────────────────

    async def upsert_chip(
        self,
        chip_id: str,
        name: str,
        family: str,
        parent_id: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        """创建或更新 Chip 节点，若有 parent_id 则创建 BELONGS_TO_FAMILY 关系。"""
        try:
            query = """
            MERGE (c:Chip {id: $chip_id})
            SET c.name    = $name,
                c.family  = $family,
                c.aliases = $aliases
            """
            await self._neo4j.run(
                query,
                chip_id=chip_id,
                name=name,
                family=family,
                aliases=aliases or [],
            )

            if parent_id:
                rel_query = """
                MATCH (c:Chip {id: $chip_id})
                MERGE (p:Chip {id: $parent_id})
                MERGE (c)-[:BELONGS_TO_FAMILY]->(p)
                """
                await self._neo4j.run(rel_query, chip_id=chip_id, parent_id=parent_id)

        except StorageUnavailable:
            raise
        except Exception as exc:
            raise StorageUnavailable(f"upsert_chip failed: {exc}") from exc

    async def upsert_board(
        self,
        board_id: str,
        name: str,
        chip_id: str,
        aliases: list[str] | None = None,
    ) -> None:
        """创建或更新 Board 节点，创建 USES_CHIP 关系。"""
        try:
            query = """
            MERGE (b:Board {id: $board_id})
            SET b.name    = $name,
                b.aliases = $aliases,
                b.chip_id = $chip_id
            WITH b
            MATCH (c:Chip {id: $chip_id})
            MERGE (b)-[:USES_CHIP]->(c)
            """
            await self._neo4j.run(
                query,
                board_id=board_id,
                name=name,
                chip_id=chip_id,
                aliases=aliases or [],
            )
        except StorageUnavailable:
            raise
        except Exception as exc:
            raise StorageUnavailable(f"upsert_board failed: {exc}") from exc

    # ── lifecycle ──────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """关闭 Neo4j 连接。"""
        await self._neo4j.close()
