"""Bar-by-bar backtest host: next-bar market fills, stop/limit resolution, P&amp;L."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from quant_research.backtest.account import Account
from quant_research.backtest.fill_resolution import (
    fill_pending_market_at_open,
    resolve_stop_limit_for_bar,
    validate_order_request,
)
from quant_research.backtest.schema import empty_trade_log
from quant_research.backtest.specs import BacktestConfig, MarketFillTiming
from quant_research.backtest.types import (
    BarContext,
    OrderRequest,
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


class BacktestEngine:
    """Closed-bar decisions; market orders fill at the **next** bar's open."""

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self._next_order_id = 1

    def run(self, bars: pl.DataFrame, strategy: Strategy) -> BacktestResult:
        if self.config.fill_model.market_fill_timing != MarketFillTiming.OPEN_OF_NEXT_BAR:
            msg = "only MarketFillTiming.OPEN_OF_NEXT_BAR is implemented"
            raise NotImplementedError(msg)

        missing = _REQUIRED_BAR_COLUMNS - set(bars.columns)
        if missing:
            msg = f"bars missing columns: {sorted(missing)}"
            raise ValueError(msg)

        df = bars.sort("timestamp")
        account = Account(self.config.run.initial_cash, self.config.instrument)
        pending_market: list[QueuedOrder] = []
        working: list[QueuedOrder] = []
        prev_close: float | None = None
        all_fills: list[SimulatedFill] = []

        for i, row in enumerate(df.iter_rows(named=True)):
            ts = row["timestamp"]
            o = float(row["open"])
            h = float(row["high"])
            low_px = float(row["low"])
            c = float(row["close"])
            v = float(row["volume"])

            for f in fill_pending_market_at_open(
                pending_market, o, ts, self.config
            ):
                account.apply_fill(f)
                all_fills.append(f)
            pending_market.clear()

            sf, working = resolve_stop_limit_for_bar(
                working, o, h, low_px, c, prev_close, ts, self.config
            )
            for f in sf:
                account.apply_fill(f)
                all_fills.append(f)

            ctx = BarContext(i, ts, o, h, low_px, c, v)
            self._route_orders(strategy.on_bar(ctx), pending_market, working)

            prev_close = c

        return BacktestResult(empty_trade_log(), all_fills, account)

    def _route_orders(
        self,
        orders: list[OrderRequest],
        pending_market: list[QueuedOrder],
        working: list[QueuedOrder],
    ) -> None:
        for req in orders:
            validate_order_request(req)
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
