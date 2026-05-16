from __future__ import annotations

import math
from datetime import datetime, timezone

_TIER_BOOST = {
    "official": 1.0,
    "vendor": 0.7,
    "community": 0.4,
    "internal_draft": 0.2,
}


def compute_final_score(
    rerank_score: float,
    source_tier: str | None,
    created_at: str | None,       # ISO 8601
    matched_constraint_count: int,
    is_superseded: bool,
    source_tier_min: str | None = None,
) -> float:
    """Compute final ranking score combining rerank score with metadata boosts.

    final = rerank_score
          + 0.15 * boost_source_tier     (official=1.0, vendor=0.7, community=0.4, internal_draft=0.2)
          + 0.10 * boost_freshness       (exp(-days/365))
          + 0.10 * boost_constraint_match (matched_count / 3, capped at 1.0)
          - 0.20 * penalty_superseded    (1.0 if superseded else 0.0)
    """
    # Source tier boost
    boost_tier = _TIER_BOOST.get(source_tier or "", 0.0) if source_tier else 0.0

    # Freshness boost: exponential decay
    boost_freshness = 0.0
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - dt).days
            boost_freshness = math.exp(-days / 365.0)
        except (ValueError, OSError):
            boost_freshness = 0.0

    # Constraint match boost
    boost_constraint = min(matched_constraint_count / 3.0, 1.0)

    # Superseded penalty
    penalty = 1.0 if is_superseded else 0.0

    return (
        rerank_score
        + 0.15 * boost_tier
        + 0.10 * boost_freshness
        + 0.10 * boost_constraint
        - 0.20 * penalty
    )
