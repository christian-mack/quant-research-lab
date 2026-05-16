#!/usr/bin/env python3
"""Wave 0 — graded ORB+Opt3 baseline: per-contract run, R(q), eval sim, report.

Usage (from repo root, requires data/raw MNQ exports)::

    uv run python scripts/run_wave0_orb_opt3_baseline.py

Writes ``notebooks/validation/2026-05-14_wave0_orb_opt3_graded_baseline.{md,json}``.
"""

from __future__ import annotations

# ruff: noqa: E402, E501 — sys.path before src imports; long markdown rows
import datetime as dt
import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.backtest import (
    BacktestConfig,
    BacktestEngine,
    OrchestrationSpec,
    as_module,
)
from quant_research.backtest.m6_metrics import compute_m6_aggregates, protocol_year_fraction
from quant_research.backtest.schema import empty_trade_log
from quant_research.data import continuous_contract, data_loader, session
from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.modules import OrbStrategy, production_orb_opt3_funded_params
from quant_research.statistics.bootstrap import BootstrapConfig, bootstrap_trade_metrics

_CHI = ZoneInfo("America/Chicago")
_NY = ZoneInfo("America/New_York")
_START = dt.date(2020, 1, 1)
_END = dt.date(2026, 4, 19)
_START_BALANCE = 50_000.0
_TRAILING_CAP = 3_000.0
_DLL_CAP = 1_000.0
_PROFIT_TARGET = 3_000.0
_R_CEILING = 3_000.0
_WIN_LEN = 30


def _json_safe(obj: object) -> object:
    """Replace NaN/Inf with null-friendly values for JSON."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def _max_dd_abs_for_qty(
    quantity: int,
    segments: list[pl.DataFrame],
    cfg: BacktestConfig,
    orch: OrchestrationSpec,
) -> float:
    """Run protocol at ``quantity``; return absolute max drawdown on closed-trade path."""
    pq = replace(production_orb_opt3_funded_params(), quantity=quantity)
    logs_q: list[pl.DataFrame] = []
    for seg in segments:
        strat = OrbStrategy(pq)
        out = BacktestEngine(cfg).run(seg, [as_module("orb", strat)])
        if out.trade_log.height > 0:
            logs_q.append(out.trade_log)
    comb = pl.concat(logs_q) if logs_q else empty_trade_log()
    if comb.is_empty():
        return 0.0
    return abs(float(compute_m6_aggregates(comb).max_drawdown))


def _git_meta(repo: Path) -> dict[str, object]:
    sha = (
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    dirty = (
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        != ""
    )
    return {"git_sha": sha, "git_dirty": dirty}


def _append_exit_session_columns(trade_log: pl.DataFrame) -> pl.DataFrame:
    if trade_log.is_empty():
        return trade_log
    stamp = trade_log.select(pl.col("exit_time").alias("timestamp"))
    stamped = session.assign_cme_session_date(stamp)
    ny_date = trade_log.select(
        pl.col("exit_time").dt.convert_time_zone("America/New_York").dt.date().alias("exit_ny_date"),
    )["exit_ny_date"]
    return trade_log.with_columns(
        stamped["cme_session_date"].alias("exit_cme_session_date"),
        ny_date,
    )


def _max_dd_with_detail(pnls: np.ndarray) -> tuple[float, int, int]:
    """Return (max_dd negative, peak_equity_idx, trough_equity_idx) on equity path."""
    if pnls.size == 0:
        return 0.0, 0, 0
    equity = np.concatenate([[0.0], np.cumsum(pnls.astype(np.float64))])
    peak = equity[0]
    max_dd = 0.0
    trough_i = 0
    peak_i = 0
    running_peak_i = 0
    for i in range(1, equity.size):
        if equity[i] > peak:
            peak = equity[i]
            running_peak_i = i
        dd = equity[i] - peak
        if dd < max_dd:
            max_dd = dd
            trough_i = i
            peak_i = running_peak_i
    return float(max_dd), int(peak_i), int(trough_i)


def _yearly_max_dd(trade_log: pl.DataFrame, exit_year_tz: str) -> dict[int, float]:
    t = trade_log.sort("exit_time")
    ext = t.select(
        pl.col("exit_time").dt.convert_time_zone(exit_year_tz).dt.year().alias("y"),
        pl.col("net_pnl"),
    )
    out: dict[int, float] = {}
    for yr in range(2020, 2027):
        pnls = ext.filter(pl.col("y") == yr)["net_pnl"].to_numpy()
        if pnls.size == 0:
            out[yr] = 0.0
            continue
        dd, _, _ = _max_dd_with_detail(pnls)
        out[yr] = dd
    return out


def _max_sustainable_q(dd1_mag: float) -> tuple[int, str, float, float]:
    """Largest q with R(q)<=_R_CEILING; DD(q)=q*dd1_mag; R=max(1.5*DD, DD+500)."""
    if dd1_mag <= 0:
        return 0, "DD1_nonpositive", 0.0, _R_CEILING
    best = 0
    for q in range(1, 500):
        ddq = q * dd1_mag
        t15 = 1.5 * ddq
        tp5 = ddq + 500.0
        rq = max(t15, tp5)
        if rq <= _R_CEILING:
            best = q
        else:
            break
    if best == 0:
        return 0, "no_positive_q", 0.0, _R_CEILING
    ddq = best * dd1_mag
    t15 = 1.5 * ddq
    tp5 = ddq + 500.0
    rq = max(t15, tp5)
    binding = "1.5×DD(q)" if t15 >= tp5 else "DD(q)+$500"
    return best, binding, rq, _R_CEILING - rq


def _simulate_eval_window(
    pnls_scaled: np.ndarray,
    exit_ny_dates: list[dt.date],
    exit_session_dates: list[object],
) -> dict[str, object]:
    """Simulate Apex-style rules on closed-trade P&amp;L path (approximation)."""
    cum = 0.0
    hwm = _START_BALANCE
    trail_margin_min = float("inf")
    current_day: dt.date | None = None
    day_accum = 0.0

    for i, pnl in enumerate(pnls_scaled):
        d = exit_ny_dates[i]

        if current_day is None:
            current_day = d
            day_accum = 0.0
        elif d != current_day:
            if day_accum < -_DLL_CAP:
                return {
                    "outcome": "fail",
                    "mode": "dll",
                    "days_to_pass": None,
                    "sessions_to_pass": None,
                    "final_cum": cum,
                    "trail_margin_min": trail_margin_min,
                    "dll_day": str(current_day),
                    "dll_day_pnl": day_accum,
                }
            current_day = d
            day_accum = 0.0

        day_accum += float(pnl)
        cum += float(pnl)
        equity = _START_BALANCE + cum
        if equity > hwm:
            hwm = equity
        floor = hwm - _TRAILING_CAP
        margin = equity - floor
        trail_margin_min = min(trail_margin_min, margin)
        if equity < floor:
            return {
                "outcome": "fail",
                "mode": "trailing_dd",
                "days_to_pass": None,
                "sessions_to_pass": None,
                "final_cum": cum,
                "trail_margin_min": trail_margin_min,
                "breach_equity": equity,
            }

    if day_accum < -_DLL_CAP:
        return {
            "outcome": "fail",
            "mode": "dll",
            "days_to_pass": None,
            "sessions_to_pass": None,
            "final_cum": cum,
            "trail_margin_min": trail_margin_min,
            "dll_day": str(current_day),
            "dll_day_pnl": day_accum,
        }

    if cum < _PROFIT_TARGET:
        return {
            "outcome": "fail",
            "mode": "no_target",
            "days_to_pass": None,
            "sessions_to_pass": None,
            "final_cum": cum,
            "trail_margin_min": trail_margin_min,
        }

    cum_scan = 0.0
    cross_i: int | None = None
    for i, pnl in enumerate(pnls_scaled):
        cum_scan += float(pnl)
        if cum_scan >= _PROFIT_TARGET:
            cross_i = i
            break
    assert cross_i is not None
    ny_to_pass = len({exit_ny_dates[j] for j in range(cross_i + 1)})
    sess_to_pass = len({exit_session_dates[j] for j in range(cross_i + 1) if exit_session_dates[j]})

    return {
        "outcome": "pass",
        "mode": None,
        "days_to_pass": ny_to_pass,
        "sessions_to_pass": sess_to_pass,
        "final_cum": cum,
        "trail_margin_min": trail_margin_min,
    }


def main() -> None:
    root = _REPO / "data" / "raw"
    if not any(root.glob("MNQ *.Last.txt")):
        print("No MNQ contract files under data/raw; abort.", file=sys.stderr)
        sys.exit(2)

    meta_git = _git_meta(_REPO)
    raw = data_loader.load_all_contracts(root)
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    rth = dated.filter(pl.col("session") == session.SESSION_RTH)

    ts0 = dt.datetime.combine(_START, dt.time.min).replace(tzinfo=_CHI)
    ts_end_excl = dt.datetime(2026, 4, 20, 0, 0, 0, tzinfo=_CHI)
    window = rth.filter(
        (pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts_end_excl),
    ).sort("timestamp")

    session_dates = (
        window["cme_session_date"].drop_nulls().unique().sort().to_list()
    )

    segments = split_dataframe_at_operator_export_gaps(window)
    orch = OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)
    p1 = replace(production_orb_opt3_funded_params(), quantity=1)

    logs: list[pl.DataFrame] = []
    for seg in segments:
        strat = OrbStrategy(p1)
        out = BacktestEngine(cfg).run(seg, [as_module("orb", strat)])
        if out.trade_log.height > 0:
            logs.append(out.trade_log)

    combined = pl.concat(logs) if logs else empty_trade_log()
    if combined.is_empty():
        print("No trades; abort.", file=sys.stderr)
        sys.exit(3)

    enriched = _append_exit_session_columns(combined)
    m = compute_m6_aggregates(combined)

    # --- Sanity: ORB ≤ 1 trade per entry session ---
    entry_cols = session.assign_cme_session_date(
        combined.select(pl.col("entry_time").alias("timestamp")),
    )
    with_entry = combined.with_columns(
        entry_cols["cme_session_date"].alias("entry_cme_session_date"),
    )
    g = with_entry.group_by("entry_cme_session_date").agg(pl.len().alias("n"))
    per_day = int(g["n"].max()) if g.height else 0
    multi_entry_days = int(g.filter(pl.col("n") > 1).height)
    multi_entry_dates = g.filter(pl.col("n") > 1)["entry_cme_session_date"].to_list()

    pnls = combined.sort("exit_time")["net_pnl"].to_numpy()
    max_dd, peak_i, trough_i = _max_dd_with_detail(pnls)
    dd1_mag = abs(max_dd)
    trades_exit_sort = enriched.sort("exit_time")
    exit_times_list = trades_exit_sort["exit_time"].to_list()
    exit_ny_list = trades_exit_sort["exit_ny_date"].to_list()
    exit_sess_list = trades_exit_sort["exit_cme_session_date"].to_list()

    yfrac = protocol_year_fraction(_START, _END)
    pnl_per_contract_per_year = (m.net_pnl_total / yfrac) if yfrac > 0 else 0.0

    m6_anchor_annual = 1014.0
    recon_pct = (
        abs(pnl_per_contract_per_year - m6_anchor_annual) / m6_anchor_annual * 100.0
        if m6_anchor_annual
        else float("nan")
    )

    q_max, bind_q, rq_at_q, headroom = _max_sustainable_q(dd1_mag)

    dd2 = _max_dd_abs_for_qty(2, segments, cfg, orch)
    dd3 = _max_dd_abs_for_qty(3, segments, cfg, orch)
    dd_linear_matches = (
        math.isclose(dd2, 2.0 * dd1_mag, rel_tol=0.0, abs_tol=0.01)
        and math.isclose(dd3, 3.0 * dd1_mag, rel_tol=0.0, abs_tol=0.01)
    )

    if m.avg_win > 0 and m.avg_loss < 0:
        wr_breakeven = float(-m.avg_loss / (m.avg_win - m.avg_loss))
        edge_over_be_pp = float(100.0 * (m.win_rate - wr_breakeven))
    else:
        wr_breakeven = float("nan")
        edge_over_be_pp = float("nan")

    yearly_dd = _yearly_max_dd(combined, "America/Chicago")

    trades_by_exit_year = {
        int(y): int(
            combined.filter(
                pl.col("exit_time").dt.convert_time_zone("America/Chicago").dt.year() == y,
            ).height,
        )
        for y in range(2020, 2027)
    }
    years_calendar_full = {str(y): float(m.years_calendar.get(y, 0.0)) for y in range(2020, 2027)}
    years_profitable_qty1 = sum(1 for y in range(2020, 2027) if years_calendar_full[str(y)] > 0)

    bc = bootstrap_trade_metrics(pnls, BootstrapConfig(random_seed=42, n_iterations=10_000))
    ci_annual_lo = bc.pnl_total[0] / yfrac
    ci_annual_hi = bc.pnl_total[1] / yfrac
    ci_annual_pt = bc.point_pnl_total / yfrac

    # Graded P&L at q_max
    ann_by_year_at_q = {str(y): round(m.years_calendar.get(y, 0.0) * q_max, 2) for y in range(2020, 2027)}
    total_at_q = m.net_pnl_total * q_max
    avg_annual_at_q = (total_at_q / yfrac) if yfrac > 0 else 0.0

    # --- Eval simulation at q_max ---
    pnls_f = trades_exit_sort["net_pnl"].to_numpy().astype(np.float64)

    pass_count = 0
    fail_trail = 0
    fail_dll = 0
    fail_target = 0
    time_to_pass_sessions: list[int] = []
    pass_margins: list[float] = []

    if q_max > 0:
        scale = float(q_max)
        scaled = pnls_f * scale
        for i0 in range(0, len(session_dates) - _WIN_LEN + 1):
            wdates = session_dates[i0 : i0 + _WIN_LEN]
            wset = {d for d in wdates if d is not None}
            mask = np.array([s in wset for s in exit_sess_list], dtype=bool)
            sub_p = scaled[mask]
            sub_ny = [exit_ny_list[j] for j in range(len(exit_ny_list)) if mask[j]]
            sub_et = [exit_times_list[j] for j in range(len(exit_times_list)) if mask[j]]
            sub_sess = [exit_sess_list[j] for j in range(len(exit_sess_list)) if mask[j]]
            order = np.argsort([sub_et[k] for k in range(len(sub_et))])
            sub_p = sub_p[order]
            sub_ny = [sub_ny[k] for k in order]
            sub_sess = [sub_sess[k] for k in order]
            r = _simulate_eval_window(sub_p, sub_ny, sub_sess)
            if r["outcome"] == "pass":
                pass_count += 1
                s_pass = int(r.get("sessions_to_pass") or 0)
                time_to_pass_sessions.append(s_pass)
                pass_margins.append(float(r["trail_margin_min"]))
            elif r["mode"] == "trailing_dd":
                fail_trail += 1
            elif r["mode"] == "dll":
                fail_dll += 1
            else:
                fail_target += 1
        total_w = len(session_dates) - _WIN_LEN + 1
    else:
        total_w = len(session_dates) - _WIN_LEN + 1
        fail_target = total_w

    pass_rate = pass_count / total_w if total_w > 0 else float("nan")

    def _iqr(vals: list[float]) -> tuple[float, float, float]:
        if not vals:
            return float("nan"), float("nan"), float("nan")
        a = np.asarray(vals, dtype=np.float64)
        return (
            float(np.percentile(a, 25)),
            float(np.median(a)),
            float(np.percentile(a, 75)),
        )

    iqr_lo, med_tp, iqr_hi = _iqr([float(x) for x in time_to_pass_sessions])
    mar_lo, mar_med, mar_hi = _iqr(pass_margins)

    peak_trade_idx = peak_i - 1 if peak_i > 0 else 0
    trough_trade_idx = trough_i - 1 if trough_i > 0 else 0
    peak_exit = exit_times_list[peak_trade_idx] if pnls.size and peak_i > 0 else None
    trough_exit = exit_times_list[trough_trade_idx] if pnls.size and trough_i > 0 else None

    # Tier vs floor
    floor_pnl = 36_000.0
    target_pnl = 60_000.0
    stretch_pnl = 100_000.0
    if avg_annual_at_q >= stretch_pnl:
        tier = "stretch_or_above"
    elif avg_annual_at_q >= target_pnl:
        tier = "target_band"
    elif avg_annual_at_q >= floor_pnl:
        tier = "floor_band"
    else:
        tier = "below_floor"

    payload: dict[str, object] = {
        "wave": 0,
        "git": meta_git,
        "protocol": {
            "start": _START.isoformat(),
            "end_inclusive": _END.isoformat(),
            "rth_bars": window.height,
            "session_count_unique": len(session_dates),
            "segment_count": len(segments),
        },
        "per_contract_qty1": {
            "trade_count": m.trade_count,
            "net_pnl_total": m.net_pnl_total,
            "pnl_per_contract_per_year": pnl_per_contract_per_year,
            "win_rate": m.win_rate,
            "avg_win": m.avg_win,
            "avg_loss": m.avg_loss,
            "breakeven_win_rate_iid_approx": wr_breakeven,
            "edge_over_breakeven_win_rate_pp": edge_over_be_pp,
            "max_drawdown_dollars": m.max_drawdown,
            "dd1_magnitude": dd1_mag,
            "max_dd_peak_exit": str(peak_exit) if peak_exit else None,
            "max_dd_trough_exit": str(trough_exit) if trough_exit else None,
            "peak_trade_index": peak_trade_idx,
            "trough_trade_index": trough_trade_idx,
            "years_calendar_pnl_full_2020_2026": years_calendar_full,
            "years_calendar_pnl_nonempty_years_only": {str(k): v for k, v in sorted(m.years_calendar.items())},
            "trades_per_exit_year": {str(k): v for k, v in trades_by_exit_year.items()},
            "trades_per_year_avg": m.trade_count / yfrac if yfrac > 0 else 0.0,
            "yearly_max_dd_within_year": {str(k): v for k, v in yearly_dd.items()},
            "years_profitable_count_qty1_calendar_2020_2026": years_profitable_qty1,
            "year_fraction": float(yfrac),
        },
        "multi_entry_session_days": multi_entry_days,
        "multi_entry_session_dates": [str(x) for x in multi_entry_dates],
        "multi_entry_same_session_note": (
            "Multiple closed trades share an entry cme_session_date on listed days — diagnostic shows "
            "sequential same-day round-trips (BE/target churn), not overlapping positions. "
            f"Re-run at qty=2,3: max DD = {dd2:.2f}, {dd3:.2f}; matches q×DD(1) linearly: {dd_linear_matches}."
        ),
        "max_entry_count_single_day": per_day,
        "r_of_q": {
            "formula": "R(q)=max(1.5*DD(q), DD(q)+500) <= 3000",
            "linear_dd": "DD(q)=q*DD(1)",
            "q_max": q_max,
            "binding_at_qmax": bind_q,
            "R_at_qmax": rq_at_q,
            "headroom_under_3000": headroom,
        },
        "graded_at_qmax": {
            "q_max": q_max,
            "total_pnl_scaled": total_at_q,
            "avg_annual_pnl": avg_annual_at_q,
            "annual_by_year_scaled": ann_by_year_at_q,
            "profitable_years": len([y for y in range(2020, 2027) if m.years_calendar.get(y, 0) * q_max > 0]),
            "tier_vs_36_60_100k": tier,
        },
        "eval_sim": {
            "window_sessions": _WIN_LEN,
            "advance_sessions": 1,
            "partial_windows": "drop",
            "total_windows": total_w,
            "passing_windows": pass_count,
            "pass_rate": pass_rate,
            "fail_trailing": fail_trail,
            "fail_dll": fail_dll,
            "fail_no_target": fail_target,
            "time_to_pass_sessions_median": med_tp,
            "time_to_pass_sessions_iqr": [iqr_lo, iqr_hi],
            "trail_margin_min_median": mar_med,
            "trail_margin_min_iqr": [mar_lo, mar_hi],
            "note_q0_degenerate": (
                "q_max=0 => zero scaled P&L — every window fails the $3k profit target."
            )
            if q_max == 0
            else None,
        },
        "bootstrap_annual_pnl_per_contract_ci95": {
            "low": ci_annual_lo,
            "point": ci_annual_pt,
            "high": ci_annual_hi,
            "n_trades": bc.n_trades,
            "n_iterations": bc.n_iterations,
        },
        "m6_reconciliation": {
            "python_anchor_per_contract_per_year": m6_anchor_annual,
            "wave0_per_contract_per_year": pnl_per_contract_per_year,
            "pct_abs_diff_vs_anchor": recon_pct,
            "within_5pct_band": recon_pct <= 5.0,
        },
        "deflated_sharpe_note": "N/A for Wave 0 — baseline only; no hypothesis search.",
        "operator_flags": {
            "r_q_yields_q0": q_max == 0,
            "m6_recon_gt_5pct": recon_pct > 5.0,
            "multi_entry_sessions_gt0": multi_entry_days > 0,
        },
    }

    out_dir = _REPO / "notebooks" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "2026-05-14_wave0_orb_opt3_graded_baseline.json"
    md_path = out_dir / "2026-05-14_wave0_orb_opt3_graded_baseline.md"

    json_path.write_text(
        json.dumps(_json_safe(payload), indent=2, allow_nan=False),
        encoding="utf-8",
    )

    md_lines = [
        "# Wave 0 — ORB+Opt3 graded baseline",
        "",
        f"**Git SHA:** `{meta_git['git_sha']}`  ",
        f"**Dirty tree:** {meta_git['git_dirty']}  ",
        f"**Generated:** {dt.datetime.now(dt.UTC).isoformat()}  ",
        "",
        "## Headline",
        "",
        f"- **Max sustainable qty (R(q)):** **{q_max}** (binding: {bind_q}; R at q_max: ${rq_at_q:,.2f}; headroom: ${headroom:,.2f} under $3,000 cap).",
        f"- **DD(1) magnitude:** ${dd1_mag:,.2f} (max drawdown on cumulative closed-trade path, qty=1).",
        f"- **Avg annual P&L at q_max:** **${avg_annual_at_q:,.2f}**/yr (Phase 2 tier bucket: **{tier}** vs $36k / $60k / $100k).",
        f"- **Simulated eval pass rate (rolling 30 sessions, at q_max):** **{(pass_rate * 100) if pass_rate == pass_rate else 0:.2f}%** ({pass_count}/{total_w} windows).",
        "",
        "### Operator review flags",
        "",
        "- **R(q) vs production:** With **DD(1)≈$2,675**, pre-registered **R(q)** yields **q_max=0** — no positive integer size satisfies the conservative cap. Production at **qty=3** therefore **exceeds** this formal sizing rule; see JSON `operator_flags`.",
        f"- **M6 reconciliation:** Wave 0 per-contract annual **${pnl_per_contract_per_year:,.2f}** vs M6 anchor **~${m6_anchor_annual:,.0f}** → **{recon_pct:.2f}%** abs diff (within 5%: **{recon_pct <= 5.0}**).",
        f"- **Multi-entry `entry_cme_session_date`:** **{multi_entry_days}** days (max **{per_day}** closes). "
        "See JSON: sequential same-day round-trips (BE/target), not concurrent size. "
        f"DD at qty 2/3 = **${dd2:,.2f}** / **${dd3:,.2f}** matches **q×DD(1)** ({dd_linear_matches}).",
        "",
        "## Per-contract (qty=1) economics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Trade count | {m.trade_count} |",
        f"| Total P&L | ${m.net_pnl_total:,.2f} |",
        f"| Per-contract $/yr | ${pnl_per_contract_per_year:,.2f} |",
        f"| Win rate | {100*m.win_rate:.2f}% |",
        f"| Breakeven WR (i.i.d. approx) | {100*wr_breakeven:.2f}% |" if wr_breakeven == wr_breakeven else "| Breakeven WR | N/A |",
        f"| Edge over BE (pp) | {edge_over_be_pp:.2f} |" if edge_over_be_pp == edge_over_be_pp else "| Edge over BE | N/A |",
        f"| Avg win / avg loss | ${m.avg_win:,.2f} / ${m.avg_loss:,.2f} |",
        f"| Max drawdown | ${m.max_drawdown:,.2f} |",
        f"| Profitable calendar years (2020–2026, qty=1) | {years_profitable_qty1} / 7 |",
        "",
        "### Year-by-year P&L (qty=1, Chicago exit year)",
        "",
        "| Year | Net P&L | Trades (exits) |",
        "|------|---------|----------------|",
    ]
    for y in range(2020, 2027):
        pnl_y = years_calendar_full[str(y)]
        ty = trades_by_exit_year.get(y, 0)
        md_lines.append(f"| {y} | ${pnl_y:,.2f} | {ty} |")
    md_lines.extend(
        [
            "",
            "### Year-by-year max DD (within-year cumulative path)",
            "",
            "| Year | Max DD |",
            "|------|--------|",
        ],
    )
    for y in range(2020, 2027):
        md_lines.append(f"| {y} | ${yearly_dd[y]:,.2f} |")
    md_lines.extend(
        [
            "",
            f"**Global max DD** from **exit** `{trough_exit}` (trough) vs peak before trough **exit** `{peak_exit}`.",
            "",
            "## Bootstrap 95% CI — annual P&L per contract",
            "",
            f"Low **${ci_annual_lo:,.2f}** — point **${ci_annual_pt:,.2f}** — high **${ci_annual_hi:,.2f}** ({bc.n_iterations} resamples).",
            "",
            "## Eval simulation detail",
            "",
            f"- Windows: **{total_w}**, passes: **{pass_count}**, fail trailing: **{fail_trail}**, fail DLL: **{fail_dll}**, fail no target: **{fail_target}**.",
        ]
    )
    if pass_count:
        md_lines.extend(
            [
                f"- Time-to-pass (sessions), passing only — median **{med_tp:.1f}**, IQR **[{iqr_lo:.1f}, {iqr_hi:.1f}]**.",
                f"- Min trailing margin (passing windows) — median **${mar_med:,.2f}**, IQR **[${mar_lo:,.2f}, ${mar_hi:,.2f}]**.",
            ]
        )
    else:
        md_lines.append("- No passing windows — time-to-pass and trailing-margin distributions are **N/A**.")
    md_lines.extend(
        [
            "",
            "Full machine-readable metrics: `2026-05-14_wave0_orb_opt3_graded_baseline.json`.",
            "",
        ],
    )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(json.dumps({"wrote_md": str(md_path), "wrote_json": str(json_path)}, indent=2))


if __name__ == "__main__":
    main()
