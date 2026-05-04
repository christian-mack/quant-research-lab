"""Canonical trade log layout (``docs/m4-backtest-engine-design.md`` §6)."""

from __future__ import annotations

import polars as pl


def trade_log_schema() -> dict[str, pl.DataType]:
    return {
        "trade_id": pl.Int64,
        "module_id": pl.Utf8,
        "entry_time": pl.Datetime(time_zone="UTC"),
        "exit_time": pl.Datetime(time_zone="UTC"),
        "direction": pl.Utf8,
        "quantity": pl.Int32,
        "entry_price": pl.Float64,
        "exit_price": pl.Float64,
        "gross_pnl": pl.Float64,
        "commission": pl.Float64,
        "net_pnl": pl.Float64,
        "exit_reason": pl.Utf8,
        "bars_held": pl.Int32,
        "mfa_git_sha": pl.Utf8,
    }


def empty_trade_log() -> pl.DataFrame:
    return pl.DataFrame(schema=trade_log_schema())
