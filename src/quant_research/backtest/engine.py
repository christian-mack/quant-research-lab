"""Bar-by-bar backtest host: OMAT, fills, trade log, end-of-series flatten."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from dataclasses import dataclass

import polars as pl

from quant_research.backtest.account import Account
from quant_research.backtest.fill_resolution import (
    fill_pending_market_at_open,
    resolve_stop_limit_for_bar,
    synthetic_market_fill,
    validate_order_request,
)
from quant_research.backtest.omat import StrategyModule, collect_orders_for_bar
from quant_research.backtest.specs import BacktestConfig, MarketFillTiming
from quant_research.backtest.trade_ledger import TradeLedger
from quant_research.backtest.types import (
    BarContext,
    OrderRequest,
    OrderSide,
    OrderType,
    QueuedOrder,
    SimulatedFill,
    Strategy,
)

_REQUIRED_BAR_COLUMNS = frozenset({"timestamp", "open", "high", "low", "close", "volume"})


@dataclass(slots=True)
class BacktestResult:
    trade_log: pl.DataFrame
    fills: list[SimulatedFill]
    account: Account


def _reconcile_owner(
    prev_qty: int,
    prev_owner: str | None,
    fill: SimulatedFill,
    new_qty: int,
) -> str | None:
    """Which module owns an open position after this fill (OMAT)."""
    if new_qty == 0:
        return None
    if prev_qty == 0:
        return fill.module_id
    if (prev_qty > 0 and new_qty < 0) or (prev_qty < 0 and new_qty > 0):
        return fill.module_id
    return prev_owner if prev_owner is not None else fill.module_id


def _apply_fills(
    fills: list[SimulatedFill],
    *,
    account: Account,
    ledger: TradeLedger,
    owner: str | None,
    bar_index: int,
    all_fills: list[SimulatedFill],
) -> str | None:
    pos_owner = owner
    for f in fills:
        pq = account.position_qty
        account.apply_fill(f)
        nq = account.position_qty
        pos_owner = _reconcile_owner(pq, pos_owner, f, nq)
        ledger.note_fill(f, pq, nq, bar_index)
        all_fills.append(f)
    return pos_owner


class BacktestEngine:
    """Closed-bar decisions; market orders fill at the **next** bar's open.

    **End of data:** Unfilled working and pending orders are **dropped** with
    ``UserWarning``. Any open position is **auto-flattened** at the **last
    bar's close** (not the next open) — a ``PYTHON_ASSUMPTION`` for series end;
    the synthetic exit uses tag ``end_of_series_flatten`` and ``exit_reason``
    ``flatten`` in the trade log.

    **Known deferral (NT8 ``ExecutionEngine.ManagePosition``):** ORB
    **``ORBMaxHoldMinutes``** / **``FlattenForRisk``** time-based flatten is **not**
    implemented in Python. Production ORB+Opt3 uses **0** (disabled). Add at
    **engine** level when a Phase 2 hypothesis needs it — see
    ``docs/m4-backtest-engine-design.md`` §10.
    """

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self._next_order_id = 1

    def run(
        self,
        bars: pl.DataFrame,
        modules: Sequence[StrategyModule],
    ) -> BacktestResult:
        if self.config.fill_model.market_fill_timing != MarketFillTiming.OPEN_OF_NEXT_BAR:
            msg = "only MarketFillTiming.OPEN_OF_NEXT_BAR is implemented"
            raise NotImplementedError(msg)

        missing = _REQUIRED_BAR_COLUMNS - set(bars.columns)
        if missing:
            msg = f"bars missing columns: {sorted(missing)}"
            raise ValueError(msg)

        mod_list = list(modules)
        if not mod_list:
            msg = "modules must be non-empty"
            raise ValueError(msg)

        df = bars.sort("timestamp")
        account = Account(self.config.run.initial_cash, self.config.instrument)
        ledger = TradeLedger(self.config.instrument.tick_value)
        pending_market: list[QueuedOrder] = []
        working: list[QueuedOrder] = []
        prev_close: float | None = None
        all_fills: list[SimulatedFill] = []
        position_owner: str | None = None

        last_bar_index = 0
        last_ts: object = None
        last_close = 0.0

        for i, row in enumerate(df.iter_rows(named=True)):
            ts = row["timestamp"]
            o = float(row["open"])
            h = float(row["high"])
            low_px = float(row["low"])
            c = float(row["close"])
            v = float(row["volume"])
            last_bar_index = i
            last_ts = ts
            last_close = c
            session_date = row.get("cme_session_date")

            mfills = fill_pending_market_at_open(pending_market, o, ts, self.config)
            pending_market.clear()
            before_m = account.position_qty
            position_owner = _apply_fills(
                mfills,
                account=account,
                ledger=ledger,
                owner=position_owner,
                bar_index=i,
                all_fills=all_fills,
            )
            if before_m != 0 and account.position_qty == 0:
                working.clear()

            sf, working = resolve_stop_limit_for_bar(
                working, o, h, low_px, c, prev_close, ts, self.config
            )
            before_s = account.position_qty
            position_owner = _apply_fills(
                sf,
                account=account,
                ledger=ledger,
                owner=position_owner,
                bar_index=i,
                all_fills=all_fills,
            )
            if before_s != 0 and account.position_qty == 0:
                working.clear()

            ctx = BarContext(
                i,
                ts,
                o,
                h,
                low_px,
                c,
                v,
                position_qty=account.position_qty,
                avg_entry_price=account.avg_entry if account.position_qty != 0 else None,
                session_date=session_date,
            )
            orders = collect_orders_for_bar(
                mod_list,
                ctx,
                orchestration=self.config.orchestration,
                position_qty=account.position_qty,
                position_owner=position_owner,
            )
            self._route_orders(orders, pending_market, working)

            prev_close = c

        self._end_of_series_cleanup(
            last_bar_index=last_bar_index,
            last_ts=last_ts,
            last_close=last_close,
            account=account,
            ledger=ledger,
            pending_market=pending_market,
            working=working,
            all_fills=all_fills,
            position_owner=position_owner,
        )

        trade_log = ledger.to_dataframe()
        return BacktestResult(trade_log=trade_log, fills=all_fills, account=account)

    def _end_of_series_cleanup(
        self,
        *,
        last_bar_index: int,
        last_ts: object,
        last_close: float,
        account: Account,
        ledger: TradeLedger,
        pending_market: list[QueuedOrder],
        working: list[QueuedOrder],
        all_fills: list[SimulatedFill],
        position_owner: str | None,
    ) -> str | None:
        if pending_market or working:
            warnings.warn(
                "Backtest end: discarding unfilled pending market and working "
                "stop/limit orders (no next bar to evaluate).",
                UserWarning,
                stacklevel=3,
            )
            pending_market.clear()
            working.clear()
        q = account.position_qty
        if q == 0:
            return None
        mod_id = position_owner if position_owner is not None else "unknown"
        warnings.warn(
            "Backtest end: auto-flattening open position at last bar close "
            "(fills at last close, not next open; see BacktestEngine docstring).",
            UserWarning,
            stacklevel=3,
        )
        side = OrderSide.SELL if q > 0 else OrderSide.BUY
        fill = synthetic_market_fill(
            order_id=self._next_order_id,
            module_id=mod_id,
            side=side,
            quantity=abs(q),
            base_price=last_close,
            ts=last_ts,
            config=self.config,
            tag="end_of_series_flatten",
        )
        self._next_order_id += 1
        pq = account.position_qty
        account.apply_fill(fill)
        ledger.note_fill(fill, pq, account.position_qty, last_bar_index)
        all_fills.append(fill)
        return _reconcile_owner(pq, position_owner, fill, account.position_qty)

    def _route_orders(
        self,
        orders: list[OrderRequest],
        pending_market: list[QueuedOrder],
        working: list[QueuedOrder],
    ) -> None:
        for req in orders:
            validate_order_request(req)
            if req.dedupe_tag:
                dt = req.dedupe_tag
                mid = req.module_id
                working[:] = [
                    w
                    for w in working
                    if not (
                        w.request.module_id == mid and w.request.dedupe_tag == dt
                    )
                ]
            oid = self._next_order_id
            self._next_order_id += 1
            q = QueuedOrder(oid, req)
            if req.order_type == OrderType.MARKET:
                pending_market.append(q)
            elif req.order_type in (OrderType.LIMIT, OrderType.STOP):
                working.append(q)
            else:
                msg = f"unknown order type: {req.order_type!r}"
                raise ValueError(msg)


def as_module(module_id: str, strategy: Strategy) -> StrategyModule:
    """Convenience wrapper for single-module runs."""
    return StrategyModule(module_id, strategy)
