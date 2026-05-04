"""Bar-by-bar backtest host (M4 scaffolding)."""

from __future__ import annotations

import polars as pl

from quant_research.backtest.schema import empty_trade_log
from quant_research.backtest.specs import BacktestConfig
from quant_research.backtest.types import BarContext, Strategy

_REQUIRED_BAR_COLUMNS = frozenset({"timestamp", "open", "high", "low", "close", "volume"})


class BacktestEngine:
    """Minimal event loop: closed-bar callback, no fill simulation yet."""

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config

    def run(self, bars: pl.DataFrame, strategy: Strategy) -> pl.DataFrame:
        missing = _REQUIRED_BAR_COLUMNS - set(bars.columns)
        if missing:
            msg = f"bars missing columns: {sorted(missing)}"
            raise ValueError(msg)

        df = bars.sort("timestamp")
        for i, row in enumerate(df.iter_rows(named=True)):
            ctx = BarContext(
                bar_index=i,
                timestamp=row["timestamp"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            strategy.on_bar(ctx)

        return empty_trade_log()
