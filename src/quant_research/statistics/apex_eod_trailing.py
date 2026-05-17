"""Apex-style EOD simulation helpers for research.

**Canonical multi-class EOD (Wave 0d+):** :func:`simulate_apex_eod_two_phase` and
:func:`simulate_eval_window_eod` — configurable start, trail, lock at **HWM ≥
start + trailing_dd**, static floor = **starting balance** post-lock, **DLL** as
**session/day pause** (no account death).

**Shorthand $50K:** :func:`simulate_apex_50k_eod_two_phase` /
:func:`simulate_eval_window_50k_eod` wrap the generalized API.

**Legacy DLL (testing only):** Pass ``dll_terminates_run=True`` to approximate the
pre–Wave 0d bug where any DLL day failed the whole run.

**Legacy Wave 0b:** :func:`simulate_apex_eod_trailing` (**$3K** trail / start **+$100**
lock) — historical notebooks only.

DLL pause rule (EOD accounts): per [Apex Help Center](https://apextraderfunding.com/help-center/)
and project ``docs/ai-project-instructions.md``, hitting the daily loss limit **pauses
trading for the remainder of the session**; the account **continues** the next session.

Per **America/New_York** calendar day, cumulative realized P&amp;L on filled closes:
when a new fill would push that cumulative **strictly below** ``-dll_limit``, we apply
that fill (snapshot equity at breach), then **ignore** further same-day P&amp;L for
equity and for the running day accumulator until the next NY day.

Result field ``dll_failure_days`` counts **distinct NY days** on which a pause triggered
(legacy name retained for API stability). ``dll_fail`` is **False** when
``dll_terminates_run`` is **False**; when **True**, ``dll_fail`` mirrors the old
terminal semantics.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

import numpy as np

TrailingMode = Literal["pure_trailing", "funded_lock"]


@dataclass(frozen=True, slots=True)
class EodTrailingSimResult:
    """Summary statistics after walking a daily net P&L series (legacy modes)."""

    starting_balance: float
    final_equity: float
    max_peak_to_trough_dd: float
    max_floor_violation: float
    min_margin_to_floor: float
    breach_session_count: int
    dll_hit_session_count: int
    binding_session_index: int
    n_sessions: int


@dataclass(frozen=True, slots=True)
class ApexEodTwoPhaseSimResult:
    """Result of :func:`simulate_apex_eod_two_phase` (pre-lock + post-lock + DLL pause)."""

    starting_balance: float
    final_equity: float
    survived: bool
    trail_breach_sessions: int
    dll_fail: bool
    dll_failure_days: int
    locked_achieved: bool
    min_margin_pre_lock: float
    min_margin_post_lock: float
    max_peak_to_trough_dd: float
    binding_session_index: int
    n_sessions: int


# Backward-compatible alias
Apex50kEodSimResult = ApexEodTwoPhaseSimResult


def simulate_apex_eod_two_phase(
    session_pnls: np.ndarray,
    ny_calendar_dates: list[dt.date],
    *,
    starting_balance: float,
    trailing_dd: float,
    dll_limit: float,
    lock_equity_threshold: float | None = None,
    post_lock_floor: float | None = None,
    enforce_dll: bool = True,
    dll_terminates_run: bool = False,
) -> ApexEodTwoPhaseSimResult:
    """
    Walk **session-close** scaled P&amp;L with Apex-style two-phase floor rules.

    **Pre-lock:** ``allowed_min = high_water_equity - trailing_dd`` (initially
    ``starting_balance - trailing_dd``).

    **Lock:** when ``high_water_equity >= lock_equity_threshold`` (default
    ``starting_balance + trailing_dd``), use **post-lock**
    ``allowed_min = post_lock_floor`` (default ``starting_balance``) permanently.

    **DLL (default):** same-day cumulative P&amp;L; first cross strictly below
    ``-dll_limit`` pauses further same-day application; counts toward
    ``dll_failure_days``; **does not** set ``survived`` false.

    **Legacy:** ``dll_terminates_run=True`` reproduces pre–Wave 0d behavior
    (any DLL day fails the run).
    """
    pnl = np.asarray(session_pnls, dtype=np.float64).ravel()
    n = int(pnl.size)
    if len(ny_calendar_dates) != n:
        msg = "ny_calendar_dates must match session_pnls length"
        raise ValueError(msg)

    lock_at = (
        float(lock_equity_threshold)
        if lock_equity_threshold is not None
        else float(starting_balance) + float(trailing_dd)
    )
    floor_after = (
        float(post_lock_floor)
        if post_lock_floor is not None
        else float(starting_balance)
    )
    trail = float(trailing_dd)

    equity = float(starting_balance)
    hwm = float(starting_balance)
    locked = False

    peak_eq = float(starting_balance)
    max_pt_dd = 0.0
    max_pt_dd_i = 0

    min_pre = float("inf")
    min_post = float("inf")
    max_violation = 0.0
    bind_i = 0

    trail_breaches = 0
    dll_fail = False
    dll_day_hits = 0

    current_day: dt.date | None = None
    day_accum = 0.0
    day_dll_paused = False
    dll_hit_counted_for_day = False

    for i in range(n):
        d_ny = ny_calendar_dates[i]
        s_pnl = float(pnl[i])

        if current_day is None:
            current_day = d_ny
            day_accum = 0.0
            day_dll_paused = False
            dll_hit_counted_for_day = False
        elif d_ny != current_day:
            if dll_terminates_run and enforce_dll and day_accum < -dll_limit:
                dll_fail = True
                dll_day_hits += 1
            current_day = d_ny
            day_accum = 0.0
            day_dll_paused = False
            dll_hit_counted_for_day = False

        if dll_terminates_run or not enforce_dll:
            day_accum += s_pnl
            equity += s_pnl
        elif day_dll_paused:
            pass
        else:
            cand = day_accum + s_pnl
            if cand < -dll_limit:
                day_accum = cand
                equity += s_pnl
                if not dll_hit_counted_for_day:
                    dll_day_hits += 1
                    dll_hit_counted_for_day = True
                day_dll_paused = True
            else:
                day_accum = cand
                equity += s_pnl

        if equity > hwm:
            hwm = equity
        if not locked and hwm >= lock_at:
            locked = True

        if locked:
            allowed_min = floor_after
            min_post = min(min_post, equity - floor_after)
        else:
            allowed_min = hwm - trail
            min_pre = min(min_pre, equity - allowed_min)

        viol = allowed_min - equity
        if viol > max_violation:
            max_violation = viol
            bind_i = i
        if equity < allowed_min:
            trail_breaches += 1

        if equity > peak_eq:
            peak_eq = equity
        pt_dd = peak_eq - equity
        if pt_dd > max_pt_dd:
            max_pt_dd = pt_dd
            max_pt_dd_i = i

    if (
        current_day is not None
        and dll_terminates_run
        and enforce_dll
        and day_accum < -dll_limit
    ):
        dll_fail = True
        dll_day_hits += 1

    if max_violation <= 0.0:
        bind_i = max_pt_dd_i

    trail_fail = trail_breaches > 0
    if dll_terminates_run and enforce_dll:
        survived = not trail_fail and not dll_fail
        out_dll_fail = bool(dll_fail)
    else:
        survived = not trail_fail
        out_dll_fail = False

    if not np.isfinite(min_pre):
        min_pre = float("nan")
    if not locked or not np.isfinite(min_post):
        min_post = float("nan") if not locked else min_post

    return ApexEodTwoPhaseSimResult(
        starting_balance=float(starting_balance),
        final_equity=equity,
        survived=bool(survived),
        trail_breach_sessions=int(trail_breaches),
        dll_fail=out_dll_fail,
        dll_failure_days=int(dll_day_hits),
        locked_achieved=bool(locked),
        min_margin_pre_lock=float(min_pre) if np.isfinite(min_pre) else float("nan"),
        min_margin_post_lock=float(min_post) if locked and np.isfinite(min_post) else float("nan"),
        max_peak_to_trough_dd=max_pt_dd,
        binding_session_index=int(bind_i),
        n_sessions=n,
    )


def simulate_apex_50k_eod_two_phase(
    session_pnls: np.ndarray,
    ny_calendar_dates: list[dt.date],
    *,
    starting_balance: float = 50_000.0,
    trail: float = 2_000.0,
    lock_equity_threshold: float = 52_000.0,
    post_lock_floor: float = 50_000.0,
    dll_limit: float = 1_000.0,
    enforce_dll: bool = True,
    dll_terminates_run: bool = False,
) -> ApexEodTwoPhaseSimResult:
    """$50K EOD shorthand; **trail** is pre-lock trailing drawdown in dollars."""
    return simulate_apex_eod_two_phase(
        session_pnls,
        ny_calendar_dates,
        starting_balance=starting_balance,
        trailing_dd=trail,
        dll_limit=dll_limit,
        lock_equity_threshold=lock_equity_threshold,
        post_lock_floor=post_lock_floor,
        enforce_dll=enforce_dll,
        dll_terminates_run=dll_terminates_run,
    )


def simulate_eval_window_eod(
    pnls_scaled: np.ndarray,
    exit_ny_dates: list[dt.date],
    exit_session_dates: list[object],
    *,
    starting_balance: float,
    trailing_dd: float,
    profit_target: float,
    dll_limit: float,
    lock_equity_threshold: float | None = None,
    post_lock_floor: float | None = None,
    dll_terminates_run: bool = False,
) -> dict[str, object]:
    """
    Eval-style window: **trade-by-trade** path; pass if equity reaches
    ``starting_balance + profit_target`` before trailing breach.

    **DLL:** default = pause remainder of NY day; does **not** fail the window.
    With ``dll_terminates_run=True``, DLL fails the window (legacy).
    """
    lock_at = (
        float(lock_equity_threshold)
        if lock_equity_threshold is not None
        else float(starting_balance) + float(trailing_dd)
    )
    floor_after = (
        float(post_lock_floor)
        if post_lock_floor is not None
        else float(starting_balance)
    )
    pt_equity = float(starting_balance) + float(profit_target)
    trail = float(trailing_dd)

    cum = 0.0
    equity = float(starting_balance)
    hwm = float(starting_balance)
    locked = False
    trail_margin_min = float("inf")
    current_day: dt.date | None = None
    day_accum = 0.0
    day_dll_paused = False

    lock_triggered = False

    for i, pnl in enumerate(pnls_scaled):
        d = exit_ny_dates[i]

        if current_day is None:
            current_day = d
            day_accum = 0.0
            day_dll_paused = False
        elif d != current_day:
            if dll_terminates_run and day_accum < -dll_limit:
                return {
                    "outcome": "fail",
                    "mode": "dll",
                    "fail_index": i,
                    "final_cum": cum,
                    "trail_margin_min": trail_margin_min,
                    "locked": lock_triggered,
                }
            current_day = d
            day_accum = 0.0
            day_dll_paused = False

        p = float(pnl)
        if dll_terminates_run:
            day_accum += p
            cum += p
        elif day_dll_paused:
            pass
        else:
            cand = day_accum + p
            if cand < -dll_limit:
                day_accum = cand
                cum += p
                day_dll_paused = True
            else:
                day_accum = cand
                cum += p

        equity = float(starting_balance) + cum

        if equity > hwm:
            hwm = equity
        if not locked and hwm >= lock_at:
            locked = True
            lock_triggered = True

        allowed_min = floor_after if locked else hwm - trail

        margin = equity - allowed_min
        trail_margin_min = min(trail_margin_min, margin)
        if equity < allowed_min:
            return {
                "outcome": "fail",
                "mode": "trailing_dd",
                "fail_index": i,
                "final_cum": cum,
                "trail_margin_min": trail_margin_min,
                "locked": lock_triggered,
            }

        if equity >= pt_equity:
            cross_i = i
            ny_to_pass = len({exit_ny_dates[j] for j in range(cross_i + 1)})
            sess_to_pass = len(
                {exit_session_dates[j] for j in range(cross_i + 1) if exit_session_dates[j]},
            )
            return {
                "outcome": "pass",
                "mode": None,
                "cross_index": cross_i,
                "days_to_pass": ny_to_pass,
                "sessions_to_pass": sess_to_pass,
                "final_cum": cum,
                "trail_margin_min": trail_margin_min,
                "locked": lock_triggered,
            }

    if dll_terminates_run and day_accum < -dll_limit:
        return {
            "outcome": "fail",
            "mode": "dll",
            "fail_index": len(pnls_scaled) - 1 if pnls_scaled.size else 0,
            "final_cum": cum,
            "trail_margin_min": trail_margin_min,
            "locked": lock_triggered,
        }

    return {
        "outcome": "fail",
        "mode": "no_target",
        "fail_index": None,
        "final_cum": cum,
        "trail_margin_min": trail_margin_min,
        "locked": lock_triggered,
    }


def simulate_eval_window_50k_eod(
    pnls_scaled: np.ndarray,
    exit_ny_dates: list[dt.date],
    exit_session_dates: list[object],
    *,
    starting_balance: float = 50_000.0,
    trail: float = 2_000.0,
    lock_equity_threshold: float = 52_000.0,
    post_lock_floor: float = 50_000.0,
    profit_target_equity: float = 53_000.0,
    dll_limit: float = 1_000.0,
    dll_terminates_run: bool = False,
) -> dict[str, object]:
    """$50K EOD eval shorthand; **profit_target_equity** overrides ``profit_target`` dollars."""
    pt = float(profit_target_equity) - float(starting_balance)
    return simulate_eval_window_eod(
        pnls_scaled,
        exit_ny_dates,
        exit_session_dates,
        starting_balance=starting_balance,
        trailing_dd=trail,
        profit_target=pt,
        dll_limit=dll_limit,
        lock_equity_threshold=lock_equity_threshold,
        post_lock_floor=post_lock_floor,
        dll_terminates_run=dll_terminates_run,
    )


def trades_to_daily_pnls_with_ny(
    exit_session_dates: list[object],
    exit_ny_dates: list[dt.date],
    net_pnls: np.ndarray,
) -> tuple[list[object], np.ndarray, list[dt.date]]:
    """Aggregate to **chronologically ordered** session dates with NY date per row."""
    if not (len(exit_session_dates) == len(exit_ny_dates) == len(net_pnls)):
        msg = "exit_session_dates, exit_ny_dates, net_pnls must match"
        raise ValueError(msg)
    day_to_sum: dict[object, float] = {}
    day_to_ny: dict[object, dt.date] = {}
    for d_sess, d_ny, p in zip(
        exit_session_dates, exit_ny_dates, net_pnls, strict=True
    ):
        day_to_sum[d_sess] = day_to_sum.get(d_sess, 0.0) + float(p)
        day_to_ny[d_sess] = d_ny
    uniq = sorted(day_to_sum.keys(), key=lambda x: x)  # type: ignore[arg-type, return-value]
    ordered_pnl = np.array([day_to_sum[d] for d in uniq], dtype=np.float64)
    ordered_ny = [day_to_ny[d] for d in uniq]
    return uniq, ordered_pnl, ordered_ny


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
    """Legacy Wave 0b trailing modes (**$3K** trail / start **+$100** lock)."""
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


def collapse_trades_with_ny_to_session_streaks(
    exit_session_dates: list[object],
    exit_ny_dates: list[dt.date],
    net_pnls: list[float] | np.ndarray,
) -> tuple[list[object], np.ndarray, list[dt.date]]:
    """Like :func:`collapse_trades_to_session_streaks` but carry last NY date per session streak."""
    if len(exit_session_dates) == 0:
        return [], np.array([], dtype=np.float64), []
    dates: list[object] = []
    totals: list[float] = []
    ny_out: list[dt.date] = []
    cur_d = exit_session_dates[0]
    acc = 0.0
    last_ny = exit_ny_dates[0]
    pnl_arr = np.asarray(net_pnls, dtype=np.float64).ravel()
    for d, ny, p in zip(exit_session_dates, exit_ny_dates, pnl_arr, strict=True):
        if d != cur_d:
            dates.append(cur_d)
            totals.append(acc)
            ny_out.append(last_ny)
            cur_d = d
            acc = 0.0
        acc += float(p)
        last_ny = ny
    dates.append(cur_d)
    totals.append(acc)
    ny_out.append(last_ny)
    return dates, np.array(totals, dtype=np.float64), ny_out


def block_bootstrap_apex_eod_funded(
    trades_pnl: np.ndarray,
    trade_dates: list[object],
    trade_ny_dates: list[dt.date],
    *,
    quantity: float,
    block_len: int,
    n_target_trades: int,
    n_iterations: int,
    rng: np.random.Generator,
    starting_balance: float = 50_000.0,
    trailing_dd: float = 2_000.0,
    dll_limit: float = 1_000.0,
    lock_equity_threshold: float | None = None,
    post_lock_floor: float | None = None,
    enforce_dll: bool = True,
    dll_terminates_run: bool = False,
) -> dict[str, np.ndarray]:
    """
    Block-bootstrap trade rows, collapse to session streaks, scale P&amp;L, run
    :func:`simulate_apex_eod_two_phase`.
    """
    n = int(trades_pnl.size)
    if n != len(trade_dates) or n != len(trade_ny_dates):
        msg = "trades_pnl, trade_dates, trade_ny_dates length mismatch"
        raise ValueError(msg)
    if block_len < 1 or n_target_trades < 1:
        msg = "block_len and n_target_trades must be >= 1"
        raise ValueError(msg)

    blocks_pnl: list[np.ndarray] = []
    blocks_dates: list[list[object]] = []
    blocks_ny: list[list[dt.date]] = []
    for start in range(0, n, block_len):
        sl = slice(start, min(start + block_len, n))
        blocks_pnl.append(trades_pnl[sl].copy())
        blocks_dates.append(list(trade_dates[sl]))
        blocks_ny.append(list(trade_ny_dates[sl]))

    n_blocks = len(blocks_pnl)
    survived = np.empty(n_iterations, dtype=bool)
    min_pre = np.empty(n_iterations, dtype=np.float64)
    min_post = np.empty(n_iterations, dtype=np.float64)
    locked_achieved = np.empty(n_iterations, dtype=bool)

    for it in range(n_iterations):
        buf_pnl: list[float] = []
        buf_d: list[object] = []
        buf_ny: list[dt.date] = []
        while len(buf_pnl) < n_target_trades:
            j = int(rng.integers(0, n_blocks))
            buf_pnl.extend(float(p) * quantity for p in blocks_pnl[j].tolist())
            buf_d.extend(blocks_dates[j])
            buf_ny.extend(blocks_ny[j])
        buf_pnl = buf_pnl[:n_target_trades]
        buf_d = buf_d[:n_target_trades]
        buf_ny = buf_ny[:n_target_trades]

        arr = np.array(buf_pnl, dtype=np.float64)
        _, daily, dny = collapse_trades_with_ny_to_session_streaks(buf_d, buf_ny, arr)
        r = simulate_apex_eod_two_phase(
            daily,
            dny,
            starting_balance=starting_balance,
            trailing_dd=trailing_dd,
            dll_limit=dll_limit,
            lock_equity_threshold=lock_equity_threshold,
            post_lock_floor=post_lock_floor,
            enforce_dll=enforce_dll,
            dll_terminates_run=dll_terminates_run,
        )
        survived[it] = r.survived
        min_pre[it] = r.min_margin_pre_lock
        min_post[it] = r.min_margin_post_lock
        locked_achieved[it] = r.locked_achieved

    return {
        "survived": survived,
        "min_margin_pre_lock": min_pre,
        "min_margin_post_lock": min_post,
        "locked_achieved": locked_achieved,
    }


def block_bootstrap_apex_50k_funded(
    trades_pnl: np.ndarray,
    trade_dates: list[object],
    trade_ny_dates: list[dt.date],
    *,
    quantity: float,
    block_len: int,
    n_target_trades: int,
    n_iterations: int,
    rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """$50K EOD shorthand for :func:`block_bootstrap_apex_eod_funded`."""
    return block_bootstrap_apex_eod_funded(
        trades_pnl,
        trade_dates,
        trade_ny_dates,
        quantity=quantity,
        block_len=block_len,
        n_target_trades=n_target_trades,
        n_iterations=n_iterations,
        rng=rng,
        starting_balance=50_000.0,
        trailing_dd=2_000.0,
        dll_limit=1_000.0,
        lock_equity_threshold=52_000.0,
        post_lock_floor=50_000.0,
        enforce_dll=True,
        dll_terminates_run=False,
    )


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
        Same path collapsed to session streaks, then **legacy funded_lock** EOD sim
        peak-to-trough drawdown on equity (Wave 0b convention).
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
