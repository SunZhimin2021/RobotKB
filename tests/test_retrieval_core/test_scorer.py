import math
from datetime import datetime, timezone, timedelta
from retrieval_core.scorer import compute_final_score


def test_official_boost():
    """official source_tier gives higher score than community."""
    score_official = compute_final_score(
        rerank_score=0.5, source_tier="official", created_at=None,
        matched_constraint_count=0, is_superseded=False
    )
    score_community = compute_final_score(
        rerank_score=0.5, source_tier="community", created_at=None,
        matched_constraint_count=0, is_superseded=False
    )
    assert score_official > score_community


def test_superseded_penalty():
    """is_superseded=True subtracts 0.20 from score."""
    base = compute_final_score(
        rerank_score=0.5, source_tier=None, created_at=None,
        matched_constraint_count=0, is_superseded=False
    )
    superseded = compute_final_score(
        rerank_score=0.5, source_tier=None, created_at=None,
        matched_constraint_count=0, is_superseded=True
    )
    assert abs((base - superseded) - 0.20) < 1e-9


def test_freshness_decay():
    """Document created 1000 days ago scores lower than one created today."""
    now = datetime.now(timezone.utc)
    old_date = (now - timedelta(days=1000)).isoformat()
    new_date = now.isoformat()

    score_old = compute_final_score(
        rerank_score=0.5, source_tier=None, created_at=old_date,
        matched_constraint_count=0, is_superseded=False
    )
    score_new = compute_final_score(
        rerank_score=0.5, source_tier=None, created_at=new_date,
        matched_constraint_count=0, is_superseded=False
    )
    assert score_new > score_old


def test_perfect_match():
    """All bonuses maxed out: score > 1.0."""
    now = datetime.now(timezone.utc).isoformat()
    score = compute_final_score(
        rerank_score=1.0, source_tier="official", created_at=now,
        matched_constraint_count=3, is_superseded=False
    )
    # 1.0 + 0.15*1.0 + 0.10*1.0 + 0.10*1.0 = 1.35
    assert score > 1.0


def test_source_tier_min_has_no_direct_effect():
    """source_tier_min parameter is accepted but doesn't crash."""
    score = compute_final_score(
        rerank_score=0.5, source_tier="vendor", created_at=None,
        matched_constraint_count=1, is_superseded=False,
        source_tier_min="official"
    )
    assert isinstance(score, float)
