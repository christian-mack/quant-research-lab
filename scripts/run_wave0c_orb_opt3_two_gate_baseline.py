#!/usr/bin/env python3
"""Wave 0c — Correct $50K Apex two-phase rules; two-gate re-grade ORB+Opt3.

Usage (repo root, requires data/raw MNQ exports)::

    uv run python scripts/run_wave0c_orb_opt3_two_gate_baseline.py

Writes ``notebooks/validation/2026-05-17_wave0c_orb_opt3_two_gate_baseline.{md,json}``.
"""

from __future__ import annotations

# ruff: noqa: E402, E501
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

from quant_research.backtest import BacktestConfig, BacktestEngine, OrchestrationSpec, as_module
from quant_research.backtest.m6_metrics import compute_m6_aggregates, protocol_year_fraction
from quant_research.backtest.schema import empty_trade_log
from quant_research.data import continuous_contract, data_loader, session
from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.modules import OrbStrategy, production_orb_opt3_funded_params
from quant_research.statistics.apex_eod_trailing import (
    block_bootstrap_apex_50k_funded,
    simulate_apex_50k_eod_two_phase,
    simulate_eval_window_50k_eod,
    trades_to_daily_pnls_with_ny,
)

_CHI = ZoneInfo("America/Chicago")
_START = dt.date(2020, 1, 1)
_END = dt.date(2026, 4, 19)
_START_BALANCE = 50_000.0
_WIN_LEN = 30
_Q_RANGE = (1, 2, 3, 4, 5)
_BOOT_BLOCKS = (5, 20, 50)
_BOOT_IT = 10_000
_BOOT_SEED_BASE = 42
_BOOT_SURVIVAL_WARN = 0.80


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


def _margin_percentile_report(a: np.ndarray) -> dict[str, float]:
    x = np.asarray(a, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {}
    return {
        "p01": float(np.percentile(x, 1)),
        "p05": float(np.percentile(x, 5)),
        "p50": float(np.percentile(x, 50)),
        "p95": float(np.percentile(x, 95)),
        "p99": float(np.percentile(x, 99)),
    }


def main() -> None:
    root_raw = _REPO / "data" / "raw"
    if not any(root_raw.glob("MNQ *.Last.txt")):
        print("No MNQ contract files under data/raw; abort.", file=sys.stderr)
        sys.exit(2)

    meta_git = _git_meta(_REPO)
    raw = data_loader.load_all_contracts(root_raw)
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    rth = dated.filter(pl.col("session") == session.SESSION_RTH)

    ts0 = dt.datetime.combine(_START, dt.time.min).replace(tzinfo=_CHI)
    ts_end_excl = dt.datetime(2026, 4, 20, 0, 0, 0, tzinfo=_CHI)
    window = rth.filter(
        (pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts_end_excl),
    ).sort("timestamp")

    session_dates = window["cme_session_date"].drop_nulls().unique().sort().to_list()
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
    trades_sorted = enriched.sort("exit_time")
    exit_sess = trades_sorted["exit_cme_session_date"].to_list()
    exit_ny = trades_sorted["exit_ny_date"].to_list()
    pnls1 = trades_sorted["net_pnl"].to_numpy().astype(np.float64)
    exit_times_list = trades_sorted["exit_time"].to_list()

    _, daily_qty1, ny_daily = trades_to_daily_pnls_with_ny(exit_sess, exit_ny, pnls1)
    yfrac = protocol_year_fraction(_START, _END)
    m = compute_m6_aggregates(combined)

    funded_by_q: dict[str, dict[str, object]] = {}
    for q in _Q_RANGE:
        dq = daily_qty1 * float(q)
        fr = simulate_apex_50k_eod_two_phase(dq, ny_daily)
        funded_by_q[str(q)] = {
            "survived": fr.survived,
            "trail_breach_sessions": fr.trail_breach_sessions,
            "dll_fail": fr.dll_fail,
            "dll_failure_days": fr.dll_failure_days,
            "locked_achieved": fr.locked_achieved,
            "min_margin_pre_lock": fr.min_margin_pre_lock,
            "min_margin_post_lock": fr.min_margin_post_lock,
            "final_equity": fr.final_equity,
            "binding_session_index": fr.binding_session_index,
        }

    funded_passing = [q for q in _Q_RANGE if funded_by_q[str(q)]["survived"]]
    funded_q_max = max(funded_passing) if funded_passing else None

    stop_funded_q1 = not bool(funded_by_q["1"]["survived"])

    eval_by_q: dict[str, dict[str, object]] = {}
    exit_sess_list = exit_sess
    exit_ny_list = exit_ny

    for q in _Q_RANGE:
        scale = float(q)
        scaled = pnls1 * scale
        pass_c = 0
        fail_tr = 0
        fail_dll = 0
        fail_nt = 0
        total_w = 0
        if len(session_dates) >= _WIN_LEN:
            total_w = len(session_dates) - _WIN_LEN + 1
            for i0 in range(total_w):
                wdates = session_dates[i0 : i0 + _WIN_LEN]
                wset = {d for d in wdates if d is not None}
                mask = np.array([s in wset for s in exit_sess_list], dtype=bool)
                sub_p = scaled[mask]
                sub_ny = [exit_ny_list[j] for j in range(len(exit_ny_list)) if mask[j]]
                sub_sess = [exit_sess_list[j] for j in range(len(exit_sess_list)) if mask[j]]
                sub_et = [exit_times_list[j] for j in range(len(exit_times_list)) if mask[j]]
                order = np.argsort([sub_et[k] for k in range(len(sub_et))])
                sub_p = sub_p[order]
                sub_ny = [sub_ny[k] for k in order]
                sub_sess = [sub_sess[k] for k in order]
                r = simulate_eval_window_50k_eod(sub_p, sub_ny, sub_sess)
                if r["outcome"] == "pass":
                    pass_c += 1
                elif r["mode"] == "trailing_dd":
                    fail_tr += 1
                elif r["mode"] == "dll":
                    fail_dll += 1
                else:
                    fail_nt += 1

        eval_by_q[str(q)] = {
            "total_windows": total_w,
            "passing_windows": pass_c,
            "pass_rate": (pass_c / total_w) if total_w > 0 else float("nan"),
            "fail_trailing": fail_tr,
            "fail_dll": fail_dll,
            "fail_no_target": fail_nt,
        }

    stop_eval_all_zero = all(
        eval_by_q[str(q)]["passing_windows"] == 0 for q in _Q_RANGE
    ) and len(session_dates) >= _WIN_LEN

    bootstrap_by_q: dict[str, dict[str, object]] = {}
    stop_bootstrap_low = False
    for q in _Q_RANGE:
        for bl in _BOOT_BLOCKS:
            rng = np.random.default_rng(_BOOT_SEED_BASE + bl + q * 1000)
            b = block_bootstrap_apex_50k_funded(
                pnls1,
                exit_sess_list,
                exit_ny_list,
                quantity=float(q),
                block_len=bl,
                n_target_trades=len(pnls1),
                n_iterations=_BOOT_IT,
                rng=rng,
            )
            surv = b["survived"]
            frac = float(np.mean(surv.astype(np.float64)))
            min_pre = b["min_margin_pre_lock"]
            min_post = b["min_margin_post_lock"]
            post_fin = min_post[np.isfinite(min_post)]
            key = f"q{q}_block{bl}"
            bootstrap_by_q[key] = {
                "funded_survival_fraction": frac,
                "margin_pre_lock_percentiles": _margin_percentile_report(min_pre),
                "margin_post_lock_percentiles": _margin_percentile_report(post_fin),
                "worst_tail_labels": (
                    "p01/p05 = lower tail of min_margin (stress); "
                    "p95/p99 = upper tail (headroom)"
                ),
                "n_iterations": _BOOT_IT,
                "seed": _BOOT_SEED_BASE + bl + q * 1000,
            }
            if funded_q_max is not None and q == funded_q_max and frac < _BOOT_SURVIVAL_WARN:
                stop_bootstrap_low = True

    eval_at_funded = (
        eval_by_q[str(funded_q_max)] if funded_q_max is not None else None
    )

    q_graded = funded_q_max if funded_q_max is not None else 0
    ann_by_year = {
        str(y): round(m.years_calendar.get(y, 0.0) * q_graded, 2)
        for y in range(2020, 2027)
    }
    total_at_q = m.net_pnl_total * q_graded
    avg_annual_at_q = (total_at_q / yfrac) if yfrac > 0 else 0.0
    years_profitable = sum(
        1 for y in range(2020, 2027) if m.years_calendar.get(y, 0.0) * q_graded > 0
    )
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
        "wave": "0c",
        "git": meta_git,
        "apex_rules": {
            "account": "$50K EOD",
            "starting_balance": _START_BALANCE,
            "trail_dollars_pre_lock": 2000,
            "lock_high_water_equity": 52_000,
            "post_lock_static_floor": 50_000,
            "profit_target_equity": 53_000,
            "dll_limit": 1000,
            "dll_test": "ny_day_sum_pnl < -1000 (Wave 0 convention)",
        },
        "protocol": {
            "start": _START.isoformat(),
            "end_inclusive": _END.isoformat(),
            "trade_count_qty1": m.trade_count,
            "daily_sessions": len(daily_qty1),
        },
        "deliverable_1_two_gate": {
            "funded_survival_6y_daily_path": funded_by_q,
            "funded_q_max": funded_q_max,
            "funded_passing_quantities": funded_passing,
            "eval_rolling_30_session_windows": eval_by_q,
            "eval_window_spec": {
                "window_sessions": _WIN_LEN,
                "advance_sessions": 1,
                "partial_windows": "drop",
                "path": "trade_by_trade within window (same as Wave 0 eval driver)",
            },
        },
        "deliverable_2_bootstrap_funded_survival_all_q": bootstrap_by_q,
        "deliverable_3_eval_at_funded_q_max": eval_at_funded,
        "deliverable_4_graded_baseline_at_funded_q_max": {
            "funded_q_max": funded_q_max,
            "q_used_for_economics": q_graded,
            "total_pnl_scaled": total_at_q,
            "avg_annual_pnl": avg_annual_at_q,
            "annual_by_year_scaled": ann_by_year,
            "profitable_calendar_years_2020_2026": years_profitable,
            "tier_vs_36_60_100k": tier,
        },
        "stop_conditions": {
            "funded_survival_fails_qty1": stop_funded_q1,
            "eval_pass_rate_zero_all_q": stop_eval_all_zero,
            "bootstrap_funded_survival_below_80pct_at_funded_q_max": stop_bootstrap_low
            if funded_q_max is not None
            else False,
        },
        "grading_conclusion": {
            "funded_q_max": funded_q_max,
            "eval_pass_rate_at_funded_q_max": eval_at_funded["pass_rate"]
            if funded_q_max is not None
            else None,
        },
        "operator_notes": (
            "Wave 0 / 0b used **$3K** trailing and wrong lock semantics; see lessons log "
            "and docs. Wave 0b **breach counts** under legacy modes are not comparable to "
            "funded survival under these rules."
        ),
    }

    out_dir = _REPO / "notebooks" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "2026-05-17_wave0c_orb_opt3_two_gate_baseline.json"
    md_path = out_dir / "2026-05-17_wave0c_orb_opt3_two_gate_baseline.md"

    json_path.write_text(
        json.dumps(_json_safe(payload), indent=2, allow_nan=False),
        encoding="utf-8",
    )

    lines = []
    any_stop = stop_funded_q1 or stop_eval_all_zero or (
        stop_bootstrap_low if funded_q_max is not None else False
    )
    if any_stop:
        lines += [
            "# **OPERATOR — STOP CONDITIONS TRIGGERED (see end of note)**",
            "",
        ]
    lines += [
        "# Wave 0c — ORB+Opt3 two-gate baseline ($2K trail / $52K lock / $50K floor)",
        "",
        f"**Git SHA:** `{meta_git['git_sha']}`  ",
        f"**Dirty tree:** {meta_git['git_dirty']}  ",
        f"**Generated:** {dt.datetime.now(dt.UTC).isoformat()}  ",
        "",
        "## Apex rules (corrected)",
        "",
        "- **Start:** $50,000 — **pre-lock floor** trails as HWM − **$2,000** (initial floor $48,000).",
        "- **Lock:** when **high-water equity ≥ $52,000**, floor **locks at $50,000**.",
        "- **Profit target (eval):** account reaches **$53,000** (+$3,000).",
        "- **DLL:** NY calendar day realized sum **&lt; −$1,000** fails (same convention as Wave 0).",
        "",
        "## Deliverable 1 — Two gates (6y daily funded path vs 30-session eval windows)",
        "",
        "### Funded survival (chronological **session / daily** totals, scaled)",
        "",
        "| q | Survived | Trail breach sessions | DLL fail | Locked HWM≥$52K | Min margin pre | Min margin post |",
        "|---|----------|------------------------|----------|----------------|----------------|-----------------|",
    ]
    for q in _Q_RANGE:
        row = funded_by_q[str(q)]
        mpr = row["min_margin_post_lock"]
        post_s = "nan" if (isinstance(mpr, float) and math.isnan(mpr)) else f"{float(mpr):.2f}"
        lines.append(
            f"| {q} | {row['survived']} | {row['trail_breach_sessions']} | {row['dll_fail']} | "
            f"{row['locked_achieved']} | {row['min_margin_pre_lock']:.2f} | {post_s} |",
        )
    lines += [
        "",
        f"**Funded q_max (passing subset):** **{funded_q_max}**  ",
        "",
        "### Eval pass rate (trade-by-trade in each 30-session window)",
        "",
        "| q | Pass | Total windows | Pass rate |",
        "|---|------|---------------|-----------|",
    ]
    for q in _Q_RANGE:
        e = eval_by_q[str(q)]
        pr = e["pass_rate"]
        pr_s = f"{100 * pr:.2f}%" if pr == pr else "N/A"
        lines.append(
            f"| {q} | {e['passing_windows']} | {e['total_windows']} | {pr_s} |",
        )

    lines += [
        "",
        "## Deliverable 2 — Bootstrap funded survival (all q ∈ {1..5}, blocks 5 / 20 / 50)",
        "",
        "See JSON `deliverable_2_bootstrap_funded_survival_all_q`. Summary for **funded q_max**:",
        "",
    ]
    if funded_q_max is not None:
        lines.extend(
            [
                "| Block | Survival frac | pre p01 | pre p95 | pre p99 |",
                "|-------|---------------|---------|---------|---------|",
            ],
        )
        for bl in _BOOT_BLOCKS:
            key = f"q{funded_q_max}_block{bl}"
            b = bootstrap_by_q.get(key)
            if b:
                mp = b["margin_pre_lock_percentiles"]
                lines.append(
                    f"| {bl} | {b['funded_survival_fraction']:.4f} | "
                    f"{mp.get('p01', float('nan')):.2f} | {mp.get('p95', float('nan')):.2f} | "
                    f"{mp.get('p99', float('nan')):.2f} |",
                )
    else:
        lines.append("*No funded q_max — still ran bootstrap for all q (JSON).*")

    lines += ["", "### Grading pair (funded_q_max, eval pass rate at that q)", ""]
    if funded_q_max is None:
        lines.append("- **(None, N/A)** — no quantity passes funded survival on the 6y path.")
    else:
        ef = eval_by_q[str(funded_q_max)]
        pr = ef["pass_rate"]
        pr_s = f"{100 * pr:.2f}%" if pr == pr else "N/A"
        lines.append(
            f"- **({funded_q_max}, {pr_s})** — see Deliverable 3 for window counts.",
        )

    lines += [
        "",
        "## Deliverable 3 — Eval pass rate at funded q_max",
        "",
    ]
    if eval_at_funded is None:
        lines.append("*No funded-passing q — N/A.*")
    else:
        ef = eval_at_funded
        pr = ef["pass_rate"]
        pr_s = f"{100 * pr:.2f}%" if pr == pr else "N/A"
        lines.append(
            f"- **Passing windows:** {ef['passing_windows']} / {ef['total_windows']} (**{pr_s}**)",
        )

    lines += [
        "",
        "## Deliverable 4 — Graded economics at funded q_max",
        "",
        f"- **q used:** {q_graded} (0 if no funded-passing qty)",
        f"- **Avg annual P&amp;L:** ${avg_annual_at_q:,.2f}",
        f"- **Tier:** {tier}",
        f"- **Profitable years (2020–2026):** {years_profitable} / 7",
        "",
        "## STOP flags (from JSON `stop_conditions`)",
        "",
        f"- **Funded fails q=1:** {stop_funded_q1}",
        f"- **Eval 0% all q:** {stop_eval_all_zero}",
        f"- **Bootstrap survival &lt; 80% at funded q_max:** "
        f"{stop_bootstrap_low if funded_q_max is not None else False}",
        "",
        f"Full JSON: `{json_path.name}`",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"wrote_md": str(md_path), "wrote_json": str(json_path)}, indent=2))


if __name__ == "__main__":
    main()
