"""Engine ``IntradaySessionHygieneSpec``: 16:59 ET flatten and [17:00, 18:00) deadzone."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from quant_research.backtest import (
    BacktestConfig,
    BacktestEngine,
    BarContext,
    OrderRequest,
    OrderSide,
    OrderType,
    as_module,
)
from quant_research.backtest.specs import (
    IntradaySessionHygieneSpec,
    SessionSpec,
)

_ET = ZoneInfo("America/New_York")


def _et(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=_ET)


class _BuyBar0Hold:
    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        if ctx.bar_index == 0:
            return [
                OrderRequest(
                    OrderSide.BUY,
                    1,
                    OrderType.MARKET,
                    module_id="m",
                ),
            ]
        return []


def test_flatten_at_1659_et_uses_that_bar_close() -> None:
    """Long from morning must exit at 16:59 bar close, not next session open."""
    bars = pl.DataFrame(
        {
            "timestamp": [
                _et(2020, 6, 2, 10, 0),
                _et(2020, 6, 2, 10, 1),
                _et(2020, 6, 2, 16, 59),
            ],
            "open": [100.0, 100.0, 100.0],
            "high": [100.0, 101.0, 105.0],
            "low": [100.0, 99.5, 99.0],
            "close": [100.0, 100.0, 103.0],
            "volume": [1.0, 1.0, 1.0],
        }
    )
    engine = BacktestEngine(BacktestConfig())
    out = engine.run(bars, [as_module("m", _BuyBar0Hold())])
    assert len(out.fills) == 2
    assert out.fills[0].base_price == 100.0
    assert out.fills[1].base_price == 103.0
    assert out.fills[1].tag == "session_maintenance_flatten_et"
    assert out.account.position_qty == 0


class _AlwaysEnterWhenFlat:
    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        if ctx.position_qty != 0:
            return []
        return [
            OrderRequest(OrderSide.BUY, 1, OrderType.MARKET, module_id="m"),
        ]


def test_entry_deadzone_weekday_no_fills() -> None:
    """No market fill during [17:00, 18:00) ET when strategy always wants in."""
    bars = pl.DataFrame(
        {
            "timestamp": [
                _et(2020, 6, 2, 17, 0),
                _et(2020, 6, 2, 17, 30),
            ],
            "open": [100.0, 100.0],
            "high": [100.0, 100.0],
            "low": [100.0, 100.0],
            "close": [100.0, 100.0],
            "volume": [1.0, 1.0],
        }
    )
    engine = BacktestEngine(BacktestConfig())
    out = engine.run(bars, [as_module("m", _AlwaysEnterWhenFlat())])
    assert len(out.fills) == 0


def test_entry_deadzone_sunday_et_same_wall_clock() -> None:
    """Sunday 2020-06-07: maintenance deadzone is still ET wall-clock [17:00, 18:00)."""
    bars = pl.DataFrame(
        {
            "timestamp": [
                _et(2020, 6, 7, 17, 15),
                _et(2020, 6, 7, 17, 45),
            ],
            "open": [100.0, 100.0],
            "high": [100.0, 100.0],
            "low": [100.0, 100.0],
            "close": [100.0, 100.0],
            "volume": [1.0, 1.0],
        }
    )
    engine = BacktestEngine(BacktestConfig())
    out = engine.run(bars, [as_module("m", _AlwaysEnterWhenFlat())])
    assert len(out.fills) == 0


def test_1659_drops_pending_market_so_no_fill_at_1700_open() -> None:
    """Market order on 16:59 bar must not fill at 17:00 open (next bar)."""
    bars = pl.DataFrame(
        {
            "timestamp": [
                _et(2020, 6, 2, 16, 59),
                _et(2020, 6, 2, 17, 0),
                _et(2020, 6, 3, 10, 0),
                _et(2020, 6, 3, 10, 1),
            ],
            "open": [100.0, 100.0, 99.0, 99.0],
            "high": [100.0, 100.0, 99.0, 99.0],
            "low": [100.0, 100.0, 99.0, 99.0],
            "close": [100.0, 100.0, 99.0, 99.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        }
    )
    engine = BacktestEngine(BacktestConfig())
    out = engine.run(bars, [as_module("m", _AlwaysEnterWhenFlat())])
    fills = out.fills
    assert len(fills) == 2
    assert fills[0].base_price == 99.0
    assert fills[1].tag == "end_of_series_flatten"


def test_hygiene_disabled_spans_maintenance() -> None:
    """Explicit ``enabled=False`` preserves legacy tests / long-window sanity checks."""
    bars = pl.DataFrame(
        {
            "timestamp": [
                _et(2020, 6, 2, 16, 59),
                _et(2020, 6, 2, 17, 0),
            ],
            "open": [100.0, 100.0],
            "high": [100.0, 100.0],
            "low": [100.0, 100.0],
            "close": [100.0, 100.0],
            "volume": [1.0, 1.0],
        }
    )
    cfg = BacktestConfig(
        session=SessionSpec(
            intraday_hygiene=IntradaySessionHygieneSpec(enabled=False),
        ),
    )
    engine = BacktestEngine(cfg)
    out = engine.run(bars, [as_module("m", _AlwaysEnterWhenFlat())])
    assert len(out.fills) == 2
    assert out.fills[0].side == OrderSide.BUY
    assert out.fills[0].timestamp == bars["timestamp"][1]
    assert out.fills[1].tag == "end_of_series_flatten"
