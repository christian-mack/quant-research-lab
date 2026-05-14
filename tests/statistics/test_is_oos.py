"""Tests for :mod:`quant_research.statistics.is_oos`."""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quant_research.statistics.is_oos import IsoSplitConfig, split_trade_log_is_oos


def _tiny_log() -> pl.DataFrame:
    base = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
    times = [base + dt.timedelta(days=i) for i in range(10)]
    return pl.DataFrame(
        {
            "exit_time": times,
            "net_pnl": [float(i - 4) for i in range(10)],
        },
    )


def test_split_by_trade_count_60_40() -> None:
    df = _tiny_log()
    is_df, oos_df = split_trade_log_is_oos(df, IsoSplitConfig(is_fraction=0.6, mode="trade_count"))
    assert is_df.height == 6
    assert oos_df.height == 4


def test_split_by_time_quantile() -> None:
    df = _tiny_log()
    is_df, oos_df = split_trade_log_is_oos(df, IsoSplitConfig(is_fraction=0.5, mode="time"))
    assert is_df.height + oos_df.height == 10
    assert is_df["exit_time"].max() <= oos_df["exit_time"].min()


def test_split_empty_raises() -> None:
    empty = pl.DataFrame(schema={"exit_time": pl.Datetime("us", "UTC"), "net_pnl": pl.Float64})
    with pytest.raises(ValueError, match="empty"):
        split_trade_log_is_oos(empty)
