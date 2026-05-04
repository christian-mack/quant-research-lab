"""Aggregate trade-log metrics for M6 smoke vs NT8 reference (not per-trade parity)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import polars as pl


@dataclass(frozen=True, slots=True)
class M6AggregateResult:
    """Summary statistics from a closed-trade log (single module / instrument scale)."""

    trade_count: int
    net_pnl_total: float
    gross_profit_sum: float
    gross_loss_sum: float
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown: float
    years_calendar: dict[int, float]
    years_positive_count: int
    years_total_count: int


def _max_drawdown_cumulative(cumulative: list[float]) -> float:
    """Largest peak-to-trough drop on a cumulative P&amp;L curve (non-positive)."""
    if not cumulative:
        return 0.0
    peak = cumulative[0]
    max_dd = 0.0
    for c in cumulative:
        if c > peak:
            peak = c
        dd = c - peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def compute_m6_aggregates(
    trade_log: pl.DataFrame,
    *,
    exit_year_tz: str = "America/Chicago",
) -> M6AggregateResult:
    """Compute aggregates from canonical ``trade_log`` (requires ``exit_time``, ``net_pnl``)."""
    if trade_log.is_empty():
        return M6AggregateResult(
            trade_count=0,
            net_pnl_total=0.0,
            gross_profit_sum=0.0,
            gross_loss_sum=0.0,
            win_count=0,
            loss_count=0,
            breakeven_count=0,
            win_rate=0.0,
            avg_win=0.0,
            avg_loss=0.0,
            profit_factor=0.0,
            max_drawdown=0.0,
            years_calendar={},
            years_positive_count=0,
            years_total_count=0,
        )

    t = trade_log.sort("exit_time")
    pnls = t["net_pnl"].to_list()
    net_total = float(sum(pnls))

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    flat = sum(1 for p in pnls if p == 0)

    gprofit = float(sum(wins)) if wins else 0.0
    gloss = float(sum(losses)) if losses else 0.0
    if gloss < 0:
        pf = gprofit / abs(gloss)
    elif gprofit > 0:
        pf = float("inf")
    else:
        pf = 0.0

    n = len(pnls)
    wr = len(wins) / n if n else 0.0

    cum: list[float] = []
    s = 0.0
    for p in pnls:
        s += p
        cum.append(s)
    max_dd = _max_drawdown_cumulative(cum)

    ext = t.select(
        pl.col("exit_time")
        .dt.convert_time_zone(exit_year_tz)
        .dt.year()
        .alias("y"),
        pl.col("net_pnl"),
    )
    by_year = ext.group_by("y").agg(pl.col("net_pnl").sum().alias("pnl"))
    yd = {int(r["y"]): float(r["pnl"]) for r in by_year.iter_rows(named=True)}
    pos_years = sum(1 for v in yd.values() if v > 0)

    return M6AggregateResult(
        trade_count=n,
        net_pnl_total=net_total,
        gross_profit_sum=gprofit,
        gross_loss_sum=gloss,
        win_count=len(wins),
        loss_count=len(losses),
        breakeven_count=flat,
        win_rate=wr,
        avg_win=float(sum(wins) / len(wins)) if wins else 0.0,
        avg_loss=float(sum(losses) / len(losses)) if losses else 0.0,
        profit_factor=999999.0 if pf == float("inf") else float(pf),
        max_drawdown=max_dd,
        years_calendar=yd,
        years_positive_count=pos_years,
        years_total_count=len(yd),
    )


def protocol_year_fraction(start: date, end: date) -> float:
    """Inclusive calendar endpoints → year fraction (simple average-year convention)."""
    days = (end - start).days + 1
    return days / 365.25
