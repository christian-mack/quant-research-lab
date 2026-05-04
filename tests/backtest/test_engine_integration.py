"""End-to-end engine: market next-bar fills and realized P&amp;L."""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from quant_research.backtest import (
    BacktestConfig,
    BacktestEngine,
    BarContext,
    OrderRequest,
    OrderSide,
    OrderType,
)

_DT = datetime(2020, 1, 2, tzinfo=UTC)


class _BuyBar0SellBar1:
    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        if ctx.bar_index == 0:
            return [OrderRequest(OrderSide.BUY, 1, OrderType.MARKET)]
        if ctx.bar_index == 1:
            return [OrderRequest(OrderSide.SELL, 1, OrderType.MARKET)]
        return []


def test_two_market_round_trip_next_bar_opens() -> None:
    """Buy after bar 0 fills at bar 1 open; sell after bar 1 fills at bar 2 open."""
    bars = pl.DataFrame(
        {
            "timestamp": [_DT, _DT, _DT],
            "open": [100.0, 100.5, 101.0],
            "high": [100.25, 100.75, 101.25],
            "low": [99.75, 100.25, 100.75],
            "close": [100.0, 100.5, 101.0],
            "volume": [1.0, 1.0, 1.0],
        }
    )
    engine = BacktestEngine(BacktestConfig())
    out = engine.run(bars, _BuyBar0SellBar1())
    assert len(out.fills) == 2
    assert out.fills[0].price == 100.5
    assert out.fills[1].price == 101.0
    assert out.account.position_qty == 0
    assert out.account.realized_pnl == pytest.approx(1.0)


class _BuyStopAfterBar0:
    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        if ctx.bar_index == 0:
            return [
                OrderRequest(OrderSide.BUY, 1, OrderType.STOP, stop_price=100.25),
            ]
        return []


def test_stop_buy_triggers_segment_after_open() -> None:
    bars = pl.DataFrame(
        {
            "timestamp": [_DT, _DT],
            "open": [100.0, 100.0],
            "high": [100.0, 100.5],
            "low": [100.0, 99.75],
            "close": [100.0, 100.25],
            "volume": [1.0, 1.0],
        }
    )
    engine = BacktestEngine(BacktestConfig())
    out = engine.run(bars, _BuyStopAfterBar0())
    assert len(out.fills) == 1
    assert out.fills[0].base_price == 100.25
    assert out.account.position_qty == 1
