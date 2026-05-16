"""测试 create_mcp_server：Tool 注册与 Handler 调用。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import mcp.types as mcp_types
from mcp.server import Server


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_retrieval():
    m = AsyncMock()
    m.search = AsyncMock()
    return m


@pytest.fixture()
def mock_diagnosis():
    m = AsyncMock()
    m.diagnose = AsyncMock()
    return m


@pytest.fixture()
def mock_graph():
    m = AsyncMock()
    m.chip_family_chain = AsyncMock(return_value=["rk3588"])
    m.boards_for_chip = AsyncMock(return_value=["rock5b"])
    return m


@pytest.fixture()
def mock_auth():
    m = MagicMock()
    m.verify_token.return_value = True
    return m


@pytest.fixture()
def server(mock_retrieval, mock_diagnosis, mock_graph, mock_auth):
    """构建 MCP Server（使用 mock 依赖）。"""
    from mcp_server.server import create_mcp_server
    return create_mcp_server(
        retrieval=mock_retrieval,
        diagnosis=mock_diagnosis,
        graph=mock_graph,
        auth=mock_auth,
    )


# ── Helper：直接调用注册的 handler ─────────────────────────────────────────────


async def _invoke_list_tools(server: Server) -> list[mcp_types.Tool]:
    """触发 list_tools handler，返回 Tool 列表。"""
    req = mcp_types.ListToolsRequest(method="tools/list", params=None)
    result = await server.request_handlers[mcp_types.ListToolsRequest](req)
    # result 是 ServerResult(ListToolsResult(...))
    return result.root.tools


async def _invoke_call_tool(
    server: Server, name: str, arguments: dict[str, Any]
) -> list[mcp_types.TextContent]:
    """触发 call_tool handler，返回 TextContent 列表。"""
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments),
    )
    result = await server.request_handlers[mcp_types.CallToolRequest](req)
    return result.root.content


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_kb_tool_registered(server):
    """create_mcp_server 后 'search_kb' 应在 tools 列表中。"""
    tools = await _invoke_list_tools(server)
    tool_names = [t.name for t in tools]
    assert "search_kb" in tool_names


@pytest.mark.asyncio
async def test_search_kb_calls_retrieval(server, mock_retrieval):
    """调用 search_kb handler 时 retrieval.search 应被调用。"""
    from common.schemas import SearchResponse

    mock_retrieval.search.return_value = SearchResponse(
        query="test query",
        hits=[{"chunk_id": "c1", "content": "hello"}],
        degraded=False,
    )

    contents = await _invoke_call_tool(
        server, "search_kb", {"query": "test query", "top_k": 3}
    )
    mock_retrieval.search.assert_called_once()
    assert len(contents) == 1
    hits = json.loads(contents[0].text)
    assert isinstance(hits, list)


@pytest.mark.asyncio
async def test_diagnose_fault_calls_workflow(server, mock_diagnosis):
    """调用 diagnose_fault handler 时 diagnosis.diagnose 应被调用。"""
    from agent_workflows.fault_diagnosis import DiagnosisCandidate

    mock_diagnosis.diagnose.return_value = [
        DiagnosisCandidate(
            fault_id="fault-001",
            description="电源不足",
            probability=0.85,
            symptom_tags=["power"],
            evidence_chunks=[],
            diagnostic_steps=["检查电源"],
            related_doc_ids=["doc-001"],
        )
    ]

    contents = await _invoke_call_tool(
        server, "diagnose_fault", {"symptom": "系统启动失败"}
    )
    mock_diagnosis.diagnose.assert_called_once_with(
        symptom="系统启动失败", context=None
    )
    assert len(contents) == 1
    candidates = json.loads(contents[0].text)
    assert isinstance(candidates, list)
    assert candidates[0]["fault_id"] == "fault-001"


@pytest.mark.asyncio
async def test_kb_exception_returns_text(server, mock_retrieval):
    """retrieval 抛 NoHitError 时，返回含错误信息的 TextContent。"""
    from common.exceptions import NoHitError

    mock_retrieval.search.side_effect = NoHitError("没有找到相关文档")

    contents = await _invoke_call_tool(
        server, "search_kb", {"query": "impossible query"}
    )
    assert len(contents) == 1
    assert "NoHitError" in contents[0].text


@pytest.mark.asyncio
async def test_list_chips_reads_yaml(server):
    """list_chips 返回芯片列表（非空，包含 id/names/family 字段）。"""
    contents = await _invoke_call_tool(server, "list_chips", {})
    assert len(contents) == 1
    chips = json.loads(contents[0].text)
    assert isinstance(chips, list)
    assert len(chips) > 0
    # 验证字段结构
    first = chips[0]
    assert "id" in first
    assert "names" in first
    assert "family" in first
