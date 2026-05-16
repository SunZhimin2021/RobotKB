from __future__ import annotations

from pydantic import BaseModel

from common.schemas import Constraint


class ConflictReport(BaseModel):
    field: str
    explicit_value: str
    implicit_value: str
    resolution: str  # "kept_explicit" | "kept_implicit"


class ConstraintMerger:
    """Merge constraints from multiple sources.

    Priority order (highest to lowest): explicit > session > implicit.
    Conflicts are reported only when both explicit and implicit provide
    different non-None values for the same field.
    """

    _FIELDS = ["chip", "board", "ros_version", "kernel_range", "source_tier_min", "language"]

    def merge(
        self,
        explicit: Constraint | None,
        session: Constraint | None,
        implicit: Constraint | None,
    ) -> tuple[Constraint, list[ConflictReport]]:
        explicit = explicit or Constraint()
        session = session or Constraint()
        implicit = implicit or Constraint()

        result: dict = {}
        conflicts: list[ConflictReport] = []

        for field in self._FIELDS:
            exp_val = getattr(explicit, field)
            ses_val = getattr(session, field)
            imp_val = getattr(implicit, field)

            if exp_val is not None:
                result[field] = exp_val
                # Conflict: explicit and implicit both set, but differ
                if imp_val is not None and imp_val != exp_val:
                    conflicts.append(
                        ConflictReport(
                            field=field,
                            explicit_value=str(exp_val),
                            implicit_value=str(imp_val),
                            resolution="kept_explicit",
                        )
                    )
            elif ses_val is not None:
                result[field] = ses_val
            elif imp_val is not None:
                result[field] = imp_val
            else:
                result[field] = None

        return Constraint(**result), conflicts
