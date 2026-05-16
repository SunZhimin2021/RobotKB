"""FaultDiagnosisWorkflow — 结构化故障诊断工作流。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from common.schemas import SearchRequest
from constraint_engine.extractor import ConstraintExtractor
from graph_service.graph import GraphService
from retrieval_core.retriever import RetrievalEngine

# 停用词集合（中文常见虚词）
_STOPWORDS: frozenset[str] = frozenset({"的", "了", "是", "在", "和", "或", "但", "而"})

# 匹配中文词组（连续汉字序列，长度 > 2）
_ZH_RE = re.compile(r"[一-鿿]{3,}")

# 匹配英文技术词：全大写 或 含数字（如 I2C、TIMEOUT、ERROR、RK3588）
# 用负向预查代替 \b，避免中文字符被 Python 3 视为 \w 导致边界失效
_EN_TECH_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,}[0-9]*|[A-Za-z]+[0-9]+[A-Za-z0-9]*)(?![A-Za-z0-9])")


@dataclass
class DiagnosisCandidate:
    """单条故障诊断候选结果。"""

    fault_id: str
    description: str
    probability: float          # 0.0 – 1.0，基于 symptom 覆盖率 (Jaccard)
    symptom_tags: list[str]
    evidence_chunks: list[dict]  # 来自 retrieval 的相关 chunk
    diagnostic_steps: list[str]  # 诊断步骤（从 evidence_chunks 中提取的文本片段）
    related_doc_ids: list[str]


class FaultDiagnosisWorkflow:
    """结构化故障诊断工作流。

    依赖 M09 GraphService + M03 RetrievalEngine。
    """

    def __init__(
        self,
        graph: GraphService,
        retrieval: RetrievalEngine,
        extractor: ConstraintExtractor,
        max_candidates: int = 5,
    ) -> None:
        self._graph = graph
        self._retrieval = retrieval
        self._extractor = extractor
        self._max_candidates = max_candidates

    # ── public API ─────────────────────────────────────────────────────────────

    async def diagnose(
        self,
        symptom: str,
        context: dict | None = None,
    ) -> list[DiagnosisCandidate]:
        """执行故障诊断流程，返回按 probability 降序排列的候选列表。

        流程：
        1. 提取约束（chip/board）
        2. 获取芯片族树，确定目标 chip_id
        3. 从图谱查故障模式
        4. 对每个故障模式检索相关文档
        5. 计算 Jaccard 概率
        6. 提取诊断步骤
        7. 排序并返回 top max_candidates
        """
        # Step 1: 提取约束
        constraint = self._extractor.extract(symptom)

        # Step 2 & 3: 若有 chip 约束，查询故障模式
        symptom_tags = self._extract_symptom_tags(symptom)

        chip_id: str | None = None
        if constraint.chip:
            chip_id = constraint.chip[0]

        if chip_id is None:
            # 无 chip 约束 → 通用检索回退
            return await self._fallback_candidate(symptom, constraint, symptom_tags)

        # 获取故障模式（graph 内部会走 chip_family_chain）
        fault_patterns = await self._graph.faults_for_chip(chip_id, symptom_tags if symptom_tags else None)

        if not fault_patterns:
            return await self._fallback_candidate(symptom, constraint, symptom_tags)

        # Step 4 & 5 & 6: 对每个故障模式检索文档并计算概率
        candidates: list[DiagnosisCandidate] = []
        for fp in fault_patterns:
            query = f"{symptom} {fp['description']}"
            response = await self._retrieval.search(
                SearchRequest(query=query, constraints=constraint, top_k=5)
            )

            probability = self._jaccard(symptom_tags, fp.get("symptom_tags") or [])
            diagnostic_steps = self._extract_diagnostic_steps(response.hits)

            candidates.append(
                DiagnosisCandidate(
                    fault_id=fp["fault_id"],
                    description=fp["description"],
                    probability=probability,
                    symptom_tags=fp.get("symptom_tags") or [],
                    evidence_chunks=response.hits,
                    diagnostic_steps=diagnostic_steps,
                    related_doc_ids=fp.get("related_doc_ids") or [],
                )
            )

        # Step 7: 按 probability 降序，截取 top max_candidates
        candidates.sort(key=lambda c: c.probability, reverse=True)
        return candidates[: self._max_candidates]

    # ── helpers ────────────────────────────────────────────────────────────────

    def _extract_symptom_tags(self, symptom: str) -> list[str]:
        """简单关键词提取（不调用 LLM）。

        - 提取长度 > 2 的中文词组
        - 提取英文技术词（全大写或含数字）
        - 去停用词
        - 返回 top 5 关键词
        """
        tags: list[str] = []

        # 中文词组（>2 个汉字）
        for m in _ZH_RE.finditer(symptom):
            word = m.group()
            if word not in _STOPWORDS:
                tags.append(word)

        # 英文技术词
        for m in _EN_TECH_RE.finditer(symptom):
            word = m.group()
            if word not in _STOPWORDS:
                tags.append(word)

        # 去重（保持顺序）
        seen: set[str] = set()
        unique: list[str] = []
        for t in tags:
            if t not in seen:
                seen.add(t)
                unique.append(t)

        return unique[:5]

    @staticmethod
    def _jaccard(a: list[str], b: list[str]) -> float:
        """计算两个标签列表的 Jaccard 相似度。"""
        set_a = set(a)
        set_b = set(b)
        union = set_a | set_b
        if not union:
            return 0.1
        intersection = set_a & set_b
        return len(intersection) / len(union)

    @staticmethod
    def _extract_diagnostic_steps(hits: list[dict]) -> list[str]:
        """从 evidence_chunks 的 content 中提取以数字或 '步骤' 开头的行。"""
        steps: list[str] = []
        # 匹配：数字（含中文序号）开头，或"步骤"开头
        step_re = re.compile(r"^(?:\d+[\.、。\)）]|步骤\s*\d*)", re.MULTILINE)
        for chunk in hits:
            content = chunk.get("content", "")
            for line in content.splitlines():
                line = line.strip()
                if line and step_re.match(line):
                    steps.append(line)
        return steps

    async def _fallback_candidate(
        self,
        symptom: str,
        constraint,
        symptom_tags: list[str],
    ) -> list[DiagnosisCandidate]:
        """无故障模式时，执行通用检索并包装为单个候选。"""
        response = await self._retrieval.search(
            SearchRequest(query=symptom, constraints=constraint, top_k=5)
        )
        diagnostic_steps = self._extract_diagnostic_steps(response.hits)
        candidate = DiagnosisCandidate(
            fault_id="generic",
            description="通用检索结果（无匹配故障模式）",
            probability=0.1,
            symptom_tags=symptom_tags,
            evidence_chunks=response.hits,
            diagnostic_steps=diagnostic_steps,
            related_doc_ids=[],
        )
        return [candidate]
