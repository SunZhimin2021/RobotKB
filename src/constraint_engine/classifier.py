from __future__ import annotations

from pydantic import BaseModel

from common.schemas import Constraint


class HardSoftConstraints(BaseModel):
    hard: Constraint  # must satisfy -- used for filtering
    soft: Constraint  # influences ranking, does not filter


class ConstraintClassifier:
    """Classify constraint fields into hard (filter) and soft (rank) buckets.

    Rules
    -----
    Hard (filtering):
        chip         -- chip incompatibility is a fundamental mismatch
        ros_version  -- ROS ABI incompatibility is non-trivial
        kernel_range -- kernel version incompatibility is non-trivial

    Soft (ranking only):
        board            -- board differences can degrade gracefully
        source_tier_min  -- affects trust/ranking, not correctness
        language         -- affects readability, not correctness
    """

    _HARD_FIELDS = {"chip", "ros_version", "kernel_range"}
    _SOFT_FIELDS = {"board", "source_tier_min", "language"}

    def classify(self, constraint: Constraint) -> HardSoftConstraints:
        hard_kwargs: dict = {}
        soft_kwargs: dict = {}

        for field in self._HARD_FIELDS:
            value = getattr(constraint, field)
            hard_kwargs[field] = value
            soft_kwargs[field] = None

        for field in self._SOFT_FIELDS:
            value = getattr(constraint, field)
            soft_kwargs[field] = value
            hard_kwargs[field] = None

        return HardSoftConstraints(
            hard=Constraint(**hard_kwargs),
            soft=Constraint(**soft_kwargs),
        )
