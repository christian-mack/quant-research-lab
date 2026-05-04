"""Trade ledger rows vs Account realized P&amp;L."""

from __future__ import annotations

from datetime import UTC, datetime

from quant_research.backtest.account import Account
from quant_research.backtest.specs import InstrumentSpec
from quant_research.backtest.trade_ledger import TradeLedger
from quant_research.backtest.types import OrderSide, SimulatedFill

_TS0 = datetime(2020, 1, 2, 14, 0, tzinfo=UTC)
_TS1 = datetime(2020, 1, 2, 14, 1, tzinfo=UTC)
_INS = InstrumentSpec(tick_value=2.0)


def _fill(
    oid: int,
    side: OrderSide,
    qty: int,
    price: float,
    mid: str,
    comm: float = 0.0,
    tag: str = "",
) -> SimulatedFill:
    return SimulatedFill(
        order_id=oid,
        timestamp=_TS0,
        side=side,
        quantity=qty,
        base_price=price,
        price=price,
        commission=comm,
        module_id=mid,
        tag=tag,
    )


def test_round_trip_row_matches_account() -> None:
    ledger = TradeLedger(_INS.tick_value)
    acct = Account(50_000.0, _INS)
    f1 = SimulatedFill(
        1,
        _TS0,
        OrderSide.BUY,
        1,
        100.0,
        100.0,
        0.0,
        module_id="orb",
    )
    pq = acct.position_qty
    acct.apply_fill(f1)
    ledger.note_fill(f1, pq, acct.position_qty, 0)

    f2 = SimulatedFill(
        2,
        _TS1,
        OrderSide.SELL,
        1,
        102.0,
        102.0,
        0.0,
        module_id="orb",
    )
    pq = acct.position_qty
    acct.apply_fill(f2)
    ledger.note_fill(f2, pq, acct.position_qty, 1)

    df = ledger.to_dataframe()
    assert df.height == 1
    row = df.row(0, named=True)
    assert row["net_pnl"] == 4.0
    assert row["module_id"] == "orb"
    assert row["exit_reason"] == "close"
    assert row["bars_held"] == 1


def test_flatten_exit_reason() -> None:
    ledger = TradeLedger(_INS.tick_value)
    f1 = _fill(1, OrderSide.BUY, 1, 100.0, "orb")
    ledger.note_fill(f1, 0, 1, 0)
    f2 = _fill(2, OrderSide.SELL, 1, 101.0, "orb", tag="end_of_series_flatten")
    ledger.note_fill(f2, 1, 0, 2)
    df = ledger.to_dataframe()
    assert df.row(0, named=True)["exit_reason"] == "flatten"
