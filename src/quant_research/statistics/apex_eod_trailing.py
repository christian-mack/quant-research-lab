"""Apex-style EOD trailing drawdown simulation on a daily P&L series.

Implements two trailing-floor conventions for research comparison:

- **pure_trailing:** ``allowed_min = high_water_equity - trail`` after each day.
- **funded_lock:** when ``high_water_equity`` first reaches ``start_balance +
  lock_profit``, set ``locked_floor = high_water_at_lock - trail``; thereafter
  ``allowed_min = locked_floor`` (floor does not rise with later equity highs).

DLL is reported separately; by default it does not censor the equity path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

TrailingMode = Literal["pure_trailing", "funded_lock"]


@dataclass(frozen=True, slots=True)
class EodTrailingSimResult:
    """Summary statistics after walking a daily net P&L series."""

    starting_balance: float
    final_equity: float
    max_peak_to_trough_dd: float
    max_floor_violation: float
    min_margin_to_floor: float
    breach_session_count: int
    dll_hit_session_count: int
    binding_session_index: int
    n_sessions: int


def simulate_apex_eod_trailing(
    daily_pnls: np.ndarray,
    *,
    starting_balance: float = 50_000.0,
    trail: float = 3_000.0,
    lock_profit: float = 100.0,
    dll_limit: float = 1_000.0,
    mode: TrailingMode = "pure_trailing",
    dll_alters_path: bool = False,
) -> EodTrailingSimResult:
    """
    Walk session-close P&Ls; update equity and trailing / locked floor rules.

    Parameters
    ----------
    daily_pnls
        1-D array of realized net P&L **per session** (already scaled for qty).
    dll_limit
        Flag sessions with P&L below ``-dll_limit``; optionally zero that day's
        contribution when ``dll_alters_path`` is True (not used for Wave 0b).
    """
    pnl = np.asarray(daily_pnls, dtype=np.float64).ravel()
    equity = float(starting_balance)
    hwm = float(starting_balance)
    locked_floor: float | None = None

    peak_eq = float(starting_balance)
    max_pt_dd = 0.0
    max_pt_dd_i = 0
    max_violation = 0.0
    min_margin = float("inf")
    breaches = 0
    dll_hits = 0
    bind_i = 0

    n = int(pnl.size)
    for i in range(n):
        d = float(pnl[i])
        if dll_alters_path and d < -dll_limit:
            d = max(d, -dll_limit)
        if d < -dll_limit:
            dll_hits += 1

        equity += d

        if equity > hwm:
            hwm = equity

        if mode == "funded_lock" and locked_floor is None and hwm >= starting_balance + lock_profit:
            locked_floor = hwm - trail

        if mode == "funded_lock" and locked_floor is not None:
            allowed_min = locked_floor
        else:
            allowed_min = hwm - trail

        margin = equity - allowed_min
        min_margin = min(min_margin, margin)
        viol = allowed_min - equity
        if viol > max_violation:
            max_violation = viol
            bind_i = i
        if equity < allowed_min:
            breaches += 1

        if equity > peak_eq:
            peak_eq = equity
        pt_dd = peak_eq - equity
        if pt_dd > max_pt_dd:
            max_pt_dd = pt_dd
            max_pt_dd_i = i

    if max_violation <= 0.0:
        bind_i = max_pt_dd_i

    return EodTrailingSimResult(
        starting_balance=starting_balance,
        final_equity=equity,
        max_peak_to_trough_dd=max_pt_dd,
        max_floor_violation=max_violation,
        min_margin_to_floor=min_margin,
        breach_session_count=breaches,
        dll_hit_session_count=dll_hits,
        binding_session_index=bind_i,
        n_sessions=n,
    )


def max_drawdown_closed_trade_pnl(pnls: np.ndarray) -> float:
    """Return max drawdown (negative depth) on cumulative trade P&L from zero."""
    if pnls.size == 0:
        return 0.0
    equity = np.concatenate([[0.0], np.cumsum(pnls.astype(np.float64))])
    peaks = np.maximum.accumulate(equity)
    return float(np.min(equity - peaks))


def trades_to_daily_pnls_chronological(
    exit_session_dates: list[object],
    net_pnls: np.ndarray,
) -> tuple[list[object], np.ndarray]:
    """
    Sum ``net_pnls`` by ``exit_cme_session_date``; order days chronologically.

    ``exit_session_date`` values must be orderable (e.g. Polars dates).
    """
    if len(exit_session_dates) != len(net_pnls):
        msg = "exit_session_dates length must match net_pnls"
        raise ValueError(msg)
    day_to_sum: dict[object, float] = {}
    for d, p in zip(exit_session_dates, net_pnls, strict=True):
        day_to_sum[d] = day_to_sum.get(d, 0.0) + float(p)
    uniq = sorted(day_to_sum.keys(), key=lambda x: x)  # type: ignore[arg-type, return-value]
    ordered_pnls = np.array([day_to_sum[d] for d in uniq], dtype=np.float64)
    return uniq, ordered_pnls


def collapse_trades_to_session_streaks(
    exit_session_dates: list[object],
    net_pnls: list[float] | np.ndarray,
) -> tuple[list[object], np.ndarray]:
    """
    Consecutive trades with the same session date merge into one daily total.

    Preserves **time order** of the trade list (required for block-bootstrap paths).
    """
    if len(exit_session_dates) == 0:
        return [], np.array([], dtype=np.float64)
    dates: list[object] = []
    totals: list[float] = []
    cur_d = exit_session_dates[0]
    acc = 0.0
    pnl_arr = np.asarray(net_pnls, dtype=np.float64).ravel()
    for d, p in zip(exit_session_dates, pnl_arr, strict=True):
        if d != cur_d:
            dates.append(cur_d)
            totals.append(acc)
            cur_d = d
            acc = 0.0
        acc += float(p)
    dates.append(cur_d)
    totals.append(acc)
    return dates, np.array(totals, dtype=np.float64)


def block_bootstrap_resample_trades(
    trades_pnl: np.ndarray,
    trade_dates: list[object],
    *,
    block_len: int,
    n_target_trades: int,
    n_iterations: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Non-overlapping blocks of ``block_len`` (last block may be shorter);

    resample blocks with replacement and concatenate until at least
    ``n_target_trades`` rows; truncate to exactly ``n_target_trades``.

    Returns
    -------
    closed_trade_max_dd
        Per replicate: abs(max drawdown depth) on the cumulative **trade** path.
    eod_peak_trough_max_dd
        Same path collapsed to session streaks, then **funded_lock** EOD sim
        peak-to-trough drawdown on equity (equals cum-P&L drawdown vs start).
    """
    n = int(trades_pnl.size)
    if n != len(trade_dates):
        msg = "trades_pnl and trade_dates length mismatch"
        raise ValueError(msg)
    if block_len < 1:
        msg = "block_len must be >= 1"
        raise ValueError(msg)
    if n_target_trades < 1:
        msg = "n_target_trades must be >= 1"
        raise ValueError(msg)

    blocks_pnl: list[np.ndarray] = []
    blocks_dates: list[list[object]] = []
    for start in range(0, n, block_len):
        sl = slice(start, min(start + block_len, n))
        blocks_pnl.append(trades_pnl[sl].copy())
        blocks_dates.append(list(trade_dates[sl]))

    n_blocks = len(blocks_pnl)
    closed_dds = np.empty(n_iterations, dtype=np.float64)
    eod_dds = np.empty(n_iterations, dtype=np.float64)

    for it in range(n_iterations):
        buf_pnl: list[float] = []
        buf_d: list[object] = []
        while len(buf_pnl) < n_target_trades:
            j = int(rng.integers(0, n_blocks))
            buf_pnl.extend(float(p) for p in blocks_pnl[j].tolist())
            buf_d.extend(blocks_dates[j])
        buf_pnl = buf_pnl[:n_target_trades]
        buf_d = buf_d[:n_target_trades]

        arr = np.array(buf_pnl, dtype=np.float64)
        closed_dds[it] = abs(max_drawdown_closed_trade_pnl(arr))

        _, daily = collapse_trades_to_session_streaks(buf_d, arr)
        sim = simulate_apex_eod_trailing(
            daily,
            mode="funded_lock",
        )
        eod_dds[it] = sim.max_peak_to_trough_dd

    return closed_dds, eod_dds
