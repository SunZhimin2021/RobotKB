from __future__ import annotations

import asyncio
import logging

from common.schemas import Constraint, SearchRequest, SearchResponse
from retrieval_core.rrf import rrf_fuse
from retrieval_core.scorer import compute_final_score

logger = logging.getLogger(__name__)


class RetrievalEngine:
    """Four-channel recall → RRF fusion → Rerank → Final score → Degradation."""

    def __init__(
        self,
        chunk_dao,       # ChunkDAO
        meili,           # MeiliClient
        graph,           # GraphService
        embedder,        # EmbedderClient
        reranker,        # RerankerClient
        extractor,       # ConstraintExtractor
        merger,          # ConstraintMerger
        classifier,      # ConstraintClassifier
        expander,        # ConstraintExpander
        settings,        # Settings object (duck-typed)
    ) -> None:
        self._chunk_dao = chunk_dao
        self._meili = meili
        self._graph = graph
        self._embedder = embedder
        self._reranker = reranker
        self._extractor = extractor
        self._merger = merger
        self._classifier = classifier
        self._expander = expander
        self._settings = settings

    # ── helpers ────────────────────────────────────────────────────────────────

    def _build_chip_filter(self, chips: list[str] | None) -> str | None:
        """Build a Meilisearch filter expression for chip list."""
        if not chips:
            return None
        chip_clauses = " OR ".join(
            f"applicable_chips = {c!r}" for c in chips
        )
        return chip_clauses

    def _build_chip_ros_filter(
        self, chips: list[str] | None, ros_version: str | None
    ) -> str | None:
        """Build a combined chip + ROS filter expression."""
        parts = []
        if chips:
            chip_clauses = " OR ".join(
                f"applicable_chips = {c!r}" for c in chips
            )
            parts.append(f"({chip_clauses})")
        if ros_version:
            parts.append(f"ros_versions = {ros_version!r}")
        return " AND ".join(parts) if parts else None

    async def _four_channel_recall(
        self,
        query: str,
        embedding: list[float],
        hard: Constraint,
        top_k: int,
        include_superseded: bool,
    ) -> list[list[dict]]:
        """Run four recall channels in parallel; failed channels return []."""

        async def dense_recall() -> list[dict]:
            return await self._chunk_dao.vector_search(
                query_embedding=embedding,
                hard_chips=hard.chip,
                ros_versions=[hard.ros_version] if hard.ros_version else None,
                top_k=top_k,
                include_superseded=include_superseded,
            )

        async def bm25_recall() -> list[dict]:
            filter_expr = self._build_chip_filter(hard.chip)
            results = await self._meili.search(query, filter_expr=filter_expr, limit=top_k)
            # Normalize: ensure chunk_id field exists (meili uses 'id')
            for r in results:
                if "chunk_id" not in r and "id" in r:
                    r["chunk_id"] = r["id"]
            return results

        async def metadata_recall() -> list[dict]:
            filter_expr = self._build_chip_ros_filter(hard.chip, hard.ros_version)
            results = await self._meili.search("", filter_expr=filter_expr, limit=top_k)
            for r in results:
                if "chunk_id" not in r and "id" in r:
                    r["chunk_id"] = r["id"]
            return results

        async def graph_recall() -> list[dict]:
            if not hard.chip:
                return []
            fault_results = []
            for chip_id in hard.chip:
                try:
                    faults = await self._graph.faults_for_chip(chip_id)
                    for fault in faults:
                        for doc_id in fault.get("related_doc_ids", []):
                            fault_results.append({
                                "chunk_id": doc_id,
                                "document_id": doc_id,
                                "content": fault.get("description", ""),
                                "applicable_chips": [chip_id],
                                "source_tier": None,
                            })
                except Exception as exc:
                    logger.warning("graph_recall failed for chip %s: %s", chip_id, exc)
            return fault_results

        raw = await asyncio.gather(
            dense_recall(),
            bm25_recall(),
            metadata_recall(),
            graph_recall(),
            return_exceptions=True,
        )

        channels: list[list[dict]] = []
        channel_names = ["dense", "bm25", "metadata", "graph"]
        for name, result in zip(channel_names, raw):
            if isinstance(result, Exception):
                logger.warning("Recall channel %s failed: %s", name, result)
                channels.append([])
            else:
                channels.append(result)
        return channels

    async def _execute_search(
        self,
        query: str,
        hard: Constraint,
        soft: Constraint,
        request: SearchRequest,
    ) -> list[dict]:
        """Run full pipeline: recall → RRF → rerank → score. Returns scored hits."""
        recall = self._settings.retrieval_recall
        include_sup = request.include_superseded

        # Embed query
        embeddings = await self._embedder.embed([query])
        embedding = embeddings[0]

        # Four-channel recall
        channels = await self._four_channel_recall(
            query, embedding, hard, recall, include_sup
        )

        # RRF fusion
        fused = rrf_fuse(channels, k=self._settings.rrf_k)
        if not fused:
            return []

        # Prepare passages for reranking
        passages = [item.get("content", "") for item in fused]

        # Rerank
        rerank_results = await self._reranker.rerank(
            query, passages, top_n=self._settings.rerank_top_n
        )

        # Build final hit list
        hits: list[dict] = []
        for rr in rerank_results:
            idx = rr["index"]
            if idx >= len(fused):
                continue
            item = fused[idx]

            # Determine matched constraints
            matched_constraints: list[str] = []
            if hard.chip and item.get("applicable_chips"):
                item_chips = set(item["applicable_chips"])
                if item_chips.intersection(hard.chip):
                    matched_constraints.append("chip")
            if hard.ros_version and item.get("ros_versions"):
                if hard.ros_version in item.get("ros_versions", []):
                    matched_constraints.append("ros_version")
            if hard.kernel_range:
                matched_constraints.append("kernel_range")

            is_superseded = item.get("status") == "superseded"
            final_score = compute_final_score(
                rerank_score=rr["score"],
                source_tier=item.get("source_tier"),
                created_at=item.get("created_at"),
                matched_constraint_count=len(matched_constraints),
                is_superseded=is_superseded,
                source_tier_min=str(soft.source_tier_min.value) if soft.source_tier_min else None,
            )

            hits.append({
                "chunk_id": item.get("chunk_id", ""),
                "content": item.get("content", ""),
                "score": final_score,
                "document_id": item.get("document_id", ""),
                "applicable_chips": item.get("applicable_chips", []),
                "source_tier": item.get("source_tier"),
                "matched_constraints": matched_constraints,
            })

        # Sort by final score
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits

    # ── public API ─────────────────────────────────────────────────────────────

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Full retrieval pipeline with multi-level degradation."""
        query = request.query

        # Step 1: Extract implicit constraints from query text
        implicit = self._extractor.extract(query)

        # Step 2: Merge constraints (explicit > session > implicit)
        merged, conflict_reports = self._merger.merge(
            explicit=request.constraints,
            session=None,
            implicit=implicit,
        )

        # Step 3: Classify hard/soft constraints
        classified = self._classifier.classify(merged)
        hard = classified.hard
        soft = classified.soft

        # Step 4: Try degradation level 0 (full constraints)
        hits = await self._execute_search(query, hard, soft, request)

        if len(hits) >= request.top_k:
            return SearchResponse(
                query=query,
                hits=hits[: request.top_k],
                degraded=False,
                conflict_report=[cr.model_dump() for cr in conflict_reports] or None,
            )

        if not request.allow_degradation:
            return SearchResponse(
                query=query,
                hits=hits[: request.top_k],
                degraded=False,
                conflict_report=[cr.model_dump() for cr in conflict_reports] or None,
            )

        # Step 5: Degradation level 1 — relax board constraint
        hard_l1 = Constraint(
            chip=hard.chip,
            ros_version=hard.ros_version,
            kernel_range=hard.kernel_range,
        )
        soft_l1 = Constraint(
            source_tier_min=soft.source_tier_min,
            language=soft.language,
        )
        hits = await self._execute_search(query, hard_l1, soft_l1, request)
        if len(hits) >= request.top_k:
            return SearchResponse(
                query=query,
                hits=hits[: request.top_k],
                degraded=True,
                degradation_note="Board constraint relaxed",
                conflict_report=[cr.model_dump() for cr in conflict_reports] or None,
            )

        # Degradation level 2 — expand chip family tree
        expanded = await self._expander.expand(merged)
        classified_exp = self._classifier.classify(expanded)
        hits = await self._execute_search(query, classified_exp.hard, classified_exp.soft, request)
        if len(hits) >= request.top_k:
            return SearchResponse(
                query=query,
                hits=hits[: request.top_k],
                degraded=True,
                degradation_note="Chip family expanded via graph",
                conflict_report=[cr.model_dump() for cr in conflict_reports] or None,
            )

        # Degradation level 3 — full fallback (no hard constraints)
        hits = await self._execute_search(query, Constraint(), Constraint(), request)
        return SearchResponse(
            query=query,
            hits=hits[: request.top_k],
            degraded=True,
            degradation_note="Full fallback: all hard constraints removed",
            conflict_report=[cr.model_dump() for cr in conflict_reports] or None,
        )
