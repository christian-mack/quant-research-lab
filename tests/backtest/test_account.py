"""Tests for Account P&amp;L and average price."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from quant_research.backtest.account import Account
from quant_research.backtest.specs import InstrumentSpec
from quant_research.backtest.types import OrderSide, SimulatedFill

_TS = datetime(2020, 1, 2, tzinfo=UTC)
_MNQ = InstrumentSpec(tick_size=0.25, tick_value=2.0)  # $2 per point


def _fill(oid: int, side: OrderSide, qty: int, price: float, comm: float = 0.0) -> SimulatedFill:
    return SimulatedFill(
        order_id=oid,
        timestamp=_TS,
        side=side,
        quantity=qty,
        base_price=price,
        price=price,
        commission=comm,
    )


def test_long_round_trip_pnl_per_point() -> None:
    a = Account(50_000.0, _MNQ)
    a.apply_fill(_fill(1, OrderSide.BUY, 1, 100.0))
    a.apply_fill(_fill(2, OrderSide.SELL, 1, 102.0))
    assert a.position_qty == 0
    assert a.realized_pnl == 4.0
    assert a.cash == 50_000.0 + 4.0


def test_long_with_commission() -> None:
    cfg = InstrumentSpec(tick_size=0.25, tick_value=2.0)
    a = Account(50_000.0, cfg)
    a.apply_fill(_fill(1, OrderSide.BUY, 1, 100.0, comm=1.25))
    a.apply_fill(_fill(2, OrderSide.SELL, 1, 102.0, comm=1.25))
    assert a.realized_pnl == 4.0
    assert a.total_commission == 2.5
    assert a.cash == 50_000.0 + 4.0 - 2.5


def test_short_round_trip() -> None:
    a = Account(50_000.0, _MNQ)
    a.apply_fill(_fill(1, OrderSide.SELL, 1, 102.0))
    a.apply_fill(_fill(2, OrderSide.BUY, 1, 100.0))
    assert a.position_qty == 0
    assert pytest.approx(a.realized_pnl) == 4.0


def test_unrealized_long() -> None:
    a = Account(50_000.0, _MNQ)
    a.apply_fill(_fill(1, OrderSide.BUY, 2, 100.0))
    assert a.unrealized_pnl(101.0) == 4.0
    assert a.equity(101.0) == a.cash + 4.0


def test_scale_in_long_average() -> None:
    a = Account(50_000.0, _MNQ)
    a.apply_fill(_fill(1, OrderSide.BUY, 1, 100.0))
    a.apply_fill(_fill(2, OrderSide.BUY, 1, 102.0))
    assert a.position_qty == 2
    assert a.avg_entry == 101.0
