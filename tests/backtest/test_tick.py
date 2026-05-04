"""Tests for tick snapping and slippage."""

from __future__ import annotations

import pytest

from quant_research.backtest.specs import (
    InstrumentSpec,
    SlippageMode,
    SlippageSide,
    SlippageSpec,
)
from quant_research.backtest.tick import apply_slippage, snap_to_tick
from quant_research.backtest.types import OrderSide


def test_snap_to_tick_nearest() -> None:
    ins = InstrumentSpec(tick_size=0.25)
    assert snap_to_tick(100.12, ins) == 100.0
    assert snap_to_tick(100.13, ins) == 100.25


def test_snap_to_tick_invalid_tick() -> None:
    with pytest.raises(ValueError, match="tick_size"):
        snap_to_tick(1.0, InstrumentSpec(tick_size=0.0))


def test_apply_slippage_adverse_buy() -> None:
    ins = InstrumentSpec(tick_size=0.25)
    spec = SlippageSpec(mode=SlippageMode.FIXED_TICKS, ticks=2.0, side=SlippageSide.ADVERSE_ONLY)
    # 100.0 + 0.5 = 100.5 -> on grid
    assert apply_slippage(100.0, OrderSide.BUY, spec, ins) == 100.5


def test_apply_slippage_adverse_sell() -> None:
    ins = InstrumentSpec(tick_size=0.25)
    spec = SlippageSpec(mode=SlippageMode.FIXED_TICKS, ticks=2.0, side=SlippageSide.ADVERSE_ONLY)
    assert apply_slippage(100.0, OrderSide.SELL, spec, ins) == 99.5


def test_apply_slippage_fixed_points_rounds() -> None:
    ins = InstrumentSpec(tick_size=0.25)
    spec = SlippageSpec(mode=SlippageMode.FIXED_POINTS, points=0.4, side=SlippageSide.ADVERSE_ONLY)
    assert apply_slippage(100.0, OrderSide.BUY, spec, ins) == 100.5
