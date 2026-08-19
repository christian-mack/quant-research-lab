#!/usr/bin/env python3
"""Wave 0h — ORB+Opt3 chapter close-out: per-session loss tail vs Apex pre-lock buffer.

Usage::

    uv run python scripts/run_wave0h_orb_opt3_chapter_closeout.py

Writes ``notebooks/validation/2026-05-17_wave0h_orb_opt3_chapter_closeout.{md,json}``.
"""

from __future__ import annotations

# ruff: noqa: E402
import datetime as dt
import json
import math
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.backtest import BacktestConfig, BacktestEngine, OrchestrationSpec, as_module
from quant_research.backtest.schema import empty_trade_log
from quant_research.data import continuous_contract, data_loader, session
from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.modules import OrbStrategy, production_orb_opt3_funded_params

_CHI = ZoneInfo("America/Chicago")
_START = dt.date(2020, 1, 1)
_END = dt.date(2026, 4, 19)

# Mirrors Wave 0e/0g PA EOD class parameters (pre-lock trailing, lock, profit target).
_APEX_PRELOCK: dict[str, dict[str, float]] = {
    "25k": {
        "starting_balance": 25_000.0,
        "trailing_dd_tdd": 1_000.0,
        "profit_target_usd": 1_500.0,
        "lock_equity": 26_000.0,
        "post_lock_floor": 25_000.0,
    },
    "50k": {
        "starting_balance": 50_000.0,
        "trailing_dd_tdd": 2_000.0,
        "profit_target_usd": 3_000.0,
        "lock_equity": 52_000.0,
        "post_lock_floor": 50_000.0,
    },
    "100k": {
        "starting_balance": 100_000.0,
        "trailing_dd_tdd": 3_000.0,
        "profit_target_usd": 6_000.0,
        "lock_equity": 103_000.0,
        "post_lock_floor": 100_000.0,
    },
    "150k": {
        "starting_balance": 150_000.0,
        "trailing_dd_tdd": 4_000.0,
        "profit_target_usd": 9_000.0,
        "lock_equity": 154_000.0,
        "post_lock_floor": 150_000.0,
    },
}

_QTY_SCALES: tuple[int, ...] = (1, 2, 5, 10)
_HIST_BINS = 40
_HALF_TDD_REFERENCE_CLASS = "50k"


def _git_meta(repo: Path) -> dict[str, object]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
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


def _json_safe(obj: object) -> object:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, dt.date):
        return obj.isoformat()
    return obj


def _append_exit_ny(trade_log: pl.DataFrame) -> pl.DataFrame:
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


def _build_rth_window() -> pl.DataFrame:
    raw = data_loader.load_all_contracts(_REPO / "data" / "raw")
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    ts0 = dt.datetime.combine(_START, dt.time.min).replace(tzinfo=_CHI)
    ts_end_excl = dt.datetime(2026, 4, 20, 0, 0, 0, tzinfo=_CHI)
    return dated.filter(
        (pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts_end_excl),
        pl.col("session") == session.SESSION_RTH,
    ).sort("timestamp")


def _build_trade_log_qty1(rth: pl.DataFrame) -> pl.DataFrame:
    segments = split_dataframe_at_operator_export_gaps(rth)
    orch = OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)
    p1 = replace(production_orb_opt3_funded_params(), quantity=1)
    logs: list[pl.DataFrame] = []
    for seg in segments:
        out = BacktestEngine(cfg).run(seg, [as_module("orb", OrbStrategy(p1))])
        if out.trade_log.height > 0:
            logs.append(out.trade_log)
    combined = pl.concat(logs) if logs else empty_trade_log()
    return _append_exit_ny(combined.sort("exit_time"))


def _percentiles_positive_magnitude(loss_neg: np.ndarray, pct: Sequence[float]) -> dict[str, float]:
    """loss_neg: negative session P&L values only. Report magnitudes at upper tail of abs(loss)."""
    if loss_neg.size == 0:
        return {f"p{int(p)}": float("nan") for p in pct}
    absv = np.abs(loss_neg.astype(np.float64))
    return {f"p{int(p)}": float(np.percentile(absv, p)) for p in pct}


def main() -> None:
    meta_git = _git_meta(_REPO)
    root_raw = _REPO / "data" / "raw"
    if not any(root_raw.glob("MNQ *.Last.txt")):
        print("No MNQ data under data/raw; abort.", file=sys.stderr)
        sys.exit(2)

    rth = _build_rth_window()
    enriched = _build_trade_log_qty1(rth)
    n_trades = int(enriched.height)

    by_day = enriched.group_by("exit_ny_date").agg(
        pl.col("net_pnl").sum().alias("session_pnl_mnq1"),
        pl.len().alias("n_trades"),
    )
    session_pnls = by_day["session_pnl_mnq1"].to_numpy().astype(np.float64)
    n_session_days = int(session_pnls.size)
    max_trades_day = int(by_day["n_trades"].max()) if n_session_days else 0
    n_multi = int(by_day.filter(pl.col("n_trades") > 1).height)

    losing_mask = session_pnls < 0
    losses = session_pnls[losing_mask]
    n_losing = int(losses.size)

    mean_loss = float(np.mean(losses)) if n_losing else float("nan")
    median_loss = float(np.median(losses)) if n_losing else float("nan")
    max_loss = float(np.min(session_pnls)) if n_session_days else float("nan")

    pct_levels = (75.0, 90.0, 95.0, 99.0)
    mag_pct = _percentiles_positive_magnitude(losses, pct_levels)
    median_abs = float(np.median(np.abs(losses))) if n_losing else float("nan")

    tail_multiples: dict[str, float | None] = {}
    if n_losing and median_abs > 0 and math.isfinite(median_abs):
        for k, v in mag_pct.items():
            tail_multiples[f"{k}_over_median_abs"] = float(v) / median_abs
    else:
        for k in mag_pct:
            tail_multiples[f"{k}_over_median_abs"] = None

    hist_counts: list[float] | None
    hist_edges: list[float] | None
    if n_losing:
        counts, edges = np.histogram(losses, bins=_HIST_BINS, range=(float(np.min(losses)), 0.0))
        hist_counts = [float(x) for x in counts.tolist()]
        hist_edges = [float(x) for x in edges.tolist()]
    else:
        hist_counts = None
        hist_edges = None

    apex_rows: list[dict[str, object]] = []
    stop_flags: dict[str, bool] = {}
    tdd_ref = float(_APEX_PRELOCK[_HALF_TDD_REFERENCE_CLASS]["trailing_dd_tdd"])
    p99_mag = mag_pct.get("p99", float("nan"))
    stop_surface = bool(math.isfinite(p99_mag) and p99_mag <= 0.5 * tdd_ref)

    for cls, row in sorted(_APEX_PRELOCK.items()):
        tdd = float(row["trailing_dd_tdd"])
        pt = float(row["profit_target_usd"])
        start = float(row["starting_balance"])
        lock_eq = float(row["lock_equity"])
        rise_to_lock = lock_eq - start
        half_tdd = 0.5 * tdd
        scale_rows: list[dict[str, object]] = []
        for q in _QTY_SCALES:
            scaled = {k: float(v) * q for k, v in mag_pct.items()}
            pct_of_tdd = {k: 100.0 * scaled[k] / tdd for k in mag_pct}
            scale_rows.append(
                {
                    "qty_mnq": q,
                    "abs_loss_percentiles_usd": scaled,
                    "abs_loss_percentiles_pct_of_tdd": pct_of_tdd,
                },
            )

        linear_stop_factor_vs_tdd = (
            half_tdd / p99_mag if (math.isfinite(p99_mag) and p99_mag > 0) else None
        )
        pct_reduction_needed: float | None = None
        if linear_stop_factor_vs_tdd is not None:
            f = min(linear_stop_factor_vs_tdd, 1.0)
            pct_reduction_needed = max(0.0, (1.0 - f) * 100.0)

        apex_rows.append(
            {
                "account_class": cls,
                "starting_balance": start,
                "pre_lock_trailing_drawdown_tdd_usd": tdd,
                "profit_target_usd": pt,
                "lock_equity_threshold": lock_eq,
                "post_lock_floor": float(row["post_lock_floor"]),
                "margin_to_trailing_floor_at_open_assumes_hwm_equals_start_usd": tdd,
                "margin_to_trailing_floor_just_below_lock_threshold_hwm_equals_lock_eq_usd": tdd,
                "notes": (
                    "Under two-phase pre-lock rules, margin to the **trailing** floor equals "
                    "**TDD** whenever equity and HWM are equal (including at open and when HWM "
                    "reaches the lock threshold). **profit_target_usd** is the eval profit-target "
                    "**dollars**, distinct from trailing margin."
                ),
                "equity_gain_from_start_to_lock_threshold_usd": rise_to_lock,
                "percentile_abs_loss_mnq1_usd": mag_pct,
                "percentile_abs_loss_mnq1_pct_of_tdd": {
                    k: 100.0 * mag_pct[k] / tdd for k in mag_pct
                },
                "scaled_qty_comparison": scale_rows,
                "back_of_envelope_linear_stop_model": {
                    "assumption": (
                        "Proportional scaling: narrowing stop distance scales all session losses "
                        "by the same factor. **Does not** model win-rate, fill quality, or "
                        "exit-type mix."
                    ),
                    "target_cap": (
                        "99th-percentile **absolute** session loss ≤ 50% of class TDD (pre-lock)."
                    ),
                    "linear_scale_factor_to_hit_cap_on_p99": linear_stop_factor_vs_tdd,
                    "implied_stop_distance_reduction_pct_if_factor_lt_1": pct_reduction_needed,
                },
            },
        )
        stop_flags[f"p99_abs_le_half_tdd_{cls}"] = bool(
            math.isfinite(p99_mag) and p99_mag <= half_tdd,
        )

    deliverable_4_operator_questions = {
        "a_candidate_strategy_families": [
            (
                "Mean-reversion intraday (timeframe / trigger distinct from legacy "
                "AfternoonMR-style stacks)"
            ),
            "Short-horizon trend continuation with deliberately tight risk (stop-first design)",
            "Cross-instrument relative-value or basket hedges on correlated index products",
            "Options-based vol / premium strategies (if execution stack and PA rules allow)",
            "Scheduled event or macro-release windows with bounded risk",
            "Microstructure-informed scalp / queue-position ideas (latency and fee sensitive)",
            "Session/regime-conditional breakout or fade with explicit tail caps",
            "Statistical pairs on index vs sector ETF micro (scope vs MNQ-only kickoff)",
            "Overnight / globex edge with DLL-aware day boundaries",
            (
                "Hybrid: reduced-size ORB-like structure with modified exit (explicitly **not** "
                "pursued as ORB+Opt3 repair per operator close-out — listed only as a family)"
            ),
        ],
        "b_apex_hard_constraints_screening": [
            (
                "Pre-register **per-session realized loss** distribution vs **pre-lock TDD** at "
                "candidate **starting** qty before scaling — e.g. flag if empirical p99 session "
                "loss approaches 50–100% of TDD under the same simulation semantics as Wave 0e–0g."
            ),
            "Maintain **DLL** (session pause) and **tier cap** fidelity when grading.",
            (
                "Keep **joint gates** (funded survival + block bootstrap + eval pass rate) unless "
                "operator revises thresholds."
            ),
        ],
        "c_trade_frequency_floor": (
            "Kickoff treats frequency as a first-class constraint. After ORB+Opt3 findings, does "
            "the operator want a **higher minimum trades/year** for new hypotheses to reduce "
            "DD-window variance — or keep MV-edge **≥80 trades/yr** as the isolation screen and "
            "relax only after tail diagnostics pass?"
        ),
        "d_instruments_wave1": (
            "Phase 2 default is **MNQ-only** (M8 deferred). Should Wave 1 hypothesis generation "
            "stay **MNQ-only** until one candidate clears gates, or expand to **ES/MES/RTY** "
            "(or options) earlier for diversification of tail behavior?"
        ),
    }

    out = {
        "wave": "0h",
        "git": meta_git,
        "protocol": {
            "start": _START.isoformat(),
            "end_inclusive": _END.isoformat(),
            "trade_log_closed_trades": n_trades,
            "unique_exit_ny_dates_with_trades": n_session_days,
            "max_trades_on_single_exit_ny_date": max_trades_day,
            "n_exit_ny_dates_with_multiple_trades": n_multi,
        },
        "deliverable_1_session_loss_distribution": {
            "aggregation": "sum(net_pnl) by exit_ny_date (America/New_York calendar), qty=1 MNQ",
            "n_losing_sessions": n_losing,
            "mean_session_pnl_losing_only": mean_loss,
            "median_session_pnl_losing_only": median_loss,
            "median_abs_session_loss_losing_only": median_abs,
            "max_single_session_loss_all_traded_days": max_loss,
            "abs_loss_percentiles_among_losing_sessions_usd": mag_pct,
            "tail_multiple_abs_percentile_over_median_abs": tail_multiples,
            "histogram_losing_sessions": {
                "n_bins": _HIST_BINS,
                "range": [float(np.min(losses)), 0.0] if n_losing else None,
                "counts": hist_counts,
                "bin_edges": hist_edges,
            },
        },
        "deliverable_1_apex_prelock_buffer_comparison": apex_rows,
        "stop_conditions": {
            "surface_if_p99_abs_session_loss_le_half_tdd_at_qty1_reference_50k": stop_surface,
            "interpretation_if_true": (
                "Tail at MNQ=1 is mild vs **$50K** pre-lock TDD — would contradict the usual "
                "single-session tail narrative; worth reconciling vs prior funded-sim path "
                "dependence before declaring close-out."
            ),
            "per_class_p99_abs_le_half_class_tdd": stop_flags,
        },
        "deliverable_4_wave1_operator_agenda": deliverable_4_operator_questions,
        "references": [
            "notebooks/validation/2026-05-17_wave0g_orb_opt3_2020_exclusion.md",
            "notebooks/validation/2026-05-17_wave0f_orb_opt3_failure_profile.json",
            "docs/orb_opt3_phase2_closeout.md",
        ],
    }

    out_path = (
        _REPO / "notebooks" / "validation" / "2026-05-17_wave0h_orb_opt3_chapter_closeout.json"
    )
    out_path.write_text(json.dumps(_json_safe(out), indent=2), encoding="utf-8")

    md_lines = [
        "# Wave 0h — ORB+Opt3 chapter close-out (session loss tail)",
        "",
        f"**Git:** `{meta_git['git_sha']}` dirty={meta_git['git_dirty']}",
        "",
        "## Deliverable 1 headline",
        "",
        f"- **Traded session days (unique exit NY date):** {n_session_days}",
        f"- **Losing sessions:** {n_losing}",
        f"- **99th pct abs loss (MNQ=1), USD:** {mag_pct.get('p99', float('nan')):.2f}",
        f"- **$50K TDD:** {_APEX_PRELOCK['50k']['trailing_dd_tdd']:.0f}; "
        f"half-TDD STOP reference: {0.5*_APEX_PRELOCK['50k']['trailing_dd_tdd']:.0f}",
        f"- **STOP surface (p99 ≤ half $50K TDD):** {stop_surface}",
        "",
        "See `docs/orb_opt3_phase2_closeout.md` for narrative + Phase 2 reframe.",
        "",
        f"Full JSON: `{out_path.name}`",
    ]
    md_path = out_path.with_suffix(".md")
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote_json": str(out_path),
                "wrote_md": str(md_path),
                "stop_surface": stop_surface,
            },
        ),
    )


if __name__ == "__main__":
    main()
