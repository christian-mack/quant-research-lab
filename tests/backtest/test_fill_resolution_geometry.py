"""Tests for bracket geometry validation in fill resolution."""

from __future__ import annotations

import pytest

from quant_research.backtest.fill_resolution import validate_bracket_geometry_in_orders
from quant_research.backtest.geometry import GeometryError
from quant_research.backtest.specs import BacktestConfig
from quant_research.backtest.types import OrderRequest, OrderSide, OrderType


def test_bracket_geometry_rejects_incoherent_long() -> None:
    cfg = BacktestConfig(enforce_trade_geometry=True)
    orders = [
        OrderRequest(
            OrderSide.BUY,
            1,
            OrderType.LIMIT,
            limit_price=100.0,
            module_id="ote",
            tag="ote_entry",
            bracket_entry=100.0,
            bracket_stop=100.5,
            bracket_target=103.0,
            bracket_direction="long",
        ),
    ]
    with pytest.raises(GeometryError):
        validate_bracket_geometry_in_orders(orders, config=cfg)


def test_bracket_geometry_accepts_coherent() -> None:
    cfg = BacktestConfig(enforce_trade_geometry=True)
    orders = [
        OrderRequest(
            OrderSide.BUY,
            1,
            OrderType.LIMIT,
            limit_price=100.0,
            module_id="ote",
            tag="ote_entry",
            bracket_entry=100.0,
            bracket_stop=99.0,
            bracket_target=103.0,
            bracket_direction="long",
        ),
    ]
    validate_bracket_geometry_in_orders(orders, config=cfg)
