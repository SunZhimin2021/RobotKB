"""Tests for etl_worker.ner module (NERVerifier)."""
from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from constraint_engine.extractor import ConstraintExtractor
from etl_worker.ner import NERVerifier

# Paths to data files
_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
CHIPS_PATH = os.path.join(_ROOT, "data", "chips.yaml")
BOARDS_PATH = os.path.join(_ROOT, "data", "boards.yaml")


@pytest.fixture(scope="module")
def extractor():
    return ConstraintExtractor(chips_path=CHIPS_PATH, boards_path=BOARDS_PATH)


@pytest.fixture(scope="module")
def verifier(extractor):
    return NERVerifier(extractor)


# ── consistent NER ─────────────────────────────────────────────────────────────

def test_consistent_ner(verifier):
    """Document mentions RK3588 and declaration includes rk3588 → consistent."""
    text = "This driver is designed for RK3588 SoC."
    result = verifier.verify(text, declared_chips=["rk3588"], declared_boards=[])

    assert result["consistent"] is True
    assert "rk3588" in result["extracted_chips"]
    assert result["missing_in_declaration"] == []
    assert result["false_positives"] == []


def test_consistent_ner_with_board(verifier):
    """Document mentions Rock 5B board → consistent when declared."""
    text = "Configuration guide for Rock 5B development board."
    result = verifier.verify(
        text, declared_chips=[], declared_boards=["rock5b"]
    )
    assert result["consistent"] is True
    assert "rock5b" in result["extracted_boards"]


def test_consistent_ner_no_entities(verifier):
    """Text with no chip/board mentions and empty declarations → consistent."""
    text = "This is a general ROS tutorial without hardware specifics."
    result = verifier.verify(text, declared_chips=[], declared_boards=[])
    assert result["consistent"] is True
    assert result["missing_in_declaration"] == []
    assert result["false_positives"] == []


# ── missing chip detected ──────────────────────────────────────────────────────

def test_missing_chip_detected(verifier):
    """Document mentions RK3588S but declaration only has rk3588 → inconsistent."""
    text = "This document covers RK3588S specific features."
    result = verifier.verify(text, declared_chips=["rk3588"], declared_boards=[])

    assert result["consistent"] is False
    # rk3588s should be in extracted but not in declaration
    assert "rk3588s" in result["extracted_chips"]
    assert "rk3588s" in result["missing_in_declaration"]


def test_missing_chip_no_declaration(verifier):
    """Document mentions a chip but declaration is empty → chip missing."""
    text = "RK3568 based system configuration."
    result = verifier.verify(text, declared_chips=[], declared_boards=[])

    assert result["consistent"] is False
    assert "rk3568" in result["missing_in_declaration"]


# ── false positives detected ───────────────────────────────────────────────────

def test_false_positive_detected(verifier):
    """Declaration includes 'jetson_agx_orin' but text doesn't mention Jetson → false positive."""
    text = "This guide is for RK3588 based robots."
    result = verifier.verify(
        text,
        declared_chips=["rk3588", "jetson_agx_orin"],
        declared_boards=[],
    )

    assert result["consistent"] is False
    assert "jetson_agx_orin" in result["false_positives"]


def test_false_positive_board(verifier):
    """Declaration includes a board that doesn't appear in the document."""
    text = "General Linux kernel configuration tips."
    result = verifier.verify(
        text,
        declared_chips=[],
        declared_boards=["rock5b"],
    )

    assert result["consistent"] is False
    assert "rock5b" in result["false_positives"]


# ── result structure ───────────────────────────────────────────────────────────

def test_verify_returns_all_keys(verifier):
    """verify() must always return all expected keys."""
    result = verifier.verify("some text", [], [])
    expected_keys = {
        "consistent",
        "extracted_chips",
        "extracted_boards",
        "missing_in_declaration",
        "false_positives",
    }
    assert set(result.keys()) == expected_keys


def test_verify_with_mock_extractor():
    """Unit test using a mock extractor to isolate NERVerifier logic."""
    mock_extractor = MagicMock()
    mock_constraint = MagicMock()
    mock_constraint.chip = ["rk3588", "rk3568"]
    mock_constraint.board = "rock5b"
    mock_extractor.extract.return_value = mock_constraint

    verifier = NERVerifier(mock_extractor)
    result = verifier.verify(
        "some text",
        declared_chips=["rk3588"],
        declared_boards=[],
    )

    assert result["consistent"] is False
    # rk3568 and rock5b are in doc but not declared
    assert "rk3568" in result["missing_in_declaration"]
    assert "rock5b" in result["missing_in_declaration"]
    # rk3588 is declared and found → not a false positive
    assert "rk3588" not in result["false_positives"]
