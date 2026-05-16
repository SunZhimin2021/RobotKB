"""Unit tests for GraphService — no real Neo4j connection."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from graph_service.graph import GraphService


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_neo4j(side_effects: list | None = None, return_value: list | None = None) -> AsyncMock:
    """Create a mock Neo4jClient with a pre-configured run() coroutine."""
    client = MagicMock()
    if side_effects is not None:
        client.run = AsyncMock(side_effect=side_effects)
    else:
        client.run = AsyncMock(return_value=return_value if return_value is not None else [])
    client.close = AsyncMock()
    return client


# ── chip_family_chain ──────────────────────────────────────────────────────────

class TestChipFamilyChain:
    async def test_chip_family_chain_self_included(self):
        """chip_family_chain always includes the requested chip_id."""
        neo4j = _make_neo4j(return_value=[{"chain": ["rk3588s", "rk3588"]}])
        svc = GraphService(neo4j)

        result = await svc.chip_family_chain("rk3588s")

        assert "rk3588s" in result

    async def test_chip_family_chain_parent_included(self):
        """chip_family_chain includes parent nodes from the ancestry path."""
        neo4j = _make_neo4j(return_value=[{"chain": ["rk3588s", "rk3588"]}])
        svc = GraphService(neo4j)

        result = await svc.chip_family_chain("rk3588s")

        assert "rk3588" in result

    async def test_chip_family_chain_self_first(self):
        """chip_id itself must be the first element in the returned list."""
        neo4j = _make_neo4j(return_value=[{"chain": ["rk3588s", "rk3588"]}])
        svc = GraphService(neo4j)

        result = await svc.chip_family_chain("rk3588s")

        assert result[0] == "rk3588s"

    async def test_chip_family_chain_empty_if_not_found(self):
        """chip_family_chain returns [] when Neo4j returns no rows."""
        neo4j = _make_neo4j(return_value=[])
        svc = GraphService(neo4j)

        result = await svc.chip_family_chain("nonexistent_chip")

        assert result == []

    async def test_chip_family_chain_deduplicates(self):
        """chip_family_chain deduplicates node ids from multiple paths."""
        # Two rows sharing "rk3588s" and "rk3588"
        neo4j = _make_neo4j(
            return_value=[
                {"chain": ["rk3588s", "rk3588"]},
                {"chain": ["rk3588s", "rk3588"]},
            ]
        )
        svc = GraphService(neo4j)

        result = await svc.chip_family_chain("rk3588s")

        assert result.count("rk3588s") == 1
        assert result.count("rk3588") == 1

    async def test_chip_cycle_detection(self):
        """Query depth is bounded at *0..10 to prevent infinite cycles.

        We verify the Cypher passed to neo4j.run contains the depth limit.
        """
        neo4j = _make_neo4j(return_value=[{"chain": ["rk3588s"]}])
        svc = GraphService(neo4j)

        await svc.chip_family_chain("rk3588s")

        call_args = neo4j.run.call_args
        cypher: str = call_args.args[0] if call_args.args else call_args.kwargs.get("query", "")
        assert "*0..10" in cypher, f"Expected '*0..10' depth limit in Cypher, got:\n{cypher}"


# ── boards_for_chip ────────────────────────────────────────────────────────────

class TestBoardsForChip:
    async def test_boards_for_chip_basic(self):
        """boards_for_chip returns correct board id list."""
        # First call: chip_family_chain query → single-node path
        # Second call: boards query
        neo4j = _make_neo4j(
            side_effects=[
                [{"chain": ["rk3588s"]}],              # chip_family_chain
                [{"board_id": "rock5b"}, {"board_id": "rock5c"}],  # boards query
            ]
        )
        svc = GraphService(neo4j)

        result = await svc.boards_for_chip("rk3588s")

        assert "rock5b" in result
        assert "rock5c" in result

    async def test_boards_for_chip_empty(self):
        """boards_for_chip returns [] when no boards use the chip family."""
        neo4j = _make_neo4j(
            side_effects=[
                [{"chain": ["rk3588s"]}],  # chip_family_chain
                [],                         # no boards
            ]
        )
        svc = GraphService(neo4j)

        result = await svc.boards_for_chip("rk3588s")

        assert result == []

    async def test_boards_for_chip_not_found_chip(self):
        """boards_for_chip returns [] when chip does not exist."""
        neo4j = _make_neo4j(
            side_effects=[
                [],  # chip_family_chain returns empty (chip not found)
            ]
        )
        svc = GraphService(neo4j)

        result = await svc.boards_for_chip("ghost_chip")

        assert result == []


# ── faults_for_chip ────────────────────────────────────────────────────────────

class TestFaultsForChip:
    async def test_faults_for_chip_returns_list(self):
        """faults_for_chip returns a list of dicts with required keys."""
        fault_row = {
            "fault_id": "fp001",
            "description": "Boot failure",
            "symptom_tags": ["no_boot", "power"],
            "related_doc_ids": ["doc1"],
        }
        neo4j = _make_neo4j(
            side_effects=[
                [{"chain": ["rk3588s"]}],  # chip_family_chain
                [fault_row],               # faults query
            ]
        )
        svc = GraphService(neo4j)

        result = await svc.faults_for_chip("rk3588s")

        assert len(result) == 1
        assert result[0]["fault_id"] == "fp001"
        assert "description" in result[0]
        assert "symptom_tags" in result[0]
        assert "related_doc_ids" in result[0]

    async def test_faults_filter_by_symptom(self):
        """faults_for_chip filters results to those matching any given symptom_tag."""
        fault_match = {
            "fault_id": "fp001",
            "description": "Boot failure",
            "symptom_tags": ["no_boot", "power"],
            "related_doc_ids": [],
        }
        fault_no_match = {
            "fault_id": "fp002",
            "description": "USB issue",
            "symptom_tags": ["usb_error"],
            "related_doc_ids": [],
        }
        neo4j = _make_neo4j(
            side_effects=[
                [{"chain": ["rk3588s"]}],          # chip_family_chain
                [fault_match, fault_no_match],      # faults query
            ]
        )
        svc = GraphService(neo4j)

        result = await svc.faults_for_chip("rk3588s", symptom_tags=["no_boot"])

        assert len(result) == 1
        assert result[0]["fault_id"] == "fp001"

    async def test_faults_for_chip_no_filter(self):
        """faults_for_chip returns all faults when symptom_tags is None."""
        faults = [
            {"fault_id": "fp001", "description": "A", "symptom_tags": ["x"], "related_doc_ids": []},
            {"fault_id": "fp002", "description": "B", "symptom_tags": ["y"], "related_doc_ids": []},
        ]
        neo4j = _make_neo4j(
            side_effects=[
                [{"chain": ["rk3588s"]}],
                faults,
            ]
        )
        svc = GraphService(neo4j)

        result = await svc.faults_for_chip("rk3588s", symptom_tags=None)

        assert len(result) == 2


# ── preview_compatibility_impact ───────────────────────────────────────────────

class TestPreviewCompatibilityImpact:
    async def test_compatibility_impact_structure(self):
        """preview_compatibility_impact returns dict with required keys."""
        neo4j = _make_neo4j(
            side_effects=[
                [{"chain": ["rk3588s"]}],          # chip_family_chain
                [{"board_id": "rock5b"}],           # boards query
                [{"module_id": "wifi"}],            # modules query
                [{"doc_count": 3}],                 # document count query
            ]
        )
        svc = GraphService(neo4j)

        result = await svc.preview_compatibility_impact("rk3588s")

        assert "affected_boards" in result
        assert "affected_modules" in result
        assert "affected_document_count" in result

    async def test_compatibility_impact_values(self):
        """preview_compatibility_impact returns correct board/module/doc data."""
        neo4j = _make_neo4j(
            side_effects=[
                [{"chain": ["rk3588s"]}],
                [{"board_id": "rock5b"}, {"board_id": "rock5c"}],
                [{"module_id": "wifi"}, {"module_id": "gpio"}],
                [{"doc_count": 5}],
            ]
        )
        svc = GraphService(neo4j)

        result = await svc.preview_compatibility_impact("rk3588s")

        assert set(result["affected_boards"]) == {"rock5b", "rock5c"}
        assert set(result["affected_modules"]) == {"wifi", "gpio"}
        assert result["affected_document_count"] == 5

    async def test_compatibility_impact_no_boards(self):
        """preview_compatibility_impact handles zero boards/modules correctly."""
        neo4j = _make_neo4j(
            side_effects=[
                [{"chain": ["rk3588s"]}],
                [],                           # no boards
                [{"doc_count": 0}],           # doc count (modules query skipped)
            ]
        )
        svc = GraphService(neo4j)

        result = await svc.preview_compatibility_impact("rk3588s")

        assert result["affected_boards"] == []
        assert result["affected_modules"] == []
        assert result["affected_document_count"] == 0


# ── upsert_chip ────────────────────────────────────────────────────────────────

class TestUpsertChip:
    async def test_upsert_chip_calls_neo4j(self):
        """upsert_chip calls neo4j.run() at least once."""
        neo4j = _make_neo4j(return_value=[])
        svc = GraphService(neo4j)

        await svc.upsert_chip("rk3588s", name="RK3588S", family="rk3588")

        assert neo4j.run.call_count >= 1

    async def test_upsert_chip_with_parent_creates_relationship(self):
        """upsert_chip with parent_id calls neo4j.run() twice (node + relationship)."""
        neo4j = _make_neo4j(return_value=[])
        svc = GraphService(neo4j)

        await svc.upsert_chip(
            "rk3588s", name="RK3588S", family="rk3588", parent_id="rk3588"
        )

        # One call for MERGE node, one for BELONGS_TO_FAMILY relationship
        assert neo4j.run.call_count == 2

    async def test_upsert_chip_without_parent_single_call(self):
        """upsert_chip without parent_id makes exactly one neo4j.run() call."""
        neo4j = _make_neo4j(return_value=[])
        svc = GraphService(neo4j)

        await svc.upsert_chip("rk3588", name="RK3588", family="rk3588")

        assert neo4j.run.call_count == 1


# ── upsert_board ───────────────────────────────────────────────────────────────

class TestUpsertBoard:
    async def test_upsert_board_calls_neo4j(self):
        """upsert_board calls neo4j.run() at least once."""
        neo4j = _make_neo4j(return_value=[])
        svc = GraphService(neo4j)

        await svc.upsert_board("rock5b", name="Rock 5B", chip_id="rk3588s")

        assert neo4j.run.call_count >= 1


# ── close ──────────────────────────────────────────────────────────────────────

class TestClose:
    async def test_close_delegates_to_neo4j(self):
        """close() calls neo4j.close()."""
        neo4j = _make_neo4j(return_value=[])
        svc = GraphService(neo4j)

        await svc.close()

        neo4j.close.assert_awaited_once()
