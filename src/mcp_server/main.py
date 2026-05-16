"""MCP Server 启动入口（stdio 模式）。"""
from __future__ import annotations

import asyncio
import logging

from mcp.server import NotificationOptions
from mcp.server.stdio import stdio_server

from agent_workflows.fault_diagnosis import FaultDiagnosisWorkflow
from common.config import get_settings
from common.logging import setup_logging
from constraint_engine.extractor import ConstraintExtractor
from graph_service.graph import GraphService
from mcp_server.auth import MCPAuth
from mcp_server.server import create_mcp_server
from retrieval_core.retriever import RetrievalEngine
from storage.chunk_dao import ChunkDAO
from storage.database import get_engine
from storage.meili_client import MeiliClient
from storage.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


async def _build_retrieval_engine(settings) -> RetrievalEngine:
    """根据 settings 构建所有底层依赖，组装 RetrievalEngine。"""
    from constraint_engine.classifier import ConstraintClassifier
    from constraint_engine.expander import ConstraintExpander
    from constraint_engine.merger import ConstraintMerger
    from retrieval_core.embedder import EmbedderClient
    from retrieval_core.reranker import RerankerClient

    chunk_dao = ChunkDAO(get_engine(settings.pg_dsn))
    meili = MeiliClient(settings.meili_url, settings.meili_api_key)
    graph = GraphService(
        Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    )
    embedder = EmbedderClient(settings.embedding_url, settings.embedding_model)
    reranker = RerankerClient(settings.reranker_url, settings.reranker_model)
    extractor = ConstraintExtractor()
    merger = ConstraintMerger()
    classifier = ConstraintClassifier()
    expander = ConstraintExpander(graph)

    return RetrievalEngine(
        chunk_dao=chunk_dao,
        meili=meili,
        graph=graph,
        embedder=embedder,
        reranker=reranker,
        extractor=extractor,
        merger=merger,
        classifier=classifier,
        expander=expander,
        settings=settings,
    )


async def main() -> None:
    """构建所有依赖，启动 stdio 模式 MCP Server。"""
    setup_logging()
    settings = get_settings()
    logger.info("Starting RobotKB MCP Server (stdio mode)")

    retrieval = await _build_retrieval_engine(settings)
    graph = GraphService(
        Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    )
    extractor = ConstraintExtractor()
    diagnosis = FaultDiagnosisWorkflow(
        graph=graph,
        retrieval=retrieval,
        extractor=extractor,
    )
    auth = MCPAuth()

    server = create_mcp_server(
        retrieval=retrieval,
        diagnosis=diagnosis,
        graph=graph,
        auth=auth,
    )

    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options(
            notification_options=NotificationOptions(),
        )
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(main())
