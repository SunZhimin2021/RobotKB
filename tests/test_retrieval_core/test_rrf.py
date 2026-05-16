from retrieval_core.rrf import rrf_fuse


def test_single_list_passthrough():
    """Single-list: each chunk gets 1/(k+1) where rank is 0-indexed."""
    results = [[{"chunk_id": "a", "content": "x"}, {"chunk_id": "b", "content": "y"}]]
    fused = rrf_fuse(results, k=60)
    assert len(fused) == 2
    assert fused[0]["chunk_id"] == "a"
    assert abs(fused[0]["rrf_score"] - 1 / (60 + 1)) < 1e-9
    assert abs(fused[1]["rrf_score"] - 1 / (60 + 2)) < 1e-9


def test_multi_list_same_chunk_accumulates():
    """Chunk appearing in two lists should accumulate scores."""
    list1 = [{"chunk_id": "a", "content": "x"}]
    list2 = [{"chunk_id": "a", "content": "x"}]
    fused = rrf_fuse([list1, list2], k=60)
    assert len(fused) == 1
    expected = 1 / (60 + 1) + 1 / (60 + 1)
    assert abs(fused[0]["rrf_score"] - expected) < 1e-9


def test_empty_input_returns_empty():
    assert rrf_fuse([], k=60) == []
    assert rrf_fuse([[]], k=60) == []
    assert rrf_fuse([[], []], k=60) == []


def test_ranking_order_correct():
    """Chunk at rank 0 across two lists beats chunk at rank 1 in one list."""
    list1 = [{"chunk_id": "top", "content": "x"}, {"chunk_id": "mid", "content": "y"}]
    list2 = [{"chunk_id": "top", "content": "x"}]
    fused = rrf_fuse([list1, list2], k=60)
    assert fused[0]["chunk_id"] == "top"
    assert fused[0]["rrf_score"] > fused[1]["rrf_score"]
