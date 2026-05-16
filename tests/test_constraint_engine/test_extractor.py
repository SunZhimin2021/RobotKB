import os
import pytest
from constraint_engine.extractor import ConstraintExtractor

CHIPS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "chips.yaml")
BOARDS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "boards.yaml")


@pytest.fixture
def extractor():
    return ConstraintExtractor(chips_path=CHIPS_PATH, boards_path=BOARDS_PATH)


def test_extract_chinese_chip(extractor):
    c = extractor.extract("适用于 RK3588S 的驱动")
    assert c.chip == ["rk3588s"]


def test_extract_english_chip(extractor):
    c = extractor.extract("RK3588 datasheet")
    assert c.chip == ["rk3588"]


def test_rk3588s_not_rk3588(extractor):
    c = extractor.extract("RK3588S")
    assert c.chip is not None
    assert "rk3588s" in c.chip
    # rk3588 should NOT appear as a spurious hit from the S variant
    assert "rk3588" not in c.chip


def test_extract_multi_chip(extractor):
    c = extractor.extract("RK3588 和 Jetson AGX Orin 的对比")
    assert c.chip is not None
    assert "rk3588" in c.chip
    assert "jetson_agx_orin" in c.chip


def test_extract_board(extractor):
    c = extractor.extract("Rock 5B 配置指南")
    assert c.board == "rock5b"


def test_extract_ros_version(extractor):
    c = extractor.extract("ROS2 Humble 安装教程")
    assert c.ros_version == "Humble"


def test_extract_no_match(extractor):
    c = extractor.extract("如何学习机器人开发")
    assert c.chip is None
    assert c.board is None


def test_extract_kernel(extractor):
    c = extractor.extract("需要 kernel 5.10.5 或以上版本")
    assert c.kernel_range is not None
    assert "5.10.5" in c.kernel_range
