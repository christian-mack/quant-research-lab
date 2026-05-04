"""Tests for intrabar path, gap policy, and market-at-open fills."""

from __future__ import annotations

from datetime import UTC, datetime

from quant_research.backtest.fill_resolution import (
    effective_intrabar_path,
    fill_pending_market_at_open,
    gap_would_trigger,
    intrabar_pivot_prices,
    resolve_stop_limit_for_bar,
)
from quant_research.backtest.specs import (
    BacktestConfig,
    FillModelSpec,
    GapPolicy,
    IntrabarPricePath,
    StopLimitIntrabarPolicy,
)
from quant_research.backtest.types import OrderRequest, OrderSide, OrderType, QueuedOrder

_TS = datetime(2020, 1, 2, 14, 0, tzinfo=UTC)
_CFG = BacktestConfig()


def test_intrabar_pivot_prices_dedup() -> None:
    piv = intrabar_pivot_prices(100.0, 100.0, 99.0, 99.5, IntrabarPricePath.OPEN_HIGH_LOW_CLOSE)
    assert piv == [100.0, 99.0, 99.5]


def test_effective_path_pessimistic() -> None:
    fm = FillModelSpec(stop_limit_intrabar=StopLimitIntrabarPolicy.PESSIMISTIC)
    assert effective_intrabar_path(fm) == IntrabarPricePath.OPEN_LOW_HIGH_CLOSE


def test_buy_stop_first_touch_ohlc() -> None:
    w = [
        QueuedOrder(
            1,
            OrderRequest(OrderSide.BUY, 1, OrderType.STOP, stop_price=100.0),
        )
    ]
    fills, rest = resolve_stop_limit_for_bar(
        w, open_px=99.0, high=101.0, low=98.5, close=99.5, prior_close=98.0, ts=_TS, config=_CFG
    )
    assert len(fills) == 1
    assert fills[0].base_price == 100.0
    assert fills[0].price == 100.0  # no slippage
    assert rest == []


def test_gap_buy_stop_fill_at_open() -> None:
    w = [
        QueuedOrder(
            1,
            OrderRequest(OrderSide.BUY, 1, OrderType.STOP, stop_price=100.0),
        )
    ]
    fills, rest = resolve_stop_limit_for_bar(
        w, open_px=100.5, high=101.0, low=100.0, close=100.25, prior_close=99.0, ts=_TS, config=_CFG
    )
    assert len(fills) == 1
    assert fills[0].base_price == 100.5
    assert rest == []


def test_no_fill_on_gap_skips_open() -> None:
    cfg = BacktestConfig(
        fill_model=FillModelSpec(gap_policy=GapPolicy.NO_FILL_ON_GAP),
    )
    w = [
        QueuedOrder(
            1,
            OrderRequest(OrderSide.BUY, 1, OrderType.STOP, stop_price=100.0),
        )
    ]
    fills, rest = resolve_stop_limit_for_bar(
        w,
        open_px=100.5,
        high=100.75,
        low=100.4,
        close=100.55,
        prior_close=99.0,
        ts=_TS,
        config=cfg,
    )
    assert fills == []
    assert len(rest) == 1


def test_sell_limit_up_cross() -> None:
    w = [
        QueuedOrder(
            1,
            OrderRequest(OrderSide.SELL, 1, OrderType.LIMIT, limit_price=100.75),
        )
    ]
    fills, rest = resolve_stop_limit_for_bar(
        w,
        open_px=100.5,
        high=101.0,
        low=100.25,
        close=100.5,
        prior_close=100.0,
        ts=_TS,
        config=_CFG,
    )
    assert len(fills) == 1
    assert fills[0].base_price == 100.75
    assert rest == []


def test_market_fill_at_open() -> None:
    pending = [
        QueuedOrder(10, OrderRequest(OrderSide.BUY, 2, OrderType.MARKET)),
    ]
    fills = fill_pending_market_at_open(pending, open_px=3000.25, ts=_TS, config=_CFG)
    assert len(fills) == 1
    assert fills[0].quantity == 2
    assert fills[0].base_price == 3000.25
    assert fills[0].side == OrderSide.BUY


def test_gap_would_trigger_sell_stop() -> None:
    req = OrderRequest(OrderSide.SELL, 1, OrderType.STOP, stop_price=100.0)
    assert gap_would_trigger(req, prior_close=100.5, open_px=99.5) is True


def test_order_priority_by_order_id() -> None:
    w = [
        QueuedOrder(2, OrderRequest(OrderSide.BUY, 1, OrderType.STOP, stop_price=100.0)),
        QueuedOrder(1, OrderRequest(OrderSide.BUY, 1, OrderType.STOP, stop_price=100.0)),
    ]
    fills, _ = resolve_stop_limit_for_bar(
        w, open_px=99.0, high=101.0, low=98.0, close=99.5, prior_close=98.5, ts=_TS, config=_CFG
    )
    assert [f.order_id for f in fills] == [1, 2]
