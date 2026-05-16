import pytest
from constraint_engine.version_matcher import VersionMatcher


def test_version_in_range_true():
    assert VersionMatcher.version_in_range("5.10.5", ">=5.10,<6.0") is True


def test_version_in_range_false():
    assert VersionMatcher.version_in_range("6.0.0", ">=5.10,<6.0") is False


def test_none_range_always_true():
    assert VersionMatcher.version_in_range("5.10.5", None) is True


def test_empty_range_always_true():
    assert VersionMatcher.version_in_range("5.10.5", "") is True


def test_ros_compatible_exact():
    assert VersionMatcher.is_compatible("Humble", "Humble") is True


def test_ros_compatible_mismatch():
    assert VersionMatcher.is_compatible("Foxy", "Humble") is False


def test_ros_compatible_none_constraint():
    assert VersionMatcher.is_compatible("Humble", None) is True


def test_ros_compatible_none_doc():
    assert VersionMatcher.is_compatible(None, "Humble") is True


def test_ros_compatible_both_none():
    assert VersionMatcher.is_compatible(None, None) is True
