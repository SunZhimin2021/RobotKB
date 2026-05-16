import pytest
from common.schemas import Constraint, SourceTier
from constraint_engine.merger import ConstraintMerger, ConflictReport


@pytest.fixture
def merger():
    return ConstraintMerger()


def test_no_conflict_merge(merger):
    explicit = Constraint(chip=["rk3588"])
    session = Constraint(ros_version="Humble")
    implicit = Constraint(board="rock5b")
    merged, conflicts = merger.merge(explicit, session, implicit)
    assert merged.chip == ["rk3588"]
    assert merged.ros_version == "Humble"
    assert merged.board == "rock5b"
    assert conflicts == []


def test_explicit_overrides_implicit(merger):
    explicit = Constraint(chip=["rk3588"])
    implicit = Constraint(chip=["jetson_agx_orin"])
    merged, conflicts = merger.merge(explicit, None, implicit)
    assert merged.chip == ["rk3588"]
    assert len(conflicts) == 1
    assert conflicts[0].field == "chip"
    assert conflicts[0].resolution == "kept_explicit"


def test_missing_field_no_conflict(merger):
    explicit = Constraint(chip=["rk3588"])
    implicit = Constraint()  # no chip
    merged, conflicts = merger.merge(explicit, None, implicit)
    assert merged.chip == ["rk3588"]
    assert conflicts == []


def test_session_fills_missing(merger):
    explicit = Constraint()  # no ros_version
    session = Constraint(ros_version="Foxy")
    merged, conflicts = merger.merge(explicit, session, None)
    assert merged.ros_version == "Foxy"
    assert conflicts == []
