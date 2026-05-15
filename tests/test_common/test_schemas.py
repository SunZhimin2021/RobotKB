import pytest
from pydantic import ValidationError
from common.schemas import (
    Constraint,
    DocumentMeta,
    Chunk,
    SearchRequest,
    SearchResponse,
    MatchedConstraint,
    MatchStatus,
    SourceTier,
    DocumentCategory,
    DocumentStatus,
)


# ---------- Constraint ----------

def test_constraint_all_fields_optional():
    c = Constraint()
    assert c.chip is None
    assert c.board is None
    assert c.ros_version is None
    assert c.kernel_range is None
    assert c.source_tier_min is None
    assert c.language is None


def test_constraint_chip_as_string():
    c = Constraint(chip="RK3588")
    assert c.chip == ["RK3588"]


def test_constraint_chip_as_list():
    c = Constraint(chip=["RK3588", "RK3568"])
    assert c.chip == ["RK3588", "RK3568"]


def test_constraint_serialization():
    c = Constraint(chip="RK3588", board="Rock 5B", ros_version="humble")
    data = c.model_dump(exclude_none=True)
    assert data["chip"] == ["RK3588"]
    assert data["board"] == "Rock 5B"
    assert data["ros_version"] == "humble"


# ---------- MatchedConstraint ----------

def test_matched_constraint_exact_status():
    mc = MatchedConstraint(field="chip", value="RK3588", status=MatchStatus.EXACT)
    assert mc.status == MatchStatus.EXACT
    assert mc.note is None


def test_matched_constraint_soft_status_with_note():
    mc = MatchedConstraint(
        field="board",
        value="Rock 5B",
        status=MatchStatus.SOFT,
        note="board matched as soft constraint"
    )
    assert mc.status == MatchStatus.SOFT
    assert mc.note is not None


def test_matched_constraint_all_statuses_valid():
    for status in MatchStatus:
        mc = MatchedConstraint(field="chip", value="RK3588", status=status)
        assert mc.status == status


# ---------- DocumentMeta ----------

def test_document_meta_required_fields():
    with pytest.raises(ValidationError):
        DocumentMeta()


def test_document_meta_minimal():
    meta = DocumentMeta(
        title="RK3588 Datasheet",
        category=DocumentCategory.HARDWARE,
        source_tier=SourceTier.OFFICIAL,
        applicable_chips=["RK3588"],
    )
    assert meta.title == "RK3588 Datasheet"
    assert meta.status == DocumentStatus.PENDING


def test_document_meta_optional_fields_have_defaults():
    meta = DocumentMeta(
        title="Test Doc",
        category=DocumentCategory.SOFTWARE,
        source_tier=SourceTier.VENDOR,
        applicable_chips=["RK3568"],
    )
    assert meta.applicable_boards == []
    assert meta.ros_versions == []
    assert meta.tags == []
    assert meta.doc_version is None


def test_document_meta_serialization():
    meta = DocumentMeta(
        title="RK3588 GPIO Guide",
        category=DocumentCategory.DEVELOPMENT,
        source_tier=SourceTier.OFFICIAL,
        applicable_chips=["RK3588"],
        applicable_boards=["Rock 5B"],
    )
    data = meta.model_dump()
    assert data["title"] == "RK3588 GPIO Guide"
    assert "RK3588" in data["applicable_chips"]


# ---------- Chunk ----------

def test_chunk_required_fields():
    with pytest.raises(ValidationError):
        Chunk()


def test_chunk_minimal():
    chunk = Chunk(
        chunk_id="uuid-1234",
        document_id="doc-5678",
        content="GPIO configuration for RK3588",
        page=1,
    )
    assert chunk.chunk_id == "uuid-1234"
    assert chunk.section is None
    assert chunk.applicable_chips == []


def test_chunk_with_full_metadata():
    chunk = Chunk(
        chunk_id="uuid-abcd",
        document_id="doc-efgh",
        content="OV5640 camera init sequence",
        page=42,
        section="5.3.2 MIPI CSI-2",
        applicable_chips=["RK3588"],
        applicable_boards=["Rock 5B"],
        source_tier=SourceTier.OFFICIAL,
    )
    assert chunk.section == "5.3.2 MIPI CSI-2"
    assert chunk.source_tier == SourceTier.OFFICIAL


# ---------- SearchRequest ----------

def test_search_request_requires_query():
    with pytest.raises(ValidationError):
        SearchRequest()


def test_search_request_defaults():
    req = SearchRequest(query="RK3588 GPIO")
    assert req.top_k == 5
    assert req.include_superseded is False
    assert req.allow_degradation is True
    assert req.constraints is None


def test_search_request_with_constraints():
    req = SearchRequest(
        query="摄像头初始化",
        constraints=Constraint(chip="RK3588", board="Rock 5B"),
        top_k=10,
    )
    assert req.constraints.chip == ["RK3588"]
    assert req.top_k == 10


def test_search_request_top_k_max():
    with pytest.raises(ValidationError):
        SearchRequest(query="test", top_k=21)


def test_search_request_top_k_min():
    with pytest.raises(ValidationError):
        SearchRequest(query="test", top_k=0)


# ---------- SearchResponse ----------

def test_search_response_minimal():
    resp = SearchResponse(query="test", hits=[])
    assert resp.hits == []
    assert resp.degraded is False
    assert resp.degradation_note is None
    assert resp.total == 0


def test_search_response_with_hits():
    hit = {
        "chunk_id": "uuid-1",
        "content": "RK3588 datasheet content",
        "doc_url": "minio://bucket/doc.pdf",
        "page": 10,
        "section": "Chapter 3",
        "matched_constraints": {},
        "source_tier": "official",
        "confidence": 0.92,
        "score": 8.7,
    }
    resp = SearchResponse(query="RK3588 GPIO", hits=[hit])
    assert len(resp.hits) == 1
    assert resp.total == 1


def test_search_response_degraded():
    resp = SearchResponse(
        query="Rock 5B+ GPIO",
        hits=[],
        degraded=True,
        degradation_note="No Rock 5B+ docs; fell back to RK3588 generic",
    )
    assert resp.degraded is True
    assert resp.degradation_note is not None
