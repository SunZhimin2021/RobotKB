from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from common.schemas import Constraint, SearchRequest, SearchResponse
from constraint_engine.merger import ConflictReport
from retrieval_core.retriever import RetrievalEngine


# ── fixtures ───────────────────────────────────────────────────────────────────

def make_settings(**overrides):
    s = MagicMock()
    s.rrf_k = 60
    s.retrieval_recall = 20
    s.rerank_top_n = 10
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def make_chunk_hit(chunk_id="c1", score=0.9):
    return {
        "chunk_id": chunk_id,
        "document_id": "doc1",
        "content": f"Content for {chunk_id}",
        "applicable_chips": ["rk3588"],
        "ros_versions": ["Humble"],
        "source_tier": "official",
        "status": "published",
        "score": score,
    }


def make_engine(
    chunk_hits=None,
    meili_hits=None,
    rerank_results=None,
    conflict_reports=None,
    merged_constraint=None,
    expander_constraint=None,
):
    chunk_dao = MagicMock()
    chunk_dao.vector_search = AsyncMock(return_value=chunk_hits or [make_chunk_hit()])

    meili = MagicMock()
    meili.search = AsyncMock(return_value=meili_hits or [])

    graph = MagicMock()
    graph.faults_for_chip = AsyncMock(return_value=[])

    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 10])

    reranker = MagicMock()
    reranker.rerank = AsyncMock(
        return_value=rerank_results or [{"index": 0, "score": 0.95}]
    )

    extractor = MagicMock()
    extractor.extract = MagicMock(return_value=Constraint())

    merger = MagicMock()
    merged = merged_constraint or Constraint()
    merger.merge = MagicMock(return_value=(merged, conflict_reports or []))

    classifier = MagicMock()
    classifier.classify = MagicMock(
        return_value=MagicMock(hard=Constraint(), soft=Constraint())
    )

    expander = MagicMock()
    expander.expand = AsyncMock(return_value=expander_constraint or Constraint())

    settings = make_settings()

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


# ── tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_returns_response():
    """Basic search returns a SearchResponse with hits."""
    engine = make_engine()
    request = SearchRequest(query="How to configure RK3588?", top_k=1)
    response = await engine.search(request)

    assert isinstance(response, SearchResponse)
    assert len(response.hits) <= request.top_k
    assert response.query == request.query


@pytest.mark.asyncio
async def test_search_uses_hard_constraint():
    """Hard chip constraint is forwarded to chunk_dao.vector_search."""
    hard_constraint = Constraint(chip=["rk3588"])
    soft_constraint = Constraint()

    chunk_dao = MagicMock()
    chunk_dao.vector_search = AsyncMock(return_value=[make_chunk_hit()])

    meili = MagicMock()
    meili.search = AsyncMock(return_value=[])

    graph = MagicMock()
    graph.faults_for_chip = AsyncMock(return_value=[])

    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 10])

    reranker = MagicMock()
    reranker.rerank = AsyncMock(return_value=[{"index": 0, "score": 0.95}])

    extractor = MagicMock()
    extractor.extract = MagicMock(return_value=Constraint())

    merger = MagicMock()
    merger.merge = MagicMock(return_value=(hard_constraint, []))

    classifier = MagicMock()
    classifier.classify = MagicMock(
        return_value=MagicMock(hard=hard_constraint, soft=soft_constraint)
    )

    expander = MagicMock()
    expander.expand = AsyncMock(return_value=Constraint())

    engine = RetrievalEngine(
        chunk_dao=chunk_dao,
        meili=meili,
        graph=graph,
        embedder=embedder,
        reranker=reranker,
        extractor=extractor,
        merger=merger,
        classifier=classifier,
        expander=expander,
        settings=make_settings(),
    )

    request = SearchRequest(query="RK3588 config", top_k=1)
    await engine.search(request)

    call_kwargs = chunk_dao.vector_search.call_args
    assert call_kwargs.kwargs.get("hard_chips") == ["rk3588"]


@pytest.mark.asyncio
async def test_degradation_triggered_on_empty():
    """When all channels return empty and allow_degradation=True, response is degraded."""
    chunk_dao = MagicMock()
    chunk_dao.vector_search = AsyncMock(return_value=[])

    meili = MagicMock()
    meili.search = AsyncMock(return_value=[])

    graph = MagicMock()
    graph.faults_for_chip = AsyncMock(return_value=[])

    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 10])

    reranker = MagicMock()
    reranker.rerank = AsyncMock(return_value=[])

    extractor = MagicMock()
    extractor.extract = MagicMock(return_value=Constraint())

    merger = MagicMock()
    merger.merge = MagicMock(return_value=(Constraint(), []))

    classifier = MagicMock()
    classifier.classify = MagicMock(
        return_value=MagicMock(hard=Constraint(), soft=Constraint())
    )

    expander = MagicMock()
    expander.expand = AsyncMock(return_value=Constraint())

    engine = RetrievalEngine(
        chunk_dao=chunk_dao, meili=meili, graph=graph,
        embedder=embedder, reranker=reranker, extractor=extractor,
        merger=merger, classifier=classifier, expander=expander,
        settings=make_settings(),
    )

    request = SearchRequest(query="test", top_k=5, allow_degradation=True)
    response = await engine.search(request)
    assert response.degraded is True


@pytest.mark.asyncio
async def test_no_degradation_when_disabled():
    """When allow_degradation=False, expander is never called."""
    chunk_dao = MagicMock()
    chunk_dao.vector_search = AsyncMock(return_value=[])

    meili = MagicMock()
    meili.search = AsyncMock(return_value=[])

    graph = MagicMock()
    graph.faults_for_chip = AsyncMock(return_value=[])

    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 10])

    reranker = MagicMock()
    reranker.rerank = AsyncMock(return_value=[])

    extractor = MagicMock()
    extractor.extract = MagicMock(return_value=Constraint())

    merger = MagicMock()
    merger.merge = MagicMock(return_value=(Constraint(), []))

    classifier = MagicMock()
    classifier.classify = MagicMock(
        return_value=MagicMock(hard=Constraint(), soft=Constraint())
    )

    expander = MagicMock()
    expander.expand = AsyncMock(return_value=Constraint())

    engine = RetrievalEngine(
        chunk_dao=chunk_dao, meili=meili, graph=graph,
        embedder=embedder, reranker=reranker, extractor=extractor,
        merger=merger, classifier=classifier, expander=expander,
        settings=make_settings(),
    )

    request = SearchRequest(query="test", top_k=5, allow_degradation=False)
    response = await engine.search(request)

    expander.expand.assert_not_called()
    assert response.degraded is False


@pytest.mark.asyncio
async def test_conflict_report_propagated():
    """When merger returns conflict reports, they appear in SearchResponse."""
    conflict = ConflictReport(
        field="chip",
        explicit_value="rk3588",
        implicit_value="rk3399",
        resolution="kept_explicit",
    )

    engine = make_engine(conflict_reports=[conflict])
    request = SearchRequest(query="test chip conflict", top_k=1)
    response = await engine.search(request)

    assert response.conflict_report is not None
    assert len(response.conflict_report) == 1
    assert response.conflict_report[0]["field"] == "chip"
