#!/usr/bin/env python3
"""Wave 0d — DLL session-pause fix + Apex EOD account-class survey (ORB+Opt3).

Usage (repo root, requires data/raw MNQ exports)::

    uv run python scripts/run_wave0d_orb_opt3_account_class_survey.py

Writes ``notebooks/validation/2026-05-13_wave0d_orb_opt3_account_class_survey.{md,json}``.
"""

from __future__ import annotations

# ruff: noqa: E402, E501
import datetime as dt
import json
import math
import subprocess
import sys
from dataclasses import dataclass, replace
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
    block_bootstrap_apex_eod_funded,
    simulate_apex_50k_eod_two_phase,
    simulate_apex_eod_two_phase,
    simulate_eval_window_50k_eod,
    simulate_eval_window_eod,
    trades_to_daily_pnls_with_ny,
)

_CHI = ZoneInfo("America/Chicago")
_START = dt.date(2020, 1, 1)
_END = dt.date(2026, 4, 19)
_WIN_LEN = 30
_BOOT_BLOCK = 20
_BOOT_IT = 10_000
_BOOT_SEED_BASE = 42
_TIER_FLOOR = 36_000.0
_TIER_TARGET = 60_000.0
_TIER_STRETCH = 100_000.0
_EVAL_MEANINGFUL = 0.50
_BOOT_OK = 0.80


@dataclass(frozen=True, slots=True)
class ApexSurveyAccount:
    """Operator Wave 0d table + eval contract cap from secondary verification."""

    key: str
    label: str
    starting_balance: float
    trailing_dd: float
    profit_target: float
    dll_limit: float
    pa_max_contracts: int
    eval_max_contracts: int


# Operator sizing row (trailing / target / DLL / PA max). Eval max from PTV 2026-03
# “4.0” blogging table; flagged in JSON ``verification`` vs help center.
ACCOUNTS: tuple[ApexSurveyAccount, ...] = (
    ApexSurveyAccount("25k", "$25K EOD", 25_000, 1_500, 1_500, 500, 4, 4),
    ApexSurveyAccount("50k", "$50K EOD", 50_000, 2_000, 3_000, 1_000, 10, 6),
    ApexSurveyAccount("100k", "$100K EOD", 100_000, 2_500, 6_000, 1_500, 14, 8),
    ApexSurveyAccount("150k", "$150K EOD", 150_000, 3_000, 9_000, 2_000, 17, 12),
)


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
        pl.col("exit_time")
        .dt.convert_time_zone("America/New_York")
        .dt.date()
        .alias("exit_ny_date"),
    )["exit_ny_date"]
    return trade_log.with_columns(
        stamped["cme_session_date"].alias("exit_cme_session_date"),
        ny_date,
    )


def _tier(avg_annual: float) -> str:
    if avg_annual >= _TIER_STRETCH:
        return "stretch_or_above"
    if avg_annual >= _TIER_TARGET:
        return "target_band"
    if avg_annual >= _TIER_FLOOR:
        return "floor_band"
    return "below_floor"


def _sim_kw(acct: ApexSurveyAccount) -> dict[str, float | None]:
    sb = float(acct.starting_balance)
    tr = float(acct.trailing_dd)
    return {
        "starting_balance": sb,
        "trailing_dd": tr,
        "dll_limit": float(acct.dll_limit),
        "lock_equity_threshold": sb + tr,
        "post_lock_floor": sb,
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
    enriched = _append_exit_session_columns(combined)
    trades_sorted = enriched.sort("exit_time")
    exit_sess = trades_sorted["exit_cme_session_date"].to_list()
    exit_ny = trades_sorted["exit_ny_date"].to_list()
    pnls1 = trades_sorted["net_pnl"].to_numpy().astype(np.float64)
    exit_times_list = trades_sorted["exit_time"].to_list()
    exit_sess_list = exit_sess
    exit_ny_list = exit_ny

    _, daily_qty1, ny_daily = trades_to_daily_pnls_with_ny(exit_sess, exit_ny, pnls1)
    yfrac = protocol_year_fraction(_START, _END)
    m = compute_m6_aggregates(combined)

    # --- Wave 0c regression ($50K q=1): terminal DLL vs session-pause ---
    dq1 = daily_qty1 * 1.0
    fr_term = simulate_apex_50k_eod_two_phase(dq1, ny_daily, dll_terminates_run=True)
    fr_pause = simulate_apex_50k_eod_two_phase(dq1, ny_daily, dll_terminates_run=False)
    pass_t = pass_p = 0
    total_w = 0
    if len(session_dates) >= _WIN_LEN:
        total_w = len(session_dates) - _WIN_LEN + 1
        for i0 in range(total_w):
            wdates = session_dates[i0 : i0 + _WIN_LEN]
            wset = {d for d in wdates if d is not None}
            mask = np.array([s in wset for s in exit_sess_list], dtype=bool)
            sub_p = pnls1[mask]
            sub_ny = [exit_ny_list[j] for j in range(len(exit_ny_list)) if mask[j]]
            sub_sess = [exit_sess_list[j] for j in range(len(exit_sess_list)) if mask[j]]
            sub_et = [exit_times_list[j] for j in range(len(exit_times_list)) if mask[j]]
            order = np.argsort([sub_et[k] for k in range(len(sub_et))])
            sub_p = sub_p[order]
            sub_ny = (np.array(sub_ny)[order]).tolist()
            sub_sess = (np.array(sub_sess, dtype=object)[order]).tolist()
            if (
                simulate_eval_window_50k_eod(sub_p, sub_ny, sub_sess, dll_terminates_run=True)[
                    "outcome"
                ]
                == "pass"
            ):
                pass_t += 1
            if (
                simulate_eval_window_50k_eod(sub_p, sub_ny, sub_sess, dll_terminates_run=False)[
                    "outcome"
                ]
                == "pass"
            ):
                pass_p += 1
    rate_t = (pass_t / total_w) if total_w else float("nan")
    rate_p = (pass_p / total_w) if total_w else float("nan")
    rel_eval = (
        float("inf")
        if total_w > 0 and pass_t == 0 and pass_p > 0
        else (abs(rate_p - rate_t) / rate_t if rate_t and rate_t > 0 else 0.0)
    )
    wave0c_surface = (fr_term.survived != fr_pause.survived) or (total_w > 0 and rel_eval > 0.20)

    by_class: dict[str, dict[str, object]] = {}
    joint_candidates: list[dict[str, object]] = []

    for acct in ACCOUNTS:
        sk = _sim_kw(acct)
        qb_max = acct.pa_max_contracts
        funded_rows: dict[str, dict[str, object]] = {}
        eval_rows: dict[str, dict[str, object]] = {}

        for q in range(1, qb_max + 1):
            dq = daily_qty1 * float(q)
            fr = simulate_apex_eod_two_phase(dq, ny_daily, **sk)
            avg_dll_days = float(fr.dll_failure_days) / yfrac if yfrac > 0 else 0.0
            funded_rows[str(q)] = {
                "survived": fr.survived,
                "trail_breach_sessions": fr.trail_breach_sessions,
                "dll_fail": fr.dll_fail,
                "dll_pause_days": fr.dll_failure_days,
                "avg_dll_pause_days_per_year": round(avg_dll_days, 4),
                "locked_achieved": fr.locked_achieved,
                "final_equity": fr.final_equity,
            }

            rng = np.random.default_rng(
                _BOOT_SEED_BASE + sum(ord(c) for c in acct.key) * 97 + q * 1_000,
            )
            b = block_bootstrap_apex_eod_funded(
                pnls1,
                exit_sess_list,
                exit_ny_list,
                quantity=float(q),
                block_len=_BOOT_BLOCK,
                n_target_trades=len(pnls1),
                n_iterations=_BOOT_IT,
                rng=rng,
                starting_balance=sk["starting_balance"],
                trailing_dd=sk["trailing_dd"],
                dll_limit=sk["dll_limit"],
                lock_equity_threshold=sk["lock_equity_threshold"],
                post_lock_floor=sk["post_lock_floor"],
                enforce_dll=True,
                dll_terminates_run=False,
            )
            frac = float(np.mean(b["survived"].astype(np.float64)))
            funded_rows[str(q)]["bootstrap_funded_survival_fraction_block20"] = frac

        funded_passing = [q for q in range(1, qb_max + 1) if funded_rows[str(q)]["survived"]]
        funded_q_max = max(funded_passing) if funded_passing else None

        for q in range(1, qb_max + 1):
            pass_c = fail_tr = fail_nt = 0
            total_we = 0
            if len(session_dates) >= _WIN_LEN:
                total_we = len(session_dates) - _WIN_LEN + 1
                for i0 in range(total_we):
                    wdates = session_dates[i0 : i0 + _WIN_LEN]
                    wset = {d for d in wdates if d is not None}
                    wmask = np.array([s in wset for s in exit_sess_list], dtype=bool)
                    sub_p = pnls1[wmask] * float(q)
                    sub_ny = [exit_ny_list[j] for j in range(len(exit_ny_list)) if wmask[j]]
                    sub_sess = [exit_sess_list[j] for j in range(len(exit_sess_list)) if wmask[j]]
                    sub_et = [exit_times_list[j] for j in range(len(exit_times_list)) if wmask[j]]
                    order = np.argsort([sub_et[k] for k in range(len(sub_et))])
                    sub_p = sub_p[order]
                    sub_ny = (np.array(sub_ny)[order]).tolist()
                    sub_sess = (np.array(sub_sess, dtype=object)[order]).tolist()
                    r = simulate_eval_window_eod(
                        sub_p,
                        sub_ny,
                        sub_sess,
                        starting_balance=acct.starting_balance,
                        trailing_dd=acct.trailing_dd,
                        profit_target=acct.profit_target,
                        dll_limit=acct.dll_limit,
                        lock_equity_threshold=acct.starting_balance + acct.trailing_dd,
                        post_lock_floor=acct.starting_balance,
                    )
                    if r["outcome"] == "pass":
                        pass_c += 1
                    elif r["mode"] == "trailing_dd":
                        fail_tr += 1
                    else:
                        fail_nt += 1

            pr = (pass_c / total_we) if total_we else float("nan")
            eval_rows[str(q)] = {
                "total_windows": total_we,
                "passing_windows": pass_c,
                "pass_rate": pr,
                "fail_trailing": fail_tr,
                "fail_no_target": fail_nt,
                "within_eval_contract_cap": q <= acct.eval_max_contracts,
            }

        ann_at = {}
        tier_at = {}
        for q in range(1, qb_max + 1):
            total_at_q = m.net_pnl_total * q
            avg_ann = (total_at_q / yfrac) if yfrac > 0 else 0.0
            ann_at[str(q)] = round(avg_ann, 2)
            tier_at[str(q)] = _tier(avg_ann)

        fq = funded_q_max
        ev_at_max = eval_rows[str(fq)]["pass_rate"] if fq is not None else float("nan")
        boot_at_max = (
            funded_rows[str(fq)]["bootstrap_funded_survival_fraction_block20"]
            if fq is not None
            else None
        )

        by_class[acct.key] = {
            "label": acct.label,
            "apex_params": {
                "starting_balance": acct.starting_balance,
                "trailing_dd": acct.trailing_dd,
                "profit_target": acct.profit_target,
                "dll_limit": acct.dll_limit,
                "lock_equity_high_water": acct.starting_balance + acct.trailing_dd,
                "post_lock_floor": acct.starting_balance,
                "pa_max_contracts": acct.pa_max_contracts,
                "eval_max_contracts_reported": acct.eval_max_contracts,
            },
            "funded_by_qty": funded_rows,
            "eval_by_qty": eval_rows,
            "annual_avg_pnl_by_qty": ann_at,
            "tier_by_qty": tier_at,
            "summary": {
                "funded_q_max": funded_q_max,
                "eval_pass_rate_at_funded_q_max": ev_at_max,
                "bootstrap_survival_at_funded_q_max": boot_at_max,
                "annual_pnl_at_funded_q_max": ann_at[str(fq)] if fq else None,
                "avg_dll_pause_days_per_year_at_funded_q_max": (
                    funded_rows[str(fq)]["avg_dll_pause_days_per_year"] if fq else None
                ),
                "tier_at_funded_q_max": tier_at[str(fq)] if fq else None,
            },
        }

        for q in range(1, qb_max + 1):
            row = funded_rows[str(q)]
            evr = eval_rows[str(q)]["pass_rate"]
            boot = row["bootstrap_funded_survival_fraction_block20"]
            if not row["survived"]:
                continue
            fails = []
            if boot < _BOOT_OK:
                fails.append("bootstrap_lt_80pct")
            if evr < _EVAL_MEANINGFUL:
                fails.append("eval_lt_50pct")
            joint_candidates.append(
                {
                    "account_class": acct.key,
                    "q": q,
                    "avg_annual_pnl": ann_at[str(q)],
                    "bootstrap_survival": boot,
                    "eval_pass_rate": evr,
                    "within_eval_contract_cap": q <= acct.eval_max_contracts,
                    "meets_all_three_gates": bool(
                        row["survived"] and boot >= _BOOT_OK and evr >= _EVAL_MEANINGFUL
                    ),
                    "gate_failures_if_any": fails,
                },
            )

    any_bootstrap_80 = False
    for acct in ACCOUNTS:
        for q in range(1, acct.pa_max_contracts + 1):
            row = by_class[acct.key]["funded_by_qty"][str(q)]
            if row["survived"] and row["bootstrap_funded_survival_fraction_block20"] >= _BOOT_OK:
                any_bootstrap_80 = True
                break
        if any_bootstrap_80:
            break

    best_joint = [c for c in joint_candidates if c["meets_all_three_gates"]]
    best_joint.sort(key=lambda x: float(x["avg_annual_pnl"]), reverse=True)
    no_triple_pass = len(best_joint) == 0

    verification = {
        "primary_official_source": "https://apextraderfunding.com/help-center/",
        "secondary_blog_verify_2026_03": (
            "PropTradingVibes / community tables (March 2026 4.0 summaries) — "
            "**not** a substitute for the help center."
        ),
        "operator_simulation_row": [
            {
                "class": a.key,
                "trailing_dd": a.trailing_dd,
                "profit_target": a.profit_target,
                "dll": a.dll_limit,
                "pa_cap": a.pa_max_contracts,
                "eval_cap_secondary_source": a.eval_max_contracts,
            }
            for a in ACCOUNTS
        ],
        "deltas_vs_blog_table": [
            "$25K: third-party trailing **$1,000** (not **$1,500**) on some 4.0 summaries — "
            "operator row uses **$1,500**; confirm on Apex help center.",
            "$100K: third-party trailing **$3,000** vs operator **$2,500** — confirm.",
            "$150K: third-party trailing **$4,000** vs operator **$3,000** — confirm.",
            "$50K PA max contracts: third-party **4** vs operator **10** — likely **definition/version** mismatch; confirm max PA size for your product SKU.",
        ],
    }

    stop_flags = {
        "wave0c_material_regression_dll_semantics": wave0c_surface,
        "no_joint_pass_funded_bootstrap80_eval50": no_triple_pass,
        "no_funded_qty_reaches_bootstrap_80pct_any_class": not any_bootstrap_80,
        "wave0c_regression_detail": {
            "funded_survived_terminal": fr_term.survived,
            "funded_survived_pause": fr_pause.survived,
            "eval_passes_terminal_q1": pass_t,
            "eval_passes_pause_q1": pass_p,
            "eval_rates": {"terminal": rate_t, "pause": rate_p},
            "rel_eval_rate_change_vs_terminal": rel_eval,
        },
    }

    payload: dict[str, object] = {
        "wave": "0d",
        "git": meta_git,
        "verification": verification,
        "protocol": {
            "start": _START.isoformat(),
            "end_inclusive": _END.isoformat(),
            "trade_count_qty1": m.trade_count,
            "daily_sessions": len(daily_qty1),
            "yfrac": yfrac,
        },
        "dll_model": "session_pause_per_NY_day_strict_below_neg_dll_limit",
        "deliverable_account_survey": by_class,
        "joint_criteria_scan": {
            "gates": {
                "funded_survival": True,
                "bootstrap_survival_min": _BOOT_OK,
                "eval_pass_rate_min": _EVAL_MEANINGFUL,
            },
            "meets_all_gates": best_joint[:10],
            "closest_candidates_top15_by_pnl": sorted(
                joint_candidates,
                key=lambda x: float(x["avg_annual_pnl"]),
                reverse=True,
            )[:15],
        },
        "stop_conditions": stop_flags,
    }

    out_dir = _REPO / "notebooks" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "2026-05-13_wave0d_orb_opt3_account_class_survey.json"
    md_path = out_dir / "2026-05-13_wave0d_orb_opt3_account_class_survey.md"

    json_path.write_text(
        json.dumps(_json_safe(payload), indent=2, allow_nan=False),
        encoding="utf-8",
    )

    lines = [
        "# Wave 0d — DLL session-pause + Apex EOD account-class survey (ORB+Opt3)",
        "",
        f"**Git SHA:** `{meta_git['git_sha']}`  ",
        f"**Dirty tree:** {meta_git['git_dirty']}  ",
        f"**Generated:** {dt.datetime.now(dt.UTC).isoformat()}  ",
        "",
        "## Parameter verification",
        "",
        "See JSON `verification` for operator row vs third-party deltas (confirm on "
        "[Apex Help Center](https://apextraderfunding.com/help-center/)).",
        "",
        "## Summary table (by account class)",
        "",
        "| Class | funded_q_max | eval@q_max | boot@q_max | $/yr@q_max | DLL pauses/yr@q_max | tier |",
        "|-------|-------------|------------|------------|------------|---------------------|------|",
    ]
    for acct in ACCOUNTS:
        s = by_class[acct.key]["summary"]
        fq = s["funded_q_max"]
        if fq is None:
            lines.append(
                f"| {acct.key} | — | — | — | — | — | — |",
            )
            continue
        lines.append(
            f"| {acct.key} | {fq} | {float(s['eval_pass_rate_at_funded_q_max']):.2%} | "
            f"{s['bootstrap_survival_at_funded_q_max']:.4f} | "
            f"${s['annual_pnl_at_funded_q_max']} | "
            f"{s['avg_dll_pause_days_per_year_at_funded_q_max']} | "
            f"{s['tier_at_funded_q_max']} |",
        )

    lines += [
        "",
        "## Joint criteria (funded + bootstrap ≥ 80% + eval ≥ 50%)",
        "",
    ]
    if best_joint:
        lines.append("**Combinations meeting all three gates (top 10 by $/yr):**")
        for c in best_joint[:10]:
            lines.append(
                f"- **{c['account_class']}** q={c['q']}: **${c['avg_annual_pnl']}/yr**, "
                f"bootstrap={c['bootstrap_survival']:.3f}, eval={c['eval_pass_rate']:.2%}",
            )
    else:
        lines.append(
            "**None** — see JSON `joint_criteria_scan.closest_candidates_top15_by_pnl` "
            "for nearest misses and gate failures.",
        )

    lines += [
        "",
        "## STOP / flags (see JSON `stop_conditions`)",
        "",
        f"- **Wave 0c material DLL regression (survival or >20% eval rate change q=1):** "
        f"{stop_flags['wave0c_material_regression_dll_semantics']}",
        f"- **No triple-gate pass:** {stop_flags['no_joint_pass_funded_bootstrap80_eval50']}",
        f"- **No funded-passing qty reaches bootstrap ≥ 80% (any class):** "
        f"{stop_flags['no_funded_qty_reaches_bootstrap_80pct_any_class']}",
        "",
        "## Wave 0c terminal-vs-pause ( $50K, q=1 )",
        "",
        f"- Funded survived — terminal: **{fr_term.survived}**, pause: **{fr_pause.survived}**",
        f"- Eval passes (30-sess windows) — terminal: **{pass_t}**, pause: **{pass_p}** / {total_w}",
        f"- |Δ eval rate| / terminal rate: **{rel_eval}**",
        "",
        f"Full JSON: `{json_path.name}`",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"wrote_md": str(md_path), "wrote_json": str(json_path)}, indent=2))


if __name__ == "__main__":
    main()
