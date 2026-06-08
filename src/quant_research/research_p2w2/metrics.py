"""IS/OOS partition and Gate #1 mortality metrics for P2-W2."""

from __future__ import annotations

import datetime as dt
from typing import Any

import numpy as np
import polars as pl

from quant_research.backtest.schema import trade_log_schema
from quant_research.backtest.validation import (
    ValidationReport,
    ValidationThresholds,
    validate_backtest_result,
)

# Pre-registered stop caps reach 10pt (= 40 ticks); avg loss near cap is plausible, not a bug.
P2_W2_V4_TICK_THRESHOLD = 50.0
from quant_research.research_p2w2.costs import P2Trade, P2_W2_BACKTEST_CONFIG

IS_FRACTION = 0.60


def split_is_oos(
    trades: list[P2Trade],
    *,
    is_fraction: float = IS_FRACTION,
) -> tuple[list[P2Trade], list[P2Trade], dict[str, Any]]:
    """Chronological 60/40 split by trade count."""
    ordered = sorted(trades, key=lambda t: t.exit_time)
    n = len(ordered)
    n_is = int(n * is_fraction) if n else 0
    is_trades = ordered[:n_is]
    oos_trades = ordered[n_is:]
    boundary_exit = is_trades[-1].exit_time if is_trades else None
    boundary_entry = oos_trades[0].entry_time if oos_trades else None
    return is_trades, oos_trades, {
        "total_trades": n,
        "is_trade_count": n_is,
        "oos_trade_count": n - n_is,
        "is_fraction": is_fraction,
        "is_oos_boundary_last_is_exit": boundary_exit.isoformat() if boundary_exit else None,
        "is_oos_boundary_first_oos_entry": boundary_entry.isoformat() if boundary_entry else None,
    }


def trades_to_harness_log(
    trades: list[P2Trade],
    *,
    git_sha: str,
) -> pl.DataFrame:
    """Build M4 trade log for validation harness."""
    rows: list[dict[str, object]] = []
    for i, t in enumerate(trades, start=1):
        rows.append(
            {
                "trade_id": i,
                "module_id": t.hypothesis_id.lower().replace("-", ""),
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "direction": "long" if t.direction == 1 else "short",
                "quantity": 1,
                "entry_price": t.entry_price,
                "stop_price": t.stop_price,
                "target_price": t.target_price,
                "exit_price": t.exit_price,
                "gross_pnl": t.gross_pnl,
                "commission": t.commission,
                "net_pnl": t.net_pnl,
                "exit_reason": t.exit_reason,
                "entry_bar": 0,
                "bars_held": t.bars_held,
                "mfa_git_sha": git_sha,
            }
        )
    schema = {**trade_log_schema()}
    return pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)


def run_harness(
    trades: list[P2Trade],
    *,
    git_sha: str,
) -> ValidationReport:
    """V1–V6 on the booked trade population."""
    log = trades_to_harness_log(trades, git_sha=git_sha)
    return validate_backtest_result(
        log,
        config=P2_W2_BACKTEST_CONFIG,
        geometry_reject_rate=0.0,
        thresholds=ValidationThresholds(
            implausible_net_ticks_per_trade=P2_W2_V4_TICK_THRESHOLD,
        ),
    )


def gate1_is_screen(is_trades: list[P2Trade]) -> dict[str, Any]:
    """Gate #1: net-of-cost per-trade expectancy on IS."""
    if not is_trades:
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

    gross = np.array([t.gross_pnl for t in is_trades], dtype=np.float64)
    comm = np.array([t.commission for t in is_trades], dtype=np.float64)
    net = np.array([t.net_pnl for t in is_trades], dtype=np.float64)
    wins = net[net > 0]
    losses = net[net < 0]
    loss_mag = -net[net < 0]

    net_exp = float(np.mean(net))
    verdict = "SURVIVOR" if net_exp > 0 else "DEAD"

    return {
        "is_trade_count": len(is_trades),
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
