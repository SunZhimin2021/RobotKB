from __future__ import annotations

import re
from pathlib import Path

import ahocorasick
import yaml

from common.schemas import Constraint


class ConstraintExtractor:
    """Extract constraints from natural language text using Aho-Corasick + regex.

    No LLM calls are made. The automaton is built once at __init__ time.
    """

    # ROS distro name, optionally preceded by "2" or "1"
    _ROS_RE = re.compile(
        r"ROS\s*(?:2\s*)?(Humble|Foxy|Galactic|Iron|Jazzy|Noetic)",
        re.IGNORECASE,
    )
    # kernel version string
    _KERNEL_RE = re.compile(r"kernel\s+(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)

    def __init__(
        self,
        chips_path: str = "data/chips.yaml",
        boards_path: str = "data/boards.yaml",
    ) -> None:
        chips_data = yaml.safe_load(Path(chips_path).read_text(encoding="utf-8"))
        boards_data = yaml.safe_load(Path(boards_path).read_text(encoding="utf-8"))

        self._chips: dict[str, str] = {}   # alias -> chip_id
        self._boards: dict[str, str] = {}  # alias -> board_id

        for chip in chips_data["chips"]:
            for name in chip["names"]:
                self._chips[name] = chip["id"]

        for board in boards_data["boards"]:
            for name in board["names"]:
                self._boards[name] = board["id"]

        # Build a single automaton for all aliases (chips + boards).
        # Each value is (kind, alias, id) where kind is "chip" or "board".
        self._automaton = ahocorasick.Automaton()
        for alias, chip_id in self._chips.items():
            self._automaton.add_word(alias, ("chip", alias, chip_id))
        for alias, board_id in self._boards.items():
            self._automaton.add_word(alias, ("board", alias, board_id))
        self._automaton.make_automaton()

    def extract(self, text: str) -> Constraint:
        """Extract constraints from *text*.

        Longest-match wins when aliases overlap (e.g. "RK3588S" beats "RK3588").
        """
        # --- chip / board via Aho-Corasick ---
        # Collect all hits: (end_index, alias_len, kind, chip/board_id)
        hits: list[tuple[int, int, str, str]] = []
        for end_idx, (kind, alias, entity_id) in self._automaton.iter(text):
            hits.append((end_idx, len(alias), kind, entity_id))

        # Resolve overlaps: keep only hits whose span is not covered by a longer hit.
        # Sort by end index desc, then length desc so longer matches are preferred.
        hits.sort(key=lambda h: (h[0], h[1]), reverse=True)
        covered: set[tuple[int, int]] = set()  # (start, end) of accepted hits
        accepted: list[tuple[str, str]] = []   # (kind, id)

        for end_idx, alias_len, kind, entity_id in hits:
            start_idx = end_idx - alias_len + 1
            # Check if this span overlaps with any already-accepted longer hit
            overlaps = any(
                not (end_idx < cs or start_idx > ce)
                for cs, ce in covered
            )
            if not overlaps:
                covered.add((start_idx, end_idx))
                accepted.append((kind, entity_id))

        chips_found: list[str] = []
        board_found: str | None = None
        seen_chips: set[str] = set()

        for kind, entity_id in accepted:
            if kind == "chip" and entity_id not in seen_chips:
                chips_found.append(entity_id)
                seen_chips.add(entity_id)
            elif kind == "board" and board_found is None:
                board_found = entity_id

        # --- ROS version ---
        ros_version: str | None = None
        ros_match = self._ROS_RE.search(text)
        if ros_match:
            # Preserve the canonical capitalisation from the regex group
            ros_version = ros_match.group(1).capitalize()

        # --- kernel version ---
        kernel_range: str | None = None
        kernel_match = self._KERNEL_RE.search(text)
        if kernel_match:
            kernel_range = f">={kernel_match.group(1)}"

        return Constraint(
            chip=chips_found if chips_found else None,
            board=board_found,
            ros_version=ros_version,
            kernel_range=kernel_range,
        )
