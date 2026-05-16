import pytest
from unittest.mock import AsyncMock
from common.schemas import Constraint
from constraint_engine.expander import ConstraintExpander


@pytest.fixture
def mock_graph():
    graph = AsyncMock()
    graph.chip_family_chain = AsyncMock(return_value=["rk3588s", "rk3588"])
    graph.boards_for_chip = AsyncMock(return_value=["rk3588"])
    return graph


@pytest.mark.asyncio
async def test_expand_chip_family(mock_graph):
    expander = ConstraintExpander(mock_graph)
    c = Constraint(chip=["rk3588s"])
    expanded = await expander.expand(c)
    # Should have called chip_family_chain for rk3588s
    mock_graph.chip_family_chain.assert_called_once_with("rk3588s")
    assert "rk3588s" in expanded.chip
    assert "rk3588" in expanded.chip


@pytest.mark.asyncio
async def test_expand_board_infer_chip(mock_graph):
    expander = ConstraintExpander(mock_graph)
    c = Constraint(board="rock5b")
    expanded = await expander.expand(c)
    mock_graph.boards_for_chip.assert_called_once_with("rock5b")
    assert expanded.chip is not None
    assert "rk3588" in expanded.chip


@pytest.mark.asyncio
async def test_expand_no_graph_call_if_empty(mock_graph):
    expander = ConstraintExpander(mock_graph)
    c = Constraint()
    expanded = await expander.expand(c)
    mock_graph.chip_family_chain.assert_not_called()
    mock_graph.boards_for_chip.assert_not_called()
    assert expanded.chip is None
    assert expanded.board is None
