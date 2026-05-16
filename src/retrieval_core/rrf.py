from __future__ import annotations


def rrf_fuse(results: list[list[dict]], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion.

    results: each inner list is one retrieval channel's results,
             items must have "chunk_id" field.
    Returns: merged list sorted by rrf_score descending, original fields preserved.
    """
    scores: dict[str, float] = {}
    items: dict[str, dict] = {}

    for channel in results:
        for rank, item in enumerate(channel):
            cid = item["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            if cid not in items:
                items[cid] = dict(item)

    fused = []
    for cid, score in scores.items():
        entry = dict(items[cid])
        entry["rrf_score"] = score
        fused.append(entry)

    fused.sort(key=lambda x: x["rrf_score"], reverse=True)
    return fused
