"""Tests for FaultDiagnosisWorkflow."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from common.schemas import Constraint, SearchResponse
from agent_workflows.fault_diagnosis import DiagnosisCandidate, FaultDiagnosisWorkflow


# ── helpers ────────────────────────────────────────────────────────────────────

def make_fault_pattern(
    fault_id: str = "F001",
    description: str = "I2C总线通信故障",
    symptom_tags: list[str] | None = None,
    related_doc_ids: list[str] | None = None,
) -> dict:
    return {
        "fault_id": fault_id,
        "description": description,
        "symptom_tags": symptom_tags if symptom_tags is not None else ["I2C", "超时"],
        "related_doc_ids": related_doc_ids if related_doc_ids is not None else ["doc1", "doc2"],
    }


def make_search_response(
    hits: list[dict] | None = None,
    query: str = "test",
) -> SearchResponse:
    return SearchResponse(
        query=query,
        hits=hits if hits is not None else [
            {"chunk_id": "c1", "content": "1. 检查I2C连接", "score": 0.9, "document_id": "doc1"},
            {"chunk_id": "c2", "content": "步骤2 检查总线电压", "score": 0.8, "document_id": "doc2"},
        ],
        degraded=False,
    )


def make_workflow(
    fault_patterns: list[dict] | None = None,
    search_response: SearchResponse | None = None,
    chip_constraint: list[str] | None = None,
) -> FaultDiagnosisWorkflow:
    """Build a FaultDiagnosisWorkflow with mocked dependencies."""
    graph = MagicMock()
    graph.faults_for_chip = AsyncMock(
        return_value=fault_patterns if fault_patterns is not None else [make_fault_pattern()]
    )
    graph.chip_family_chain = AsyncMock(return_value=["rk3588", "rk3588s"])

    retrieval = MagicMock()
    retrieval.search = AsyncMock(
        return_value=search_response if search_response is not None else make_search_response()
    )

    extractor = MagicMock()
    constraint = Constraint(chip=chip_constraint if chip_constraint is not None else ["rk3588"])
    extractor.extract = MagicMock(return_value=constraint)

    return FaultDiagnosisWorkflow(
        graph=graph,
        retrieval=retrieval,
        extractor=extractor,
        max_candidates=5,
    )


# ── tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_diagnose_returns_candidates():
    """diagnose() 返回 DiagnosisCandidate 列表。"""
    wf = make_workflow()
    results = await wf.diagnose("RK3588 I2C通信超时故障")

    assert isinstance(results, list)
    assert len(results) >= 1
    assert all(isinstance(c, DiagnosisCandidate) for c in results)


@pytest.mark.asyncio
async def test_probability_sorted():
    """结果按 probability 降序排列。"""
    fault_patterns = [
        make_fault_pattern("F001", "I2C故障", symptom_tags=["I2C", "超时", "ERROR"]),
        make_fault_pattern("F002", "SPI故障", symptom_tags=["SPI"]),
        make_fault_pattern("F003", "UART故障", symptom_tags=["UART", "超时"]),
    ]
    wf = make_workflow(fault_patterns=fault_patterns)
    results = await wf.diagnose("I2C总线超时ERROR")

    assert len(results) >= 2
    for i in range(len(results) - 1):
        assert results[i].probability >= results[i + 1].probability


@pytest.mark.asyncio
async def test_evidence_chunks_populated():
    """evidence_chunks 来自 retrieval.search 的 hits。"""
    hits = [
        {"chunk_id": "c1", "content": "步骤1 检查电源", "score": 0.95, "document_id": "doc1"},
        {"chunk_id": "c2", "content": "步骤2 检查连接", "score": 0.85, "document_id": "doc2"},
    ]
    wf = make_workflow(search_response=make_search_response(hits=hits))
    results = await wf.diagnose("I2C故障诊断")

    assert len(results) >= 1
    assert results[0].evidence_chunks == hits


@pytest.mark.asyncio
async def test_no_fault_pattern_fallback():
    """图谱无故障模式时返回通用检索候选（1 个）。"""
    wf = make_workflow(fault_patterns=[])
    results = await wf.diagnose("RK3588 异常故障")

    assert len(results) == 1
    assert results[0].fault_id == "generic"
    assert results[0].probability == 0.1


@pytest.mark.asyncio
async def test_symptom_tags_extracted():
    """_extract_symptom_tags 提取关键词（不含停用词）。"""
    wf = make_workflow()
    tags = wf._extract_symptom_tags("RK3588在I2C通信超时出现ERROR")

    assert "I2C" in tags or "ERROR" in tags or "RK3588" in tags
    # 停用词不应出现
    stopwords = {"的", "了", "是", "在", "和", "或", "但", "而"}
    for tag in tags:
        assert tag not in stopwords


@pytest.mark.asyncio
async def test_diagnostic_steps_from_content():
    """含数字开头行的 content → diagnostic_steps 非空。"""
    hits = [
        {"chunk_id": "c1", "content": "1. 检查I2C总线\n2. 测量电压\n普通描述行", "score": 0.9},
        {"chunk_id": "c2", "content": "步骤1 重启服务\n步骤2 查看日志", "score": 0.8},
    ]
    wf = make_workflow(search_response=make_search_response(hits=hits))
    results = await wf.diagnose("I2C故障")

    assert len(results) >= 1
    assert len(results[0].diagnostic_steps) > 0


@pytest.mark.asyncio
async def test_chip_constraint_passed_to_retrieval():
    """提取到 chip 时，传入 retrieval.search 的 constraints 包含该 chip。"""
    graph = MagicMock()
    graph.faults_for_chip = AsyncMock(return_value=[make_fault_pattern()])
    graph.chip_family_chain = AsyncMock(return_value=["rk3399"])

    retrieval = MagicMock()
    retrieval.search = AsyncMock(return_value=make_search_response())

    extractor = MagicMock()
    extractor.extract = MagicMock(return_value=Constraint(chip=["rk3399"]))

    wf = FaultDiagnosisWorkflow(
        graph=graph,
        retrieval=retrieval,
        extractor=extractor,
    )

    await wf.diagnose("RK3399 I2C故障")

    assert retrieval.search.called
    call_args = retrieval.search.call_args
    search_request = call_args.args[0] if call_args.args else call_args.kwargs.get("request")
    # retrieval.search 接受 SearchRequest 作为位置参数
    if search_request is None:
        # positional
        search_request = call_args[0][0]
    assert search_request.constraints is not None
    assert search_request.constraints.chip == ["rk3399"]


@pytest.mark.asyncio
async def test_max_candidates_respected():
    """结果数量不超过 max_candidates。"""
    fault_patterns = [
        make_fault_pattern(f"F{i:03d}", f"故障{i}") for i in range(10)
    ]
    wf = make_workflow(fault_patterns=fault_patterns)
    wf._max_candidates = 3
    results = await wf.diagnose("通用故障")

    assert len(results) <= 3


@pytest.mark.asyncio
async def test_no_chip_constraint_fallback():
    """无 chip 约束时直接走通用检索，返回 1 个 generic 候选。"""
    graph = MagicMock()
    graph.faults_for_chip = AsyncMock(return_value=[])

    retrieval = MagicMock()
    retrieval.search = AsyncMock(return_value=make_search_response())

    extractor = MagicMock()
    extractor.extract = MagicMock(return_value=Constraint())  # chip=None

    wf = FaultDiagnosisWorkflow(graph=graph, retrieval=retrieval, extractor=extractor)
    results = await wf.diagnose("电机驱动异常")

    assert len(results) == 1
    assert results[0].fault_id == "generic"
    # graph.faults_for_chip 不应被调用
    graph.faults_for_chip.assert_not_called()
