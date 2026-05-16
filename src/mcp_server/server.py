"""MCP Server 工厂函数 — 注册 Tools 和 Resources。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl

from agent_workflows.fault_diagnosis import FaultDiagnosisWorkflow
from common.exceptions import KBException
from common.schemas import Constraint, SearchRequest
from graph_service.graph import GraphService
from mcp_server.auth import MCPAuth
from retrieval_core.retriever import RetrievalEngine

logger = logging.getLogger(__name__)

# data/ 目录相对于项目根（向上三级：src/mcp_server → src → robotkb）
_DATA_DIR = Path(__file__).parent.parent.parent / "data"

# kb exception code → 前缀映射
_KB_ERROR_PREFIXES: dict[int, str] = {
    40001: "ConstraintExtractError",
    40002: "NoHitError",
    40003: "ConstraintConflictError",
    50001: "StorageUnavailable",
    50002: "InferenceUnavailable",
}


def _kb_error_content(exc: KBException) -> list[TextContent]:
    prefix = _KB_ERROR_PREFIXES.get(exc.code, "KBError")
    return [TextContent(type="text", text=f"{prefix}: {exc}")]


def _load_yaml(filename: str) -> Any:
    path = _DATA_DIR / filename
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_mcp_server(
    retrieval: RetrievalEngine,
    diagnosis: FaultDiagnosisWorkflow,
    graph: GraphService,
    auth: MCPAuth,
) -> Server:
    """注册 MCP Tools 和 Resources，返回 Server 实例。"""

    server = Server("robotkb", version="0.1.0")

    # ── Tool 列表 ──────────────────────────────────────────────────────────────

    _TOOLS: list[Tool] = [
        Tool(
            name="search_kb",
            description="在 RobotKB 知识库中语义检索文档片段。",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索查询"},
                    "chips": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": "芯片 ID 列表（可选）",
                    },
                    "board": {"type": ["string", "null"], "description": "主板 ID（可选）"},
                    "ros_version": {
                        "type": ["string", "null"],
                        "description": "ROS 版本（可选）",
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                        "description": "返回条数",
                    },
                    "allow_degradation": {
                        "type": "boolean",
                        "default": True,
                        "description": "是否允许降级检索",
                    },
                    "_token": {"type": ["string", "null"], "description": "Bearer token（可选）"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="diagnose_fault",
            description="根据症状描述诊断可能的故障原因及诊断步骤。",
            inputSchema={
                "type": "object",
                "properties": {
                    "symptom": {"type": "string", "description": "故障症状描述"},
                    "context": {
                        "type": ["object", "null"],
                        "description": "附加上下文（芯片、板卡、ROS 版本等）",
                    },
                    "_token": {"type": ["string", "null"], "description": "Bearer token（可选）"},
                },
                "required": ["symptom"],
            },
        ),
        Tool(
            name="check_compatibility",
            description="查询芯片的家族链和兼容板卡列表。",
            inputSchema={
                "type": "object",
                "properties": {
                    "chip_id": {"type": "string", "description": "芯片 ID"},
                    "_token": {"type": ["string", "null"], "description": "Bearer token（可选）"},
                },
                "required": ["chip_id"],
            },
        ),
        Tool(
            name="list_chips",
            description="列出知识库支持的所有芯片。",
            inputSchema={
                "type": "object",
                "properties": {
                    "_token": {"type": ["string", "null"], "description": "Bearer token（可选）"},
                },
            },
        ),
        Tool(
            name="list_boards",
            description="列出知识库支持的所有主板。",
            inputSchema={
                "type": "object",
                "properties": {
                    "_token": {"type": ["string", "null"], "description": "Bearer token（可选）"},
                },
            },
        ),
        Tool(
            name="submit_feedback",
            description="提交对检索结果的评分和评论反馈。",
            inputSchema={
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string", "description": "文档片段 ID"},
                    "rating": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                        "description": "评分（1-5）",
                    },
                    "comment": {
                        "type": ["string", "null"],
                        "description": "评论（可选）",
                    },
                    "_token": {"type": ["string", "null"], "description": "Bearer token（可选）"},
                },
                "required": ["chunk_id", "rating"],
            },
        ),
    ]

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return _TOOLS

    # ── Tool 处理器 ─────────────────────────────────────────────────────────────

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict[str, Any]
    ) -> list[TextContent]:
        # token 验证（可选；若提供则验证）
        token = arguments.get("_token")
        if token and not auth.verify_token(token):
            return [TextContent(type="text", text="Unauthorized: invalid token")]

        if name == "search_kb":
            return await _handle_search_kb(arguments)
        elif name == "diagnose_fault":
            return await _handle_diagnose_fault(arguments)
        elif name == "check_compatibility":
            return await _handle_check_compatibility(arguments)
        elif name == "list_chips":
            return await _handle_list_chips(arguments)
        elif name == "list_boards":
            return await _handle_list_boards(arguments)
        elif name == "submit_feedback":
            return await _handle_submit_feedback(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    # ── 各 Tool 实现 ─────────────────────────────────────────────────────────────

    async def _handle_search_kb(args: dict[str, Any]) -> list[TextContent]:
        try:
            chips = args.get("chips")
            board = args.get("board")
            ros_version = args.get("ros_version")
            constraint = None
            if chips or board or ros_version:
                constraint = Constraint(
                    chip=chips,
                    board=board,
                    ros_version=ros_version,
                )
            request = SearchRequest(
                query=args["query"],
                constraints=constraint,
                top_k=args.get("top_k", 5),
                allow_degradation=args.get("allow_degradation", True),
            )
            response = await retrieval.search(request)
            return [TextContent(type="text", text=json.dumps(response.hits, ensure_ascii=False))]
        except KBException as e:
            return _kb_error_content(e)

    async def _handle_diagnose_fault(args: dict[str, Any]) -> list[TextContent]:
        try:
            candidates = await diagnosis.diagnose(
                symptom=args["symptom"],
                context=args.get("context"),
            )
            result = []
            for c in candidates:
                result.append({
                    "fault_id": c.fault_id,
                    "description": c.description,
                    "probability": c.probability,
                    "symptom_tags": c.symptom_tags,
                    "evidence_chunks": c.evidence_chunks,
                    "diagnostic_steps": c.diagnostic_steps,
                    "related_doc_ids": c.related_doc_ids,
                })
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
        except KBException as e:
            return _kb_error_content(e)

    async def _handle_check_compatibility(args: dict[str, Any]) -> list[TextContent]:
        try:
            chip_id = args["chip_id"]
            chip_family = await graph.chip_family_chain(chip_id)
            compatible_boards = await graph.boards_for_chip(chip_id)
            result = {
                "chip_family": chip_family,
                "compatible_boards": compatible_boards,
            }
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
        except KBException as e:
            return _kb_error_content(e)

    async def _handle_list_chips(_args: dict[str, Any]) -> list[TextContent]:
        data = _load_yaml("chips.yaml")
        chips = data.get("chips", [])
        result = [
            {"id": c["id"], "names": c.get("names", []), "family": c.get("family", "")}
            for c in chips
        ]
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    async def _handle_list_boards(_args: dict[str, Any]) -> list[TextContent]:
        data = _load_yaml("boards.yaml")
        boards = data.get("boards", [])
        result = [
            {"id": b["id"], "names": b.get("names", []), "chip_id": b.get("chip_id", "")}
            for b in boards
        ]
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]

    async def _handle_submit_feedback(args: dict[str, Any]) -> list[TextContent]:
        chunk_id = args["chunk_id"]
        rating = args["rating"]
        comment = args.get("comment")
        logger.info(
            "Feedback received: chunk_id=%s rating=%s comment=%r",
            chunk_id,
            rating,
            comment,
        )
        return [TextContent(type="text", text=json.dumps({"status": "accepted"}))]

    # ── Resources ───────────────────────────────────────────────────────────────

    from common.schemas import DocumentCategory  # noqa: PLC0415 (local import for closure)

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        return [
            Resource(
                uri=AnyUrl("kb://manifest"),
                name="RobotKB Manifest",
                description="服务清单：名称、版本、工具列表",
                mimeType="application/json",
            ),
            Resource(
                uri=AnyUrl("kb://chips"),
                name="Chips",
                description="支持的芯片列表",
                mimeType="application/x-yaml",
            ),
            Resource(
                uri=AnyUrl("kb://boards"),
                name="Boards",
                description="支持的主板列表",
                mimeType="application/x-yaml",
            ),
            Resource(
                uri=AnyUrl("kb://taxonomy"),
                name="Taxonomy",
                description="文档分类体系（DocumentCategory 枚举）",
                mimeType="application/json",
            ),
            Resource(
                uri=AnyUrl("kb://stats"),
                name="Stats",
                description="运行状态",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
        uri_str = str(uri)

        if uri_str == "kb://manifest":
            manifest = {
                "name": "RobotKB",
                "version": "0.1.0",
                "tools": [t.name for t in _TOOLS],
            }
            return [ReadResourceContents(content=json.dumps(manifest, ensure_ascii=False), mime_type="application/json")]

        elif uri_str == "kb://chips":
            path = _DATA_DIR / "chips.yaml"
            content = path.read_text(encoding="utf-8")
            return [ReadResourceContents(content=content, mime_type="application/x-yaml")]

        elif uri_str == "kb://boards":
            path = _DATA_DIR / "boards.yaml"
            content = path.read_text(encoding="utf-8")
            return [ReadResourceContents(content=content, mime_type="application/x-yaml")]

        elif uri_str == "kb://taxonomy":
            taxonomy = {
                "categories": [{"name": e.name, "value": e.value} for e in DocumentCategory]
            }
            return [ReadResourceContents(content=json.dumps(taxonomy, ensure_ascii=False), mime_type="application/json")]

        elif uri_str == "kb://stats":
            stats = {"status": "ok"}
            return [ReadResourceContents(content=json.dumps(stats), mime_type="application/json")]

        else:
            raise ValueError(f"Unknown resource URI: {uri_str}")

    return server
