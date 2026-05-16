from __future__ import annotations

from common.schemas import Constraint


class ConstraintExpander:
    """Expand constraints via a graph service (duck-typed to avoid circular imports).

    GraphService protocol:
        async def chip_family_chain(self, chip_id: str) -> list[str]: ...
        async def boards_for_chip(self, chip_id: str) -> list[str]: ...
    """

    def __init__(self, graph_service) -> None:  # duck-typed GraphService
        self._graph = graph_service

    async def expand(self, constraint: Constraint) -> Constraint:
        """Return a new Constraint with chip/board fields expanded via the graph.

        If constraint.chip is set: each chip_id is expanded to the full
        family chain, and all resulting ids are merged (deduplicated, order
        preserved -- original ids first).

        If constraint.board is set but chip is None: boards_for_chip is called
        with the board id to derive the associated chip list.

        The original Constraint is not mutated.
        """
        chip = list(constraint.chip) if constraint.chip else None
        board = constraint.board

        if chip:
            expanded_chips: list[str] = []
            seen: set[str] = set()
            for chip_id in chip:
                family = await self._graph.chip_family_chain(chip_id)
                for cid in family:
                    if cid not in seen:
                        expanded_chips.append(cid)
                        seen.add(cid)
            chip = expanded_chips if expanded_chips else chip

        elif board is not None:
            inferred = await self._graph.boards_for_chip(board)
            if inferred:
                chip = inferred

        return Constraint(
            chip=chip,
            board=board,
            ros_version=constraint.ros_version,
            kernel_range=constraint.kernel_range,
            source_tier_min=constraint.source_tier_min,
            language=constraint.language,
        )
