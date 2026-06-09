"""IS/OOS partition and Gate #1 mortality metrics for P2 (M4 trade log)."""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl

from quant_research.backtest.m6_metrics import protocol_year_fraction
from quant_research.backtest.validation import ValidationThresholds
from quant_research.research_p2w2.costs import P2_W2_BACKTEST_CONFIG

P2_W2_V4_TICK_THRESHOLD = 50.0
IS_FRACTION = 0.60


def split_is_oos_log(
    trade_log: pl.DataFrame,
    *,
    is_fraction: float = IS_FRACTION,
) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, Any]]:
    """Chronological 60/40 split by trade count."""
    if trade_log.is_empty():
        empty = trade_log
        return empty, empty, {
            "total_trades": 0,
            "is_trade_count": 0,
            "oos_trade_count": 0,
            "is_fraction": is_fraction,
            "is_oos_boundary_last_is_exit": None,
            "is_oos_boundary_first_oos_entry": None,
        }
    ordered = trade_log.sort("exit_time")
    n = ordered.height
    n_is = int(n * is_fraction) if n else 0
    is_log = ordered.head(n_is)
    oos_log = ordered.tail(n - n_is)
    boundary_exit = is_log["exit_time"][-1] if n_is else None
    boundary_entry = oos_log["entry_time"][0] if oos_log.height else None
    return is_log, oos_log, {
        "total_trades": n,
        "is_trade_count": n_is,
        "oos_trade_count": n - n_is,
        "is_fraction": is_fraction,
        "is_oos_boundary_last_is_exit": boundary_exit.isoformat() if boundary_exit else None,
        "is_oos_boundary_first_oos_entry": boundary_entry.isoformat() if boundary_entry else None,
    }


def gate1_is_screen_log(is_log: pl.DataFrame) -> dict[str, Any]:
    """Gate #1: net-of-cost per-trade expectancy on IS."""
    if is_log.is_empty():
        return {
            "is_trade_count": 0,
            "gross_expectancy_per_trade": 0.0,
            "cost_per_trade": 0.0,
            "net_expectancy_per_trade": 0.0,
            "win_rate": 0.0,
            "avg_win_net": 0.0,
            "avg_loss_net": 0.0,
            "max_single_trade_loss_net": 0.0,
            "p95_single_trade_loss_net": 0.0,
            "verdict": "DEAD",
            "verdict_reason": "no IS trades",
        }

    gross = is_log["gross_pnl"].to_numpy()
    comm = is_log["commission"].to_numpy()
    net = is_log["net_pnl"].to_numpy()
    wins = net[net > 0]
    losses = net[net < 0]
    loss_mag = -net[net < 0]

    net_exp = float(np.mean(net))
    verdict = "SURVIVOR" if net_exp > 0 else "DEAD"

    return {
        "is_trade_count": is_log.height,
        "gross_expectancy_per_trade": float(np.mean(gross)),
        "cost_per_trade": float(np.mean(comm)),
        "net_expectancy_per_trade": net_exp,
        "win_rate": float(np.mean(net > 0)),
        "avg_win_net": float(np.mean(wins)) if wins.size else 0.0,
        "avg_loss_net": float(np.mean(losses)) if losses.size else 0.0,
        "max_single_trade_loss_net": float(np.max(loss_mag)) if loss_mag.size else 0.0,
        "p95_single_trade_loss_net": float(np.percentile(loss_mag, 95)) if loss_mag.size else 0.0,
        "verdict": verdict,
        "verdict_reason": "net expectancy > 0" if verdict == "SURVIVOR" else "net expectancy <= 0",
    }


def trades_per_yr(total_trades: int, protocol_start: str, protocol_end: str) -> float:
    yfrac = protocol_year_fraction(protocol_start, protocol_end)
    return total_trades / yfrac if yfrac > 0 else 0.0


def validation_thresholds() -> ValidationThresholds:
    return ValidationThresholds(implausible_net_ticks_per_trade=P2_W2_V4_TICK_THRESHOLD)
