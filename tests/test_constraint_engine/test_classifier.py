import pytest
from common.schemas import Constraint, SourceTier
from constraint_engine.classifier import ConstraintClassifier, HardSoftConstraints


@pytest.fixture
def classifier():
    return ConstraintClassifier()


def test_chip_is_hard(classifier):
    c = Constraint(chip=["rk3588"])
    result = classifier.classify(c)
    assert isinstance(result, HardSoftConstraints)
    assert result.hard.chip == ["rk3588"]
    assert result.soft.chip is None


def test_board_is_soft(classifier):
    c = Constraint(board="rock5b")
    result = classifier.classify(c)
    assert result.soft.board == "rock5b"
    assert result.hard.board is None


def test_ros_version_is_hard(classifier):
    c = Constraint(ros_version="Humble")
    result = classifier.classify(c)
    assert result.hard.ros_version == "Humble"
    assert result.soft.ros_version is None


def test_kernel_range_is_hard(classifier):
    c = Constraint(kernel_range=">=5.10,<6.0")
    result = classifier.classify(c)
    assert result.hard.kernel_range == ">=5.10,<6.0"
    assert result.soft.kernel_range is None


def test_source_tier_is_soft(classifier):
    c = Constraint(source_tier_min=SourceTier.OFFICIAL)
    result = classifier.classify(c)
    assert result.soft.source_tier_min == SourceTier.OFFICIAL
    assert result.hard.source_tier_min is None


def test_language_is_soft(classifier):
    c = Constraint(language="zh")
    result = classifier.classify(c)
    assert result.soft.language == "zh"
    assert result.hard.language is None


def test_mixed_constraint(classifier):
    c = Constraint(
        chip=["rk3588"],
        board="rock5b",
        ros_version="Humble",
        source_tier_min=SourceTier.VENDOR,
    )
    result = classifier.classify(c)
    assert result.hard.chip == ["rk3588"]
    assert result.hard.ros_version == "Humble"
    assert result.soft.board == "rock5b"
    assert result.soft.source_tier_min == SourceTier.VENDOR
