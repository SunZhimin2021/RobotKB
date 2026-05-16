from __future__ import annotations

import re

from constraint_engine.extractor import ConstraintExtractor


class NERVerifier:
    """Extract chip/board entities from document text and compare with user labels.

    Inconsistencies are surfaced as a structured diff report.
    """

    def __init__(self, extractor: ConstraintExtractor) -> None:
        self._extractor = extractor

    def verify(
        self,
        text: str,
        declared_chips: list[str],
        declared_boards: list[str],
    ) -> dict:
        """Extract chip/board entities and compare with declared labels.

        Returns:
            {
                "consistent": bool,
                "extracted_chips": list[str],
                "extracted_boards": list[str],
                "missing_in_declaration": list[str],  # in doc but not declared
                "false_positives": list[str],          # declared but not in doc
            }
        """
        constraint = self._extractor.extract(text)

        extracted_chips: list[str] = constraint.chip or []
        extracted_boards: list[str] = [constraint.board] if constraint.board else []

        # Normalise to lower-case for comparison
        declared_all = set(c.lower() for c in declared_chips) | set(
            b.lower() for b in declared_boards
        )
        extracted_all = set(c.lower() for c in extracted_chips) | set(
            b.lower() for b in extracted_boards
        )

        missing_in_declaration = sorted(extracted_all - declared_all)
        false_positives = sorted(declared_all - extracted_all)

        consistent = not missing_in_declaration and not false_positives

        return {
            "consistent": consistent,
            "extracted_chips": extracted_chips,
            "extracted_boards": extracted_boards,
            "missing_in_declaration": missing_in_declaration,
            "false_positives": false_positives,
        }
