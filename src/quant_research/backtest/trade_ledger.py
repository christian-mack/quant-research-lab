"""Build canonical trade log rows from filled round-trips (flat-to-flat)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import polars as pl

from quant_research.backtest.schema import empty_trade_log, trade_log_schema
from quant_research.backtest.types import OrderSide, SimulatedFill


@dataclass(slots=True)
class _OpenRound:
    trade_id: int
    module_id: str
    signed_qty: int
    report_qty: int
    entry_vwap: float
    entry_time: Any
    entry_bar: int
    commission: float
    gross_pnl: float
    exit_vwap_numer: float
    exit_qty_closed: int
    exit_time: Any | None
    exit_bar: int | None
    exit_reason: str


class TradeLedger:
    """One completed row per flat-to-flat cycle (supports scale-in / partials)."""

    def __init__(self, dollars_per_point: float) -> None:
        self.dollars_per_point = dollars_per_point
        self.rows: list[dict[str, Any]] = []
        self._next_trade_id = 1
        self._open: _OpenRound | None = None

    def note_fill(
        self,
        fill: SimulatedFill,
        prev_qty: int,
        new_qty: int,
        bar_index: int,
    ) -> None:
        dp = self.dollars_per_point

        if self._open is None:
            if prev_qty == 0 and new_qty != 0:
                self._open = self._start_round(fill, new_qty, bar_index)
                self._next_trade_id += 1
            return

        o = self._open
        o.commission += fill.commission

        if prev_qty > 0 and new_qty < 0:
            self._close_long_to_flat_or_zero(fill, prev_qty, 0, bar_index, dp)
            self._finalize_round()
            self._open = self._start_round(fill, new_qty, bar_index, commission_credit=0.0)
            self._next_trade_id += 1
            return
        if prev_qty < 0 and new_qty > 0:
            self._close_short_to_flat_or_zero(fill, prev_qty, 0, bar_index, dp)
            self._finalize_round()
            self._open = self._start_round(fill, new_qty, bar_index, commission_credit=0.0)
            self._next_trade_id += 1
            return

        if prev_qty > 0:
            self._apply_long_leg(fill, prev_qty, new_qty, bar_index, dp)
        elif prev_qty < 0:
            self._apply_short_leg(fill, prev_qty, new_qty, bar_index, dp)

        if new_qty == 0:
            self._finalize_round()
            self._open = None
        elif self._open is not None:
            self._open.signed_qty = new_qty

    def to_dataframe(self, git_sha: str | None = None) -> pl.DataFrame:
        sha = git_sha if git_sha is not None else os.environ.get("MFA_GIT_SHA", "")
        if not self.rows:
            return empty_trade_log()
        for r in self.rows:
            r["mfa_git_sha"] = sha
        return pl.DataFrame(self.rows, schema=trade_log_schema())

    def _start_round(
        self,
        fill: SimulatedFill,
        new_qty: int,
        bar_index: int,
        *,
        commission_credit: float | None = None,
    ) -> _OpenRound:
        comm = fill.commission if commission_credit is None else commission_credit
        return _OpenRound(
            trade_id=self._next_trade_id,
            module_id=fill.module_id,
            signed_qty=new_qty,
            report_qty=abs(new_qty),
            entry_vwap=fill.price,
            entry_time=fill.timestamp,
            entry_bar=bar_index,
            commission=comm,
            gross_pnl=0.0,
            exit_vwap_numer=0.0,
            exit_qty_closed=0,
            exit_time=fill.timestamp,
            exit_bar=bar_index,
            exit_reason="",
        )

    def _apply_long_leg(
        self,
        fill: SimulatedFill,
        prev_qty: int,
        new_qty: int,
        bar_index: int,
        dp: float,
    ) -> None:
        o = self._open
        assert o is not None
        if fill.side == OrderSide.SELL and new_qty < prev_qty:
            closed = prev_qty - max(new_qty, 0)
            o.gross_pnl += (fill.price - o.entry_vwap) * closed * dp
            o.exit_vwap_numer += fill.price * closed
            o.exit_qty_closed += closed
            o.exit_time = fill.timestamp
            o.exit_bar = bar_index
            o.exit_reason = fill.tag or "close"
        elif fill.side == OrderSide.BUY and new_qty > prev_qty:
            added = new_qty - prev_qty
            o.entry_vwap = (o.entry_vwap * prev_qty + fill.price * added) / new_qty
            o.report_qty = max(o.report_qty, abs(new_qty))

    def _apply_short_leg(
        self,
        fill: SimulatedFill,
        prev_qty: int,
        new_qty: int,
        bar_index: int,
        dp: float,
    ) -> None:
        o = self._open
        assert o is not None
        abs_prev = -prev_qty
        if fill.side == OrderSide.BUY and new_qty > prev_qty:
            closed = abs_prev - max(-new_qty, 0)
            o.gross_pnl += (o.entry_vwap - fill.price) * closed * dp
            o.exit_vwap_numer += fill.price * closed
            o.exit_qty_closed += closed
            o.exit_time = fill.timestamp
            o.exit_bar = bar_index
            o.exit_reason = fill.tag or "close"
        elif fill.side == OrderSide.SELL and new_qty < prev_qty:
            added = -new_qty - abs_prev
            new_abs = -new_qty
            o.entry_vwap = (o.entry_vwap * abs_prev + fill.price * added) / new_abs
            o.report_qty = max(o.report_qty, new_abs)

    def _close_long_to_flat_or_zero(
        self,
        fill: SimulatedFill,
        prev_qty: int,
        new_qty: int,
        bar_index: int,
        dp: float,
    ) -> None:
        o = self._open
        assert o is not None
        closed = prev_qty - max(new_qty, 0)
        o.gross_pnl += (fill.price - o.entry_vwap) * closed * dp
        o.exit_vwap_numer += fill.price * closed
        o.exit_qty_closed += closed
        o.exit_time = fill.timestamp
        o.exit_bar = bar_index
        o.exit_reason = fill.tag or "close"

    def _close_short_to_flat_or_zero(
        self,
        fill: SimulatedFill,
        prev_qty: int,
        new_qty: int,
        bar_index: int,
        dp: float,
    ) -> None:
        o = self._open
        assert o is not None
        abs_prev = -prev_qty
        abs_new = max(-new_qty, 0)
        closed = abs_prev - abs_new
        o.gross_pnl += (o.entry_vwap - fill.price) * closed * dp
        o.exit_vwap_numer += fill.price * closed
        o.exit_qty_closed += closed
        o.exit_time = fill.timestamp
        o.exit_bar = bar_index
        o.exit_reason = fill.tag or "close"

    def _finalize_round(self) -> None:
        o = self._open
        assert o is not None
        exit_px = (
            o.exit_vwap_numer / o.exit_qty_closed if o.exit_qty_closed > 0 else o.entry_vwap
        )
        direction = "long" if o.signed_qty > 0 else "short"
        reason = o.exit_reason or "close"
        if reason == "end_of_series_flatten":
            reason = "flatten"
        net = o.gross_pnl - o.commission
        exit_bar = o.exit_bar if o.exit_bar is not None else o.entry_bar
        bars_held = exit_bar - o.entry_bar
        self.rows.append(
            {
                "trade_id": o.trade_id,
                "module_id": o.module_id,
                "entry_time": o.entry_time,
                "exit_time": o.exit_time,
                "direction": direction,
                "quantity": o.report_qty,
                "entry_price": o.entry_vwap,
                "exit_price": exit_px,
                "gross_pnl": o.gross_pnl,
                "commission": o.commission,
                "net_pnl": net,
                "exit_reason": reason,
                "bars_held": int(bars_held),
                "mfa_git_sha": "",
            }
        )
