"""Smoke tests for M4 backtest scaffold."""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from quant_research.backtest import (
    BacktestConfig,
    BacktestEngine,
    BarContext,
    trade_log_schema,
)


class _NullStrategy:
    def on_bar(self, ctx: BarContext) -> list:
        return []


def test_engine_run_empty_trade_log() -> None:
    bars = pl.DataFrame(
        {
            "timestamp": [
                datetime(2020, 1, 2, 14, 0, tzinfo=UTC),
                datetime(2020, 1, 2, 14, 1, tzinfo=UTC),
            ],
            "open": [3000.0, 3001.0],
            "high": [3001.0, 3002.0],
            "low": [2999.0, 3000.0],
            "close": [3000.5, 3001.5],
            "volume": [100.0, 110.0],
        }
    )
    engine = BacktestEngine(BacktestConfig())
    out = engine.run(bars, _NullStrategy())
    assert out.columns == list(trade_log_schema().keys())
    assert out.height == 0


def test_engine_missing_columns() -> None:
    bars = pl.DataFrame({"timestamp": [datetime(2020, 1, 1, tzinfo=UTC)], "open": [1.0]})
    engine = BacktestEngine(BacktestConfig())
    with pytest.raises(ValueError, match="missing columns"):
        engine.run(bars, _NullStrategy())
