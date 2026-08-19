"""Tests for ledger-boundary geometry enforcement."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from quant_research.backtest.geometry import REJECT_STOP_WRONG_SIDE
from quant_research.backtest.trade_ledger import TradeLedger
from quant_research.backtest.types import OrderSide, SimulatedFill

CT = ZoneInfo("America/Chicago")
TS = dt.datetime(2024, 6, 10, 14, 0, tzinfo=CT)


def _fill(
    *,
    side: OrderSide,
    price: float,
    tag: str = "",
    stop: float | None = None,
    target: float | None = None,
    direction: str | None = None,
) -> SimulatedFill:
    return SimulatedFill(
        order_id=1,
        timestamp=TS,
        side=side,
        quantity=1,
        base_price=price,
        price=price,
        commission=0.0,
        module_id="m",
        tag=tag,
        bracket_stop=stop,
        bracket_target=target,
        bracket_direction=direction,
    )


def test_ledger_rejects_incoherent_long_at_finalize() -> None:
    ledger = TradeLedger(2.0, enforce_geometry=True)
    ledger.note_fill(
        _fill(
            side=OrderSide.BUY,
            price=100.0,
            tag="entry",
            stop=100.5,
            target=103.0,
            direction="long",
        ),
        0,
        1,
        0,
    )
    ledger.note_fill(_fill(side=OrderSide.SELL, price=100.5, tag="stop"), 1, 0, 0)
    assert len(ledger.rows) == 0
    assert ledger.geometry_rejects.get(REJECT_STOP_WRONG_SIDE) == 1


def test_ledger_books_coherent_long() -> None:
    ledger = TradeLedger(2.0, enforce_geometry=True)
    ledger.note_fill(
        _fill(
            side=OrderSide.BUY,
            price=100.0,
            tag="entry",
            stop=99.0,
            target=102.0,
            direction="long",
        ),
        0,
        1,
        0,
    )
    ledger.note_fill(_fill(side=OrderSide.SELL, price=102.0, tag="target"), 1, 0, 1)
    df = ledger.to_dataframe()
    assert df.height == 1
    assert df["stop_price"][0] == pytest.approx(99.0)
    assert df["target_price"][0] == pytest.approx(102.0)
