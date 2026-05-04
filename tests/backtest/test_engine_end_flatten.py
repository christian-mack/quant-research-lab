"""End-of-series: flatten + discard working orders warnings."""

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
    as_module,
)

_DT = datetime(2020, 1, 2, tzinfo=UTC)


class _BuyOnly:
    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        if ctx.bar_index == 0:
            return [OrderRequest(OrderSide.BUY, 1, OrderType.MARKET, module_id="x")]
        return []


def test_auto_flatten_open_position_warns() -> None:
    bars = pl.DataFrame(
        {
            "timestamp": [_DT, _DT],
            "open": [100.0, 100.5],
            "high": [100.25, 100.75],
            "low": [99.75, 100.25],
            "close": [100.0, 100.5],
            "volume": [1.0, 1.0],
        }
    )
    engine = BacktestEngine(BacktestConfig())
    with pytest.warns(UserWarning, match="[Ff]latten|[Dd]iscarding"):
        out = engine.run(bars, [as_module("x", _BuyOnly())])
    assert out.account.position_qty == 0
    assert out.trade_log.height == 1
    row = out.trade_log.row(0, named=True)
    assert row["exit_reason"] == "flatten"


class _WorkingLeft:
    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        if ctx.bar_index == 0:
            return [
                OrderRequest(
                    OrderSide.BUY,
                    1,
                    OrderType.STOP,
                    stop_price=9999.0,
                    module_id="x",
                ),
            ]
        return []


def test_discard_working_at_end_warns() -> None:
    bars = pl.DataFrame(
        {
            "timestamp": [_DT, _DT],
            "open": [100.0, 100.5],
            "high": [100.25, 100.75],
            "low": [99.75, 100.25],
            "close": [100.0, 100.5],
            "volume": [1.0, 1.0],
        }
    )
    engine = BacktestEngine(BacktestConfig())
    with pytest.warns(UserWarning, match="[Dd]iscarding"):
        out = engine.run(bars, [as_module("x", _WorkingLeft())])
    assert out.account.position_qty == 0
    assert out.trade_log.height == 0
