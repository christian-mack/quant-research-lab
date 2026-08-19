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
import math
from collections.abc import Callable
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
class ApexBalanceTier:
    """PA balance band: **max_contracts_mini** caps mini size (1 mini = 10 MNQ)."""

    min_balance: float
    max_balance: float
    max_contracts_mini: int
    dll_limit: float


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
    tier_summary: dict[str, object] | None = None


# Backward-compatible alias
Apex50kEodSimResult = ApexEodTwoPhaseSimResult


def apex_tier_index_for_equity(
    equity: float,
    tiers: tuple[ApexBalanceTier, ...],
) -> tuple[int, ApexBalanceTier]:
    """Return tier index and row for **prior EOD** equity before a session opens.

    Tiers are **sorted by** ``min_balance``. If equity sits **below** the
    published bottom band (stress path before trailing breach is recorded), use
    the **lowest** tier — same caps/DLL as the bottom band (conservative).
    If equity falls in a **gap** between adjacent published bands, use the
    **lower** band until equity reaches the next ``min_balance``.
    """
    if not tiers:
        msg = "balance_tiers must be non-empty"
        raise ValueError(msg)
    ts = tuple(sorted(tiers, key=lambda t: t.min_balance))
    e = float(equity)
    bottom = ts[0]
    if e < bottom.min_balance:
        return 0, bottom
    last_i = len(ts) - 1
    for i, t in enumerate(ts):
        if t.min_balance <= e <= t.max_balance:
            return i, t
    for i in range(last_i):
        lo, hi = ts[i], ts[i + 1]
        if lo.max_balance < e < hi.min_balance:
            return i, lo
    top = ts[last_i]
    if e > top.max_balance and math.isfinite(top.max_balance):
        return last_i, top
    msg = f"equity {equity} outside tier table"
    raise ValueError(msg)


def effective_mnq_qty(
    target_qty_mnq: float,
    tier: ApexBalanceTier,
    *,
    mnq_per_mini: float,
) -> float:
    cap = float(tier.max_contracts_mini) * float(mnq_per_mini)
    return float(min(float(target_qty_mnq), cap))


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
    balance_tiers: tuple[ApexBalanceTier, ...] | None = None,
    target_qty_mnq: float | None = None,
    mnq_per_mini: float = 10.0,
) -> ApexEodTwoPhaseSimResult:
    """
    Walk **session-close** P&amp;L with Apex-style two-phase floor rules.

    **Flat mode (default):** ``session_pnls`` are **already scaled** dollars; use
    ``dll_limit`` constant; ``balance_tiers`` and ``target_qty_mnq`` must be **None**.

    **Tiered PA mode (Wave 0e+):** pass ``balance_tiers`` and ``target_qty_mnq``.
    Then ``session_pnls`` are **per 1 MNQ**; each session applies
    ``pnl[i] * effective_mnq`` where ``effective_mnq = min(target_qty_mnq,
    tier.max_contracts_mini * mnq_per_mini)``. Tier and DLL are fixed at **session
    open** from **prior** session EOD equity (session **0** uses ``starting_balance``).
    Same **NY calendar day** uses the DLL limit from the **first** session row of
    that day (tier at that row's open). For **per-session diagnostic rows**, use
    :func:`simulate_apex_eod_two_phase_tiered_with_trace`.

    **Pre-lock:** ``allowed_min = HWM - trailing_dd``. **Post-lock:** static floor.
    **DLL:** session pause (unless ``dll_terminates_run``).
    """
    if balance_tiers is not None and target_qty_mnq is not None:
        return _simulate_apex_eod_two_phase_tiered(
            session_pnls,
            ny_calendar_dates,
            starting_balance=starting_balance,
            trailing_dd=trailing_dd,
            lock_equity_threshold=lock_equity_threshold,
            post_lock_floor=post_lock_floor,
            enforce_dll=enforce_dll,
            dll_terminates_run=dll_terminates_run,
            balance_tiers=balance_tiers,
            target_qty_mnq=float(target_qty_mnq),
            mnq_per_mini=float(mnq_per_mini),
        )

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
    floor_after = float(post_lock_floor) if post_lock_floor is not None else float(starting_balance)
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

    if current_day is not None and dll_terminates_run and enforce_dll and day_accum < -dll_limit:
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
        tier_summary=None,
    )


def _simulate_apex_eod_two_phase_tiered(
    session_pnls_per_mnq: np.ndarray,
    ny_calendar_dates: list[dt.date],
    *,
    starting_balance: float,
    trailing_dd: float,
    lock_equity_threshold: float | None,
    post_lock_floor: float | None,
    enforce_dll: bool,
    dll_terminates_run: bool,
    balance_tiers: tuple[ApexBalanceTier, ...],
    target_qty_mnq: float,
    mnq_per_mini: float,
    session_trace_out: list[dict[str, object]] | None = None,
) -> ApexEodTwoPhaseSimResult:
    tiers = tuple(sorted(balance_tiers, key=lambda t: t.min_balance))
    pnl1 = np.asarray(session_pnls_per_mnq, dtype=np.float64).ravel()
    n = int(pnl1.size)
    if len(ny_calendar_dates) != n:
        msg = "ny_calendar_dates must match session_pnls length"
        raise ValueError(msg)

    lock_at = (
        float(lock_equity_threshold)
        if lock_equity_threshold is not None
        else float(starting_balance) + float(trailing_dd)
    )
    floor_after = float(post_lock_floor) if post_lock_floor is not None else float(starting_balance)
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
    day_fixed_dll: float | None = None

    n_tiers = len(tiers)
    sessions_per_tier = [0] * n_tiers
    dll_pause_days_per_tier = [0] * n_tiers
    transitions: list[dict[str, object]] = []
    prev_tier_idx: int | None = None
    pre_lock_sessions = 0
    post_lock_sessions = 0

    tier_idx_for_dll_charge: int = 0

    for i in range(n):
        d_ny = ny_calendar_dates[i]
        eod_prior = equity
        locked_open = locked
        hwm_open = hwm
        allowed_min_open = floor_after if locked_open else hwm_open - trail
        margin_open = eod_prior - allowed_min_open

        t_idx, tier_open = apex_tier_index_for_equity(eod_prior, tiers)
        eff = effective_mnq_qty(target_qty_mnq, tier_open, mnq_per_mini=mnq_per_mini)
        session_dll = float(tier_open.dll_limit)
        s_pnl = float(pnl1[i]) * eff
        dll_new_pause = False

        if current_day is None:
            current_day = d_ny
            day_accum = 0.0
            day_dll_paused = False
            dll_hit_counted_for_day = False
            day_fixed_dll = session_dll
            tier_idx_for_dll_charge = t_idx
        elif d_ny != current_day:
            if (
                dll_terminates_run
                and enforce_dll
                and day_fixed_dll is not None
                and day_accum < -day_fixed_dll
            ):
                dll_fail = True
                dll_day_hits += 1
            current_day = d_ny
            day_accum = 0.0
            day_dll_paused = False
            dll_hit_counted_for_day = False
            day_fixed_dll = session_dll
            tier_idx_for_dll_charge = t_idx

        if prev_tier_idx is None:
            prev_tier_idx = t_idx
        elif t_idx != prev_tier_idx:
            transitions.append(
                {
                    "session_index": i,
                    "from_tier": prev_tier_idx,
                    "to_tier": t_idx,
                    "direction": "up" if t_idx > prev_tier_idx else "down",
                    "equity_before_session": eod_prior,
                },
            )
            prev_tier_idx = t_idx

        sessions_per_tier[t_idx] += 1

        dll_lim_row = day_fixed_dll if day_fixed_dll is not None else session_dll

        if dll_terminates_run or not enforce_dll:
            day_accum += s_pnl
            equity += s_pnl
        elif day_dll_paused:
            pass
        else:
            cand = day_accum + s_pnl
            if cand < -dll_lim_row:
                day_accum = cand
                equity += s_pnl
                if not dll_hit_counted_for_day:
                    dll_day_hits += 1
                    dll_pause_days_per_tier[tier_idx_for_dll_charge] += 1
                    dll_hit_counted_for_day = True
                    dll_new_pause = True
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
            post_lock_sessions += 1
        else:
            allowed_min = hwm - trail
            min_pre = min(min_pre, equity - allowed_min)
            pre_lock_sessions += 1

        viol = allowed_min - equity
        if viol > max_violation:
            max_violation = viol
            bind_i = i
        breach_close = equity < allowed_min
        if breach_close:
            trail_breaches += 1

        if equity > peak_eq:
            peak_eq = equity
        pt_dd = peak_eq - equity
        if pt_dd > max_pt_dd:
            max_pt_dd = pt_dd
            max_pt_dd_i = i

        if session_trace_out is not None:
            margin_close = equity - allowed_min
            session_trace_out.append(
                {
                    "session_index": i,
                    "ny_date": d_ny,
                    "tier_index_open": t_idx,
                    "effective_mnq": eff,
                    "session_dll_limit": session_dll,
                    "session_pnl": float(s_pnl),
                    "equity_open": float(eod_prior),
                    "equity_close": float(equity),
                    "locked_open": bool(locked_open),
                    "locked_close": bool(locked),
                    "allowed_min_open": float(allowed_min_open),
                    "allowed_min_close": float(allowed_min),
                    "margin_to_floor_open": float(margin_open),
                    "margin_to_floor_close": float(margin_close),
                    "trail_breach_after_session": bool(breach_close),
                    "dll_new_pause_this_session": bool(dll_new_pause),
                },
            )

    if (
        current_day is not None
        and dll_terminates_run
        and enforce_dll
        and day_fixed_dll is not None
        and day_accum < -day_fixed_dll
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

    eff_series = [effective_mnq_qty(target_qty_mnq, t, mnq_per_mini=mnq_per_mini) for t in tiers]
    tier_summary: dict[str, object] = {
        "target_qty_mnq": target_qty_mnq,
        "mnq_per_mini": mnq_per_mini,
        "tier_transitions": transitions,
        "sessions_per_tier_index": {str(k): sessions_per_tier[k] for k in range(n_tiers)},
        "dll_pause_days_per_tier_index": {
            str(k): dll_pause_days_per_tier[k] for k in range(n_tiers)
        },
        "pre_lock_sessions": pre_lock_sessions,
        "post_lock_sessions": post_lock_sessions,
        "effective_mnq_cap_by_tier_index": {str(k): eff_series[k] for k in range(n_tiers)},
    }

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
        tier_summary=tier_summary,
    )


def simulate_apex_eod_two_phase_tiered_with_trace(
    session_pnls_per_mnq: np.ndarray,
    ny_calendar_dates: list[dt.date],
    *,
    starting_balance: float,
    trailing_dd: float,
    lock_equity_threshold: float | None = None,
    post_lock_floor: float | None = None,
    enforce_dll: bool = True,
    dll_terminates_run: bool = False,
    balance_tiers: tuple[ApexBalanceTier, ...],
    target_qty_mnq: float,
    mnq_per_mini: float = 10.0,
) -> tuple[ApexEodTwoPhaseSimResult, list[dict[str, object]]]:
    """Tiered funded walk with one dict per session (Wave 0f failure profiling)."""
    trace: list[dict[str, object]] = []
    res = _simulate_apex_eod_two_phase_tiered(
        session_pnls_per_mnq,
        ny_calendar_dates,
        starting_balance=starting_balance,
        trailing_dd=trailing_dd,
        lock_equity_threshold=lock_equity_threshold,
        post_lock_floor=post_lock_floor,
        enforce_dll=enforce_dll,
        dll_terminates_run=dll_terminates_run,
        balance_tiers=balance_tiers,
        target_qty_mnq=float(target_qty_mnq),
        mnq_per_mini=float(mnq_per_mini),
        session_trace_out=trace,
    )
    return res, trace


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
    floor_after = float(post_lock_floor) if post_lock_floor is not None else float(starting_balance)
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


def eval_pass_rate_calendar_days(
    pnls_per_eval_mnq: np.ndarray,
    exit_ny_dates: list[dt.date],
    exit_session_dates: list[object],
    exit_times: list[object],
    *,
    starting_balance: float,
    trailing_dd: float,
    profit_target: float,
    dll_limit: float,
    lock_equity_threshold: float | None = None,
    post_lock_floor: float | None = None,
    window_calendar_days: int = 30,
    dll_terminates_run: bool = False,
) -> dict[str, object]:
    """
    Rolling **calendar-day** windows of length ``window_calendar_days`` (inclusive span).

    Each window ``[d0, d0 + window_calendar_days - 1]`` includes trades with
    ``exit_ny_dates`` in that inclusive range. Trades are **pre-scaled** to eval MNQ
    (caller applies ``min(target_mnq, eval_cap_mnq)`` per trade row).
    """
    if pnls_per_eval_mnq.size != len(exit_ny_dates):
        msg = "pnls length must match exit_ny_dates"
        raise ValueError(msg)
    if window_calendar_days < 1:
        msg = "window_calendar_days must be >= 1"
        raise ValueError(msg)

    mn = min(exit_ny_dates)
    mx = max(exit_ny_dates)
    pass_c = 0
    fail_tr = 0
    fail_nt = 0
    total_w = 0
    d0 = mn
    span = dt.timedelta(days=window_calendar_days - 1)
    while d0 <= mx - span:
        d1 = d0 + span
        mask = np.array([(d0 <= d <= d1) for d in exit_ny_dates], dtype=bool)
        if not np.any(mask):
            d0 += dt.timedelta(days=1)
            continue
        total_w += 1
        idx = np.flatnonzero(mask)
        order = np.argsort([exit_times[int(i)] for i in idx])
        idx2 = idx[order]
        sub_p = pnls_per_eval_mnq[idx2]
        sub_ny = [exit_ny_dates[int(i)] for i in idx2]
        sub_sess = [exit_session_dates[int(i)] for i in idx2]
        r = simulate_eval_window_eod(
            sub_p,
            sub_ny,
            sub_sess,
            starting_balance=starting_balance,
            trailing_dd=trailing_dd,
            profit_target=profit_target,
            dll_limit=dll_limit,
            lock_equity_threshold=lock_equity_threshold,
            post_lock_floor=post_lock_floor,
            dll_terminates_run=dll_terminates_run,
        )
        if r["outcome"] == "pass":
            pass_c += 1
        elif r["mode"] == "trailing_dd":
            fail_tr += 1
        else:
            fail_nt += 1
        d0 += dt.timedelta(days=1)

    return {
        "total_windows": total_w,
        "passing_windows": pass_c,
        "pass_rate": (pass_c / total_w) if total_w > 0 else float("nan"),
        "fail_trailing": fail_tr,
        "fail_no_target": fail_nt,
        "window_calendar_days": window_calendar_days,
    }


def block_bootstrap_apex_eod_tiered_funded(
    trades_pnl_per_mnq: np.ndarray,
    trade_dates: list[object],
    trade_ny_dates: list[dt.date],
    *,
    target_qty_mnq: float,
    block_len: int,
    n_target_trades: int,
    n_iterations: int,
    rng: np.random.Generator,
    starting_balance: float,
    trailing_dd: float,
    balance_tiers: tuple[ApexBalanceTier, ...],
    lock_equity_threshold: float | None = None,
    post_lock_floor: float | None = None,
    mnq_per_mini: float = 10.0,
    enforce_dll: bool = True,
    dll_terminates_run: bool = False,
) -> dict[str, np.ndarray]:
    """Block-bootstrap **per-MNQ** trades through tiered PA funded path."""
    n = int(trades_pnl_per_mnq.size)
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
        blocks_pnl.append(trades_pnl_per_mnq[sl].copy())
        blocks_dates.append(list(trade_dates[sl]))
        blocks_ny.append(list(trade_ny_dates[sl]))

    n_blocks = len(blocks_pnl)
    survived = np.empty(n_iterations, dtype=bool)

    for it in range(n_iterations):
        buf_pnl: list[float] = []
        buf_d: list[object] = []
        buf_ny: list[dt.date] = []
        while len(buf_pnl) < n_target_trades:
            j = int(rng.integers(0, n_blocks))
            buf_pnl.extend(float(p) for p in blocks_pnl[j].tolist())
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
            dll_limit=0.0,
            lock_equity_threshold=lock_equity_threshold,
            post_lock_floor=post_lock_floor,
            enforce_dll=enforce_dll,
            dll_terminates_run=dll_terminates_run,
            balance_tiers=balance_tiers,
            target_qty_mnq=target_qty_mnq,
            mnq_per_mini=mnq_per_mini,
        )
        survived[it] = r.survived

    return {"survived": survived}


def diagnose_block_bootstrap_flat_funded_path(
    trades_pnl_scaled: np.ndarray,
    trade_dates: list[object],
    trade_ny_dates: list[dt.date],
    *,
    year: int,
    block_len: int,
    n_target_trades: int,
    n_iterations: int,
    rng: np.random.Generator,
    protocol_yfrac: float,
    funded_sim: Callable[
        [np.ndarray, list[dt.date]],
        ApexEodTwoPhaseSimResult,
    ],
) -> dict[str, object]:
    """
    Trade-series bootstrap diagnostics: per-resample **count of trades** with
    ``exit_ny_dates.year == year``, closed-trade **max DD**, **annualized** scaled
    P&amp;L on the path, and **funded survival** from ``funded_sim`` on collapsed
    session streaks.
    """
    n = int(trades_pnl_scaled.size)
    if n != len(trade_dates) or n != len(trade_ny_dates):
        msg = "length mismatch"
        raise ValueError(msg)
    n_y = sum(1 for d in trade_ny_dates if d.year == year)
    p_year = n_y / n if n else 0.0
    expected_count = float(n_target_trades) * p_year

    blocks_pnl: list[np.ndarray] = []
    blocks_dates: list[list[object]] = []
    blocks_ny: list[list[dt.date]] = []
    for start in range(0, n, block_len):
        sl = slice(start, min(start + block_len, n))
        blocks_pnl.append(trades_pnl_scaled[sl].copy())
        blocks_dates.append(list(trade_dates[sl]))
        blocks_ny.append(list(trade_ny_dates[sl]))

    n_blocks = len(blocks_pnl)
    counts = np.empty(n_iterations, dtype=np.int32)
    survived = np.empty(n_iterations, dtype=bool)
    max_dd = np.empty(n_iterations, dtype=np.float64)
    ann_pnl = np.empty(n_iterations, dtype=np.float64)

    for it in range(n_iterations):
        buf_pnl: list[float] = []
        buf_d: list[object] = []
        buf_ny: list[dt.date] = []
        while len(buf_pnl) < n_target_trades:
            j = int(rng.integers(0, n_blocks))
            for p, d, ny in zip(
                blocks_pnl[j].tolist(),
                blocks_dates[j],
                blocks_ny[j],
                strict=True,
            ):
                buf_pnl.append(float(p))
                buf_d.append(d)
                buf_ny.append(ny)
        buf_pnl = buf_pnl[:n_target_trades]
        buf_d = buf_d[:n_target_trades]
        buf_ny = buf_ny[:n_target_trades]

        arr = np.array(buf_pnl, dtype=np.float64)
        counts[it] = int(sum(1 for ny in buf_ny if ny.year == year))
        max_dd[it] = max_drawdown_closed_trade_pnl(arr)
        ann_pnl[it] = float(np.sum(arr)) / protocol_yfrac if protocol_yfrac > 0 else 0.0

        _, daily, dny = collapse_trades_with_ny_to_session_streaks(buf_d, buf_ny, arr)
        survived[it] = funded_sim(daily, dny).survived

    tol = 0.10 * expected_count if expected_count > 0 else 0.0
    near_expected = np.abs(counts.astype(np.float64) - expected_count) <= max(tol, 1.0)
    cond_frac = (
        float(np.mean(survived[near_expected].astype(np.float64)))
        if np.any(near_expected)
        else float("nan")
    )
    uncond_frac = float(np.mean(survived.astype(np.float64)))

    c_fail = counts[~near_expected] if np.any(~near_expected) else np.array([], dtype=np.int32)
    c_pass = counts[near_expected] if np.any(near_expected) else np.array([], dtype=np.int32)

    return {
        "year": year,
        "block_len": block_len,
        "n_trades_source": n,
        "n_trades_year_source": n_y,
        "p_year_in_source": p_year,
        "expected_year_trade_count": expected_count,
        "count_mean": float(np.mean(counts)),
        "count_std": float(np.std(counts)),
        "count_p05": float(np.percentile(counts, 5)),
        "count_p95": float(np.percentile(counts, 95)),
        "unconditional_survival_fraction": uncond_frac,
        "conditional_survival_within_10pct_expected_count": cond_frac,
        "n_resamples_near_expected_count": int(np.sum(near_expected)),
        "mean_count_failing_resamples": float(np.mean(c_fail)) if c_fail.size else None,
        "mean_count_passing_resamples": float(np.mean(c_pass)) if c_pass.size else None,
        "interpretation_hint": (
            "Compare conditional vs unconditional survival; compare count distribution "
            "to expected_count under Bernoulli(p_year) × n_target (block bootstrap "
            "alters variance vs iid)."
        ),
        "max_dd_mean": float(np.mean(max_dd)),
        "max_dd_p95": float(np.percentile(max_dd, 95)),
        "annual_pnl_mean": float(np.mean(ann_pnl)),
    }


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
    for d_sess, d_ny, p in zip(exit_session_dates, exit_ny_dates, net_pnls, strict=True):
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
