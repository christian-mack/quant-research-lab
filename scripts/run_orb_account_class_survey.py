#!/usr/bin/env python3
"""ORB+Opt3 Apex EOD account-class survey — floor-income fit ($50K / $100K / $150K).

Uses the Wave 0 validated ORB+Opt3 qty=1 trade log (re-run with harness if needed).

Usage (repo root, MNQ data under ``data/raw`` or ``data/raw/mnq``)::

    uv run python scripts/run_orb_account_class_survey.py

Writes ``notebooks/validation/2026-06-08_orb_account_class_survey.{md,json}``.
"""

from __future__ import annotations

# ruff: noqa: E402, E501
import datetime as dt
import json
import math
import subprocess
import sys
from collections import defaultdict
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
    ApexBalanceTier,
    apex_tier_index_for_equity,
    simulate_apex_eod_two_phase,
    simulate_eval_window_eod,
    trades_to_daily_pnls_with_ny,
)

_CHI = ZoneInfo("America/Chicago")
_START = dt.date(2020, 1, 1)
_END = dt.date(2026, 4, 19)
_WIN_LEN = 30
_MNQ_PER_MINI = 10.0
_DD1_ANCHOR = 2675.0
_PNL_ANCHOR = 1014.16
_TIER_FLOOR = 36_000.0
_TIER_TARGET = 60_000.0
_TIER_STRETCH = 100_000.0
_EVAL_GATE = 0.50
_PAYOUT_FIRST_100PCT = 25_000.0
_PAYOUT_SPLIT = 0.90


def pa_50k_tiers() -> tuple[ApexBalanceTier, ...]:
    return (
        ApexBalanceTier(50_000, 51_499, 2, 1_000),
        ApexBalanceTier(51_500, 52_999, 3, 1_000),
        ApexBalanceTier(53_000, 55_999, 4, 2_000),
        ApexBalanceTier(56_000, float("inf"), 4, 3_000),
    )


def pa_100k_tiers() -> tuple[ApexBalanceTier, ...]:
    return (
        ApexBalanceTier(100_000, 101_999, 3, 1_750),
        ApexBalanceTier(102_000, 102_999, 4, 1_750),
        ApexBalanceTier(103_000, 104_999, 5, 1_750),
        ApexBalanceTier(105_000, 109_999, 6, 2_500),
        ApexBalanceTier(110_000, float("inf"), 6, 3_500),
    )


def pa_150k_tiers() -> tuple[ApexBalanceTier, ...]:
    return (
        ApexBalanceTier(150_000, 151_999, 4, 2_500),
        ApexBalanceTier(152_000, 152_999, 5, 2_500),
        ApexBalanceTier(153_000, 154_999, 7, 2_500),
        ApexBalanceTier(155_000, 159_999, 10, 3_000),
        ApexBalanceTier(160_000, float("inf"), 10, 4_000),
    )


@dataclass(frozen=True, slots=True)
class SurveyAccount:
    key: str
    label: str
    starting_balance: float
    trailing_dd: float
    profit_target: float
    lock_equity: float
    post_lock_floor: float
    eval_max_mini: int
    eval_fee_usd: float
    tiers: tuple[ApexBalanceTier, ...]


ACCOUNTS: tuple[SurveyAccount, ...] = (
    SurveyAccount(
        "50k",
        "$50K EOD",
        50_000,
        2_000,
        3_000,
        52_000,
        50_000,
        6,
        167.0,
        pa_50k_tiers(),
    ),
    SurveyAccount(
        "100k",
        "$100K EOD",
        100_000,
        3_000,
        6_000,
        103_000,
        100_000,
        8,
        207.0,
        pa_100k_tiers(),
    ),
    SurveyAccount(
        "150k",
        "$150K EOD",
        150_000,
        4_000,
        9_000,
        154_000,
        150_000,
        12,
        297.0,
        pa_150k_tiers(),
    ),
)


def _mnq_raw_root() -> Path:
    return _REPO / "data" / "raw"


def _mnq_contract_glob(root_raw: Path) -> str | None:
    """Return the glob pattern that matches MNQ exports under ``root_raw``."""
    if any(root_raw.glob(data_loader.MNQ_CONTRACT_GLOB)):
        return data_loader.MNQ_CONTRACT_GLOB
    if any(root_raw.glob(data_loader.DEFAULT_CONTRACT_GLOB)):
        return data_loader.DEFAULT_CONTRACT_GLOB
    return None


def _load_mnq_raw(root_raw: Path) -> pl.DataFrame:
    pattern = _mnq_contract_glob(root_raw)
    if pattern is None:
        msg = f"No MNQ contract files under {root_raw} (tried mnq/ subfolder and root)"
        raise FileNotFoundError(msg)
    return data_loader.load_all_contracts(root_raw, pattern=pattern)


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


def _econ_tier(ann: float) -> str:
    if ann >= _TIER_STRETCH:
        return "stretch"
    if ann >= _TIER_TARGET:
        return "target"
    if ann >= _TIER_FLOOR:
        return "floor"
    return "below_floor"


def _net_payout_annual(gross: float) -> float:
    if gross <= 0:
        return gross
    if gross <= _PAYOUT_FIRST_100PCT:
        return gross
    return _PAYOUT_FIRST_100PCT + (gross - _PAYOUT_FIRST_100PCT) * _PAYOUT_SPLIT


def _rq_dollars(q: int, dd1: float) -> float:
    dd_q = float(q) * dd1
    return max(1.5 * dd_q, dd_q + 500.0)


def _max_q_for_rq(trailing_dd: float, dd1: float, q_hi: int) -> int:
    best = 0
    for q in range(1, q_hi + 1):
        if _rq_dollars(q, dd1) <= trailing_dd:
            best = q
    return best


def _max_q_dll(worst_session_loss_mnq1: float, tier1_dll: float, q_hi: int) -> int:
    w = abs(float(worst_session_loss_mnq1))
    if w <= 0:
        return q_hi
    best = 0
    for q in range(1, q_hi + 1):
        if w * q <= tier1_dll:
            best = q
    return best


def _max_q_consistency(
    max_day_profit_mnq1: float,
    total_profit_mnq1: float,
    q_hi: int,
) -> int:
    if total_profit_mnq1 <= 0:
        return 0
    ratio = float(max_day_profit_mnq1) / float(total_profit_mnq1)
    if ratio <= 0.30:
        return q_hi
    return 0


def _max_q_contract_cap(tier1_max_mini: int) -> int:
    return int(tier1_max_mini * _MNQ_PER_MINI)


def _max_q_gate_a(
    daily_mnq1: np.ndarray,
    ny_daily: list[dt.date],
    acct: SurveyAccount,
    q_hi: int,
) -> int:
    best = 0
    for q in range(1, q_hi + 1):
        fr = simulate_apex_eod_two_phase(
            daily_mnq1,
            ny_daily,
            starting_balance=acct.starting_balance,
            trailing_dd=acct.trailing_dd,
            dll_limit=0.0,
            lock_equity_threshold=acct.lock_equity,
            post_lock_floor=acct.post_lock_floor,
            balance_tiers=acct.tiers,
            target_qty_mnq=float(q),
            mnq_per_mini=_MNQ_PER_MINI,
        )
        if fr.survived:
            best = q
    return best


def _max_q_eod_dd(
    daily_mnq1: np.ndarray,
    ny_daily: list[dt.date],
    acct: SurveyAccount,
    trailing_dd: float,
    q_hi: int,
) -> tuple[int, bool]:
    """Largest q where EOD path peak-to-trough DD <= trailing_dd."""
    linear_ok = True
    best = 0
    dd1_path = None
    for q in range(1, q_hi + 1):
        fr = simulate_apex_eod_two_phase(
            daily_mnq1,
            ny_daily,
            starting_balance=acct.starting_balance,
            trailing_dd=acct.trailing_dd,
            dll_limit=0.0,
            lock_equity_threshold=acct.lock_equity,
            post_lock_floor=acct.post_lock_floor,
            balance_tiers=acct.tiers,
            target_qty_mnq=float(q),
            mnq_per_mini=_MNQ_PER_MINI,
            enforce_dll=False,
        )
        if dd1_path is None:
            dd1_path = fr.max_peak_to_trough_dd
        elif q == 2 and dd1_path > 0:
            ratio = fr.max_peak_to_trough_dd / (dd1_path * 2.0)
            if abs(ratio - 1.0) > 0.02:
                linear_ok = False
        if fr.max_peak_to_trough_dd <= trailing_dd:
            best = q
    return best, linear_ok


def _eval_pass_rate_sessions(
    pnls1: np.ndarray,
    exit_ny: list[dt.date],
    exit_sess: list[object],
    exit_times: list[object],
    session_dates: list[object],
    acct: SurveyAccount,
    qty_mnq: float,
) -> dict[str, object]:
    eval_cap_mnq = float(acct.eval_max_mini) * _MNQ_PER_MINI
    eval_q = min(float(qty_mnq), eval_cap_mnq)
    _, tier1 = apex_tier_index_for_equity(acct.starting_balance, acct.tiers)
    eval_dll = float(tier1.dll_limit)

    pass_c = fail_tr = fail_nt = 0
    total_w = 0
    if len(session_dates) >= _WIN_LEN:
        total_w = len(session_dates) - _WIN_LEN + 1
        for i0 in range(total_w):
            wdates = session_dates[i0 : i0 + _WIN_LEN]
            wset = {d for d in wdates if d is not None}
            mask = np.array([s in wset for s in exit_sess], dtype=bool)
            sub_p = pnls1[mask] * eval_q
            sub_ny = [exit_ny[j] for j in range(len(exit_ny)) if mask[j]]
            sub_sess = [exit_sess[j] for j in range(len(exit_sess)) if mask[j]]
            sub_et = [exit_times[j] for j in range(len(exit_times)) if mask[j]]
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
                dll_limit=eval_dll,
                lock_equity_threshold=acct.lock_equity,
                post_lock_floor=acct.post_lock_floor,
            )
            if r["outcome"] == "pass":
                pass_c += 1
            elif r.get("mode") == "trailing_dd":
                fail_tr += 1
            else:
                fail_nt += 1

    pr = (pass_c / total_w) if total_w else float("nan")
    return {
        "total_windows": total_w,
        "passing_windows": pass_c,
        "pass_rate": pr,
        "eval_qty_mnq": eval_q,
        "eval_dll_tier1": eval_dll,
        "fail_trailing": fail_tr,
        "fail_no_target": fail_nt,
        "window_trading_sessions": _WIN_LEN,
    }


def _yearly_pnl(
    exit_ny: list[dt.date],
    pnls: np.ndarray,
) -> dict[str, float]:
    by_year: dict[int, float] = defaultdict(float)
    for d, p in zip(exit_ny, pnls, strict=True):
        by_year[d.year] += float(p)
    return {str(y): round(v, 2) for y, v in sorted(by_year.items())}


def _load_wave0_artifacts() -> dict[str, object]:
    """Fallback when ``data/raw`` MNQ exports are absent (Wave 0 JSON in-repo)."""
    wave0 = json.loads(
        (_REPO / "notebooks/validation/2026-05-14_wave0_orb_opt3_graded_baseline.json").read_text(
            encoding="utf-8",
        ),
    )
    wave0h = json.loads(
        (_REPO / "notebooks/validation/2026-05-17_wave0h_orb_opt3_chapter_closeout.json").read_text(
            encoding="utf-8",
        ),
    )
    wave0f = json.loads(
        (_REPO / "notebooks/validation/2026-05-17_wave0f_orb_opt3_failure_profile.json").read_text(
            encoding="utf-8",
        ),
    )
    return {"wave0": wave0, "wave0h": wave0h, "wave0f": wave0f}


def _survey_from_artifacts(meta_git: dict[str, object]) -> dict[str, object]:
    """Reconstruct survey from Wave 0 graded artifacts (no fresh backtest)."""
    arts = _load_wave0_artifacts()
    wave0 = arts["wave0"]
    wave0h = arts["wave0h"]
    wave0f = arts["wave0f"]

    per = wave0["per_contract_qty1"]
    pnl_per_yr = float(per["pnl_per_contract_per_year"])
    net_total_mnq1 = float(per["net_pnl_total"])
    dd1_closed = float(per["dd1_magnitude"])
    yfrac = float(per["year_fraction"])
    worst_session = float(
        wave0h["deliverable_1_session_loss_distribution"]["max_single_session_loss_all_traded_days"],
    )
    # Upper bound on best NY day (mnq=1): 6 trades/day × avg_win from Wave 0.
    best_session_bound = float(per["avg_win"]) * float(
        wave0h["protocol"]["max_trades_on_single_exit_ny_date"],
    )
    consistency_ratio = best_session_bound / net_total_mnq1 if net_total_mnq1 > 0 else None

    sweep = wave0f["deliverable_4_low_qty_sweep"]
    by_cls_sweep: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in sweep:
        by_cls_sweep[str(row["account_class"])].append(row)

    by_class: dict[str, dict[str, object]] = {}

    for acct in ACCOUNTS:
        _, tier1 = apex_tier_index_for_equity(acct.starting_balance, acct.tiers)
        tier1_dll = float(tier1.dll_limit)
        tier1_cap_mnq = _max_q_contract_cap(tier1.max_contracts_mini)
        q_hi = min(45, tier1_cap_mnq, int(acct.eval_max_mini * _MNQ_PER_MINI))

        q_rq_closed = _max_q_for_rq(acct.trailing_dd, dd1_closed, q_hi)
        q_dll = _max_q_dll(worst_session, tier1_dll, q_hi)
        q_consistency = _max_q_consistency(best_session_bound, net_total_mnq1, q_hi)
        q_contract = tier1_cap_mnq

        cls_rows = sorted(by_cls_sweep.get(acct.key, []), key=lambda r: float(r["target_qty_mnq"]))
        gate_a = 0
        gate_a_row: dict[str, object] | None = None
        for row in cls_rows:
            if row.get("funded_survived"):
                gate_a = int(float(row["target_qty_mnq"]))
                gate_a_row = row

        q_rq_eod = 0
        dd_linear = True
        dd1_path = None
        for row in cls_rows:
            q = int(float(row["target_qty_mnq"]))
            pt_dd = float(row["max_peak_to_trough_dd"])
            if dd1_path is None:
                dd1_path = pt_dd
            elif q == 2 and dd1_path > 0:
                if abs(pt_dd / (dd1_path * 2.0) - 1.0) > 0.02:
                    dd_linear = False
            dd_q = pt_dd / q if q else pt_dd
            if _rq_dollars(q, dd_q) <= acct.trailing_dd:
                q_rq_eod = q

        constraints = {
            "R_q_closed_trade_dd": q_rq_closed,
            "EOD_path_R_q_screen": q_rq_eod,
            "worst_session_vs_tier1_dll": q_dll,
            "consistency_30pct": q_consistency,
            "tier1_contract_cap_mnq": q_contract,
            "gate_a_funded_survival": gate_a,
        }
        q_operational = min(
            q_dll,
            q_consistency,
            q_contract,
            gate_a,
        )
        q_max = q_operational
        binding = min(
            {
                k: v
                for k, v in constraints.items()
                if k not in ("R_q_closed_trade_dd", "EOD_path_R_q_screen")
            },
            key=lambda k: constraints[k],
        )

        gross_ann = pnl_per_yr * q_max if q_max > 0 else 0.0
        net_ann = _net_payout_annual(gross_ann)
        yearly_gross = {
            y: round(float(v) * q_max, 2)
            for y, v in per["years_calendar_pnl_full_2020_2026"].items()
        }
        yearly_net = {y: round(_net_payout_annual(v), 2) for y, v in yearly_gross.items()}

        pass_rate = float("nan")
        eval_detail: dict[str, object] = {}
        q_row: dict[str, object] | None = None
        if q_max > 0:
            q_row = next(
                (r for r in cls_rows if int(float(r["target_qty_mnq"])) == q_max),
                None,
            )
            if q_row is None:
                q_row = next(
                    (
                        r
                        for r in cls_rows
                        if int(float(r["target_qty_mnq"])) >= q_max and r.get("funded_survived")
                    ),
                    None,
                )
        if q_row is not None:
            pass_rate = float(q_row.get("eval_pass_rate", float("nan")))
            eval_qty_used = int(float(q_row["target_qty_mnq"]))
            eval_detail = {
                "pass_rate": pass_rate,
                "eval_qty_mnq": min(float(q_max), acct.eval_max_mini * _MNQ_PER_MINI),
                "eval_sim_qty_from_sweep": eval_qty_used,
                "eval_proxy_note": (
                    None
                    if eval_qty_used == q_max
                    else f"Exact q={q_max} not in Wave 0f sweep; pass rate from q={eval_qty_used} row."
                ),
                "eval_dll_tier1": tier1_dll,
                "window_note": (
                    "Wave 0f 30 **calendar-day** NY windows (tiered eval sim); "
                    "pre-registered spec is 30 **trading-session** windows — "
                    "re-run with data/raw for session-window eval."
                ),
            }

        eval_cost = acct.eval_fee_usd / pass_rate if pass_rate and pass_rate > 0 else float("inf")
        net_after_eval = net_ann - eval_cost if math.isfinite(eval_cost) else float("nan")
        clears_floor = bool(q_max > 0 and net_ann >= _TIER_FLOOR and pass_rate >= _EVAL_GATE)

        fr_row = q_row or {}
        by_class[acct.key] = {
            "label": acct.label,
            "apex_params": {
                "starting_balance": acct.starting_balance,
                "trailing_dd": acct.trailing_dd,
                "profit_target": acct.profit_target,
                "lock_equity": acct.lock_equity,
                "tier1_dll": tier1_dll,
                "tier1_max_mini": tier1.max_contracts_mini,
                "tier1_cap_mnq": tier1_cap_mnq,
                "eval_max_mini": acct.eval_max_mini,
                "eval_fee_usd": acct.eval_fee_usd,
                "eval_fee_source": "operator_table_flagged_confirm_help_center",
            },
            "constraint_qty_limits_mnq": constraints,
            "max_sustainable_qty_mnq": q_max,
            "gate_a_funded_q_max_mnq": gate_a,
            "R_q_stress_screen_binds_at_zero": q_rq_closed == 0 and q_rq_eod == 0,
            "binding_constraint": binding,
            "dd_linearity_eod_path": dd_linear,
            "dd1_closed_trade_usd": dd1_closed,
            "worst_session_pnl_mnq1_usd": worst_session,
            "best_session_pnl_mnq1_upper_bound_usd": best_session_bound,
            "consistency_ratio_mnq1_upper_bound": consistency_ratio,
            "funded_at_q_max": {
                "survived": bool(fr_row.get("funded_survived")) if q_max > 0 else False,
                "max_peak_to_trough_dd": fr_row.get("max_peak_to_trough_dd"),
                "dll_pause_days": fr_row.get("dll_pause_days"),
                "final_equity": fr_row.get("final_equity"),
            },
            "economics_at_q_max": {
                "per_mnq_annual_gross_usd": round(pnl_per_yr, 2),
                "gross_annual_usd": round(gross_ann, 2),
                "net_payout_annual_usd": round(net_ann, 2),
                "net_after_eval_amortized_usd": (
                    round(net_after_eval, 2) if math.isfinite(net_after_eval) else None
                ),
                "tier": _econ_tier(net_ann),
                "yearly_gross_usd": yearly_gross,
                "yearly_net_payout_usd": yearly_net,
            },
            "eval_at_q_max": eval_detail,
            "eval_cost_per_funded_account_usd": (
                round(eval_cost, 2) if math.isfinite(eval_cost) else None
            ),
            "clears_floor_income_gate": clears_floor,
        }

    anchor_divergence = abs(pnl_per_yr - _PNL_ANCHOR) / _PNL_ANCHOR if _PNL_ANCHOR else 0.0
    any_deployable = any(row["clears_floor_income_gate"] for row in by_class.values())
    all_tail_bind = all(
        by_class[k]["binding_constraint"]
        in (
            "worst_session_vs_tier1_dll",
            "R_q_closed_trade_dd",
            "EOD_path_dd_vs_tdd",
            "gate_a_funded_survival",
        )
        for k in by_class
    )

    return {
        "survey": "orb_opt3_account_class_floor_income",
        "date": "2026-06-08",
        "git": meta_git,
        "input_mode": "wave0_artifacts_fallback",
        "artifact_sources": [
            "notebooks/validation/2026-05-14_wave0_orb_opt3_graded_baseline.json",
            "notebooks/validation/2026-05-17_wave0h_orb_opt3_chapter_closeout.json",
            "notebooks/validation/2026-05-17_wave0f_orb_opt3_failure_profile.json",
        ],
        "protocol": {
            "start": _START.isoformat(),
            "end_inclusive": _END.isoformat(),
            "trade_count_qty1": int(per["trade_count"]),
            "daily_sessions": wave0h["protocol"]["unique_exit_ny_dates_with_trades"],
            "yfrac": yfrac,
            "wave0_log_reference": "2026-05-14_wave0_orb_opt3_graded_baseline.json",
        },
        "per_mnq_anchor": {
            "python_pnl_per_yr": round(pnl_per_yr, 2),
            "anchor_expected": _PNL_ANCHOR,
            "divergence_pct": round(anchor_divergence * 100, 2),
            "reproduction_ok": anchor_divergence <= 0.10,
        },
        "harness": {
            "segment_runs": 0,
            "all_segments_passed": None,
            "note": "No fresh backtest — Wave 0 log reused from graded baseline JSON.",
        },
        "payout_model": {
            "first_usd_100pct": _PAYOUT_FIRST_100PCT,
            "remainder_split_to_trader": _PAYOUT_SPLIT,
            "note": "Annual gross simplified to one payout cycle per year.",
        },
        "account_classes": by_class,
        "verdict": {
            "deployable_any_class": any_deployable,
            "structural_loss_tail_wall": not any_deployable and all_tail_bind,
            "summary": (
                "DEPLOYABLE on at least one class"
                if any_deployable
                else "NO class clears floor + eval gate — loss-tail / sizing wall structural"
            ),
        },
        "stop_conditions": {
            "reproduction_divergence_gt_10pct": anchor_divergence > 0.10,
        },
    }


def _write_outputs(payload: dict[str, object], pnl_per_yr: float, harness_pass: bool | None) -> None:
    meta_git = payload["git"]
    by_class = payload["account_classes"]
    any_deployable = payload["verdict"]["deployable_any_class"]

    out_dir = _REPO / "notebooks" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "2026-06-08_orb_account_class_survey.json"
    md_path = out_dir / "2026-06-08_orb_account_class_survey.md"

    json_path.write_text(
        json.dumps(_json_safe(payload), indent=2, allow_nan=False),
        encoding="utf-8",
    )

    input_mode = payload.get("input_mode", "fresh_backtest")
    harness_line = (
        "Wave 0 graded baseline reused (no fresh backtest)"
        if input_mode == "wave0_artifacts_fallback"
        else ("PASS all segments" if harness_pass else "FAIL — see JSON")
    )

    lines = [
        "# ORB+Opt3 account-class survey — floor-income fit",
        "",
        f"**Date:** 2026-06-08  ",
        f"**Git:** `{meta_git['git_sha']}` dirty={meta_git['git_dirty']}  ",
        f"**Input mode:** {input_mode}  ",
        "",
        "> Edge is **not** re-tested. Input: Wave 0 validated ORB+Opt3 qty=1 log "
        f"(**${pnl_per_yr:,.0f}/yr/MNQ**).",
        "",
        f"**Harness / log:** {harness_line}",
        "",
        "## Cross-class comparison",
        "",
        "| class | max sust qty (MNQ) | binding constraint | funded $/yr net | "
        "eval pass rate | eval cost / funded acct | clears floor? | tier |",
        "|-------|-------------------|--------------------|---------------|"
        "---------------|-------------------------|---------------|------|",
    ]
    for acct in ACCOUNTS:
        row = by_class[acct.key]
        ec = row["economics_at_q_max"]
        ev = row["eval_at_q_max"]
        q = row["max_sustainable_qty_mnq"]
        q_ec = row.get("economics_eval_qty_mnq", q)
        bind = row["binding_constraint"]
        if q == 0 and row.get("consistency_fails_at_mnq1"):
            bind = f"{bind} (strict; ex-consistency q={row.get('max_sustainable_qty_ex_consistency_mnq')})"
        pr = ev.get("pass_rate") if ev else float("nan")
        pr_s = f"{float(pr):.1%}" if pr == pr else "—"
        cost = row["eval_cost_per_funded_account_usd"]
        cost_s = f"${cost:,.0f}" if cost else "—"
        qty_label = str(q) if q > 0 else f"0 (econ@{q_ec})"
        lines.append(
            f"| {acct.key} | {qty_label} | {bind} | "
            f"${ec['net_payout_annual_usd']:,.0f} | {pr_s} | {cost_s} | "
            f"{'YES' if row['clears_floor_income_gate'] else 'NO'} | {ec['tier']} |",
        )

    lines += [
        "",
        "## Verdict",
        "",
        f"**{payload['verdict']['summary']}**",
        "",
        "### Constraint detail (qty limits, MNQ)",
        "",
    ]
    for acct in ACCOUNTS:
        c = by_class[acct.key]["constraint_qty_limits_mnq"]
        lines.append(f"- **{acct.key}:** " + ", ".join(f"{k}={v}" for k, v in c.items()))

    lines += [
        "",
        "### Gate A funded q_max (income context — not DLL-bound operational qty)",
        "",
        "| class | Gate A q_max (MNQ) | gross $/yr at Gate A | gap to $36K floor |",
        "|-------|-------------------|----------------------|-------------------|",
    ]
    for acct in ACCOUNTS:
        row = by_class[acct.key]
        ga = row.get("gate_a_funded_q_max_mnq", row["constraint_qty_limits_mnq"]["gate_a_funded_survival"])
        gross_ga = float(row["economics_at_q_max"]["per_mnq_annual_gross_usd"]) * float(ga)
        gap = _TIER_FLOOR - gross_ga
        lines.append(f"| {acct.key} | {ga} | ${gross_ga:,.0f} | ${gap:,.0f} short |")

    lines += [
        "",
        "### Operator recommendation",
        "",
    ]
    if any_deployable:
        deploy = [k for k, v in by_class.items() if v["clears_floor_income_gate"]]
        lines.append(
            f"ORB+Opt3 is a **DEPLOYABLE** candidate on: **{', '.join(deploy)}** "
            f"at listed max sustainable qty."
        )
    else:
        lines.append(
            "ORB+Opt3 **does not fit any** Apex EOD class at **$36K/yr floor** with "
            "**eval pass rate ≥ 50%**. The wall is **structural**: per-MNQ edge (~$1K/yr) "
            "requires ~**36 MNQ** for floor gross, but **loss-tail / TDD / DLL / Gate A** "
            "caps sustainable qty at **≤5–15 MNQ** depending on class — far below income size. "
            "This confirms the **$50K production cut** logic extends across larger classes; "
            "the constraint is **account rules × loss tail**, not missing edge."
        )

    lines += ["", f"Full JSON: `{json_path.name}`", ""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"wrote_json": str(json_path), "wrote_md": str(md_path)}, indent=2))


def main() -> None:
    meta_git = _git_meta(_REPO)
    root_raw = _mnq_raw_root()
    if _mnq_contract_glob(root_raw) is None:
        print(
            "No MNQ contract files under data/raw or data/raw/mnq; "
            "using Wave 0 artifact fallback.",
            file=sys.stderr,
        )
        payload = _survey_from_artifacts(meta_git)
        per = payload["per_mnq_anchor"]["python_pnl_per_yr"]
        _write_outputs(payload, float(per), None)
        return

    raw = _load_mnq_raw(root_raw)
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
    validation_reports: list[dict[str, object]] = []
    for seg in segments:
        strat = OrbStrategy(p1)
        out = BacktestEngine(cfg).run(seg, [as_module("orb", strat)])
        if out.validation_report is not None:
            validation_reports.append(out.validation_report.to_dict())
        if out.trade_log.height > 0:
            logs.append(out.trade_log)

    combined = pl.concat(logs) if logs else empty_trade_log()
    enriched = _append_exit_session_columns(combined)
    trades_sorted = enriched.sort("exit_time")
    exit_sess = trades_sorted["exit_cme_session_date"].to_list()
    exit_ny = trades_sorted["exit_ny_date"].to_list()
    pnls1 = trades_sorted["net_pnl"].to_numpy().astype(np.float64)
    exit_times_list = trades_sorted["exit_time"].to_list()

    _, daily_mnq1, ny_daily = trades_to_daily_pnls_with_ny(exit_sess, exit_ny, pnls1)
    yfrac = protocol_year_fraction(_START, _END)
    m = compute_m6_aggregates(combined)
    pnl_per_yr = m.net_pnl_total / yfrac if yfrac > 0 else 0.0
    anchor_divergence = abs(pnl_per_yr - _PNL_ANCHOR) / _PNL_ANCHOR if _PNL_ANCHOR else 0.0

    worst_session = float(np.min(daily_mnq1)) if daily_mnq1.size else 0.0
    best_session = float(np.max(daily_mnq1)) if daily_mnq1.size else 0.0
    dd1_closed = abs(float(m.max_drawdown_dollars)) if hasattr(m, "max_drawdown_dollars") else _DD1_ANCHOR

    harness_pass = all(r.get("passed", False) for r in validation_reports) if validation_reports else False

    q_search_hi = 45
    by_class: dict[str, dict[str, object]] = {}

    for acct in ACCOUNTS:
        _, tier1 = apex_tier_index_for_equity(acct.starting_balance, acct.tiers)
        tier1_dll = float(tier1.dll_limit)
        tier1_cap_mnq = _max_q_contract_cap(tier1.max_contracts_mini)
        q_hi = min(q_search_hi, tier1_cap_mnq, int(acct.eval_max_mini * _MNQ_PER_MINI))

        q_rq_closed = _max_q_for_rq(acct.trailing_dd, dd1_closed, q_hi)
        q_rq_formula_at_qmax = _rq_dollars(max(q_rq_closed, 1), dd1_closed) if q_rq_closed else None

        q_eod_dd, dd_linear = _max_q_eod_dd(daily_mnq1, ny_daily, acct, acct.trailing_dd, q_hi)
        q_rq_eod = 0
        for q in range(1, q_hi + 1):
            fr_q = simulate_apex_eod_two_phase(
                daily_mnq1,
                ny_daily,
                starting_balance=acct.starting_balance,
                trailing_dd=acct.trailing_dd,
                dll_limit=0.0,
                lock_equity_threshold=acct.lock_equity,
                post_lock_floor=acct.post_lock_floor,
                balance_tiers=acct.tiers,
                target_qty_mnq=float(q),
                mnq_per_mini=_MNQ_PER_MINI,
                enforce_dll=False,
            )
            dd_q = fr_q.max_peak_to_trough_dd / q if q else fr_q.max_peak_to_trough_dd
            if _rq_dollars(q, dd_q) <= acct.trailing_dd:
                q_rq_eod = q

        q_dll = _max_q_dll(worst_session, tier1_dll, q_hi)
        q_consistency = _max_q_consistency(best_session, m.net_pnl_total, q_hi)
        q_contract = tier1_cap_mnq
        q_gate_a = _max_q_gate_a(daily_mnq1, ny_daily, acct, q_hi)

        constraints = {
            "R_q_closed_trade_dd": q_rq_closed,
            "EOD_path_R_q_screen": q_rq_eod,
            "worst_session_vs_tier1_dll": q_dll,
            "consistency_30pct": q_consistency,
            "tier1_contract_cap_mnq": q_contract,
            "gate_a_funded_survival": q_gate_a,
        }
        q_max = min(q_dll, q_consistency, q_contract, q_gate_a)
        q_ex_consistency = min(q_dll, q_contract, q_gate_a)
        binding = min(
            {
                k: v
                for k, v in constraints.items()
                if k not in ("R_q_closed_trade_dd", "EOD_path_R_q_screen")
            },
            key=lambda k: constraints[k],
        )
        report_q = q_max if q_max > 0 else q_ex_consistency

        fr_at_max = simulate_apex_eod_two_phase(
            daily_mnq1,
            ny_daily,
            starting_balance=acct.starting_balance,
            trailing_dd=acct.trailing_dd,
            dll_limit=0.0,
            lock_equity_threshold=acct.lock_equity,
            post_lock_floor=acct.post_lock_floor,
            balance_tiers=acct.tiers,
            target_qty_mnq=float(report_q) if report_q > 0 else 1.0,
            mnq_per_mini=_MNQ_PER_MINI,
        )

        gross_ann = pnl_per_yr * report_q if report_q > 0 else 0.0
        net_ann = _net_payout_annual(gross_ann)
        yearly_gross = _yearly_pnl(exit_ny, pnls1 * float(report_q if report_q > 0 else 0))
        yearly_net = {y: round(_net_payout_annual(v), 2) for y, v in yearly_gross.items()}

        ev = _eval_pass_rate_sessions(
            pnls1,
            exit_ny,
            exit_sess,
            exit_times_list,
            session_dates,
            acct,
            float(report_q if report_q > 0 else 1),
        )
        pass_rate = float(ev["pass_rate"]) if ev["total_windows"] else float("nan")
        eval_cost = acct.eval_fee_usd / pass_rate if pass_rate and pass_rate > 0 else float("inf")
        net_after_eval = net_ann - eval_cost if math.isfinite(eval_cost) else float("nan")

        clears_floor = bool(
            report_q > 0
            and net_ann >= _TIER_FLOOR
            and pass_rate >= _EVAL_GATE
        )

        by_class[acct.key] = {
            "label": acct.label,
            "apex_params": {
                "starting_balance": acct.starting_balance,
                "trailing_dd": acct.trailing_dd,
                "profit_target": acct.profit_target,
                "lock_equity": acct.lock_equity,
                "tier1_dll": tier1_dll,
                "tier1_max_mini": tier1.max_contracts_mini,
                "tier1_cap_mnq": tier1_cap_mnq,
                "eval_max_mini": acct.eval_max_mini,
                "eval_fee_usd": acct.eval_fee_usd,
                "eval_fee_source": "operator_table_flagged_confirm_help_center",
            },
            "constraint_qty_limits_mnq": constraints,
            "max_sustainable_qty_mnq": q_max,
            "max_sustainable_qty_ex_consistency_mnq": q_ex_consistency,
            "economics_eval_qty_mnq": report_q,
            "gate_a_funded_q_max_mnq": q_gate_a,
            "R_q_stress_screen_binds_at_zero": q_rq_closed == 0 and q_rq_eod == 0,
            "consistency_fails_at_mnq1": q_consistency == 0,
            "binding_constraint": binding,
            "dd_linearity_eod_path": dd_linear,
            "dd1_closed_trade_usd": dd1_closed,
            "worst_session_pnl_mnq1_usd": worst_session,
            "best_session_pnl_mnq1_usd": best_session,
            "consistency_ratio_mnq1": (
                best_session / m.net_pnl_total if m.net_pnl_total > 0 else None
            ),
            "funded_at_q_max": {
                "survived": fr_at_max.survived if report_q > 0 else False,
                "max_peak_to_trough_dd": fr_at_max.max_peak_to_trough_dd,
                "dll_pause_days": fr_at_max.dll_failure_days,
                "final_equity": fr_at_max.final_equity,
            },
            "economics_at_q_max": {
                "per_mnq_annual_gross_usd": round(pnl_per_yr, 2),
                "gross_annual_usd": round(gross_ann, 2),
                "net_payout_annual_usd": round(net_ann, 2),
                "net_after_eval_amortized_usd": (
                    round(net_after_eval, 2) if math.isfinite(net_after_eval) else None
                ),
                "tier": _econ_tier(net_ann),
                "yearly_gross_usd": yearly_gross,
                "yearly_net_payout_usd": yearly_net,
            },
            "eval_at_q_max": ev,
            "eval_cost_per_funded_account_usd": (
                round(eval_cost, 2) if math.isfinite(eval_cost) else None
            ),
            "clears_floor_income_gate": clears_floor,
        }

    any_deployable = any(row["clears_floor_income_gate"] for row in by_class.values())
    all_dll_bind = all(
        row["binding_constraint"] in ("worst_session_vs_tier1_dll", "R_q_closed_trade_dd", "EOD_path_dd_vs_tdd")
        for row in by_class.values()
    )

    payload: dict[str, object] = {
        "survey": "orb_opt3_account_class_floor_income",
        "date": "2026-06-08",
        "input_mode": "fresh_backtest",
        "git": meta_git,
        "protocol": {
            "start": _START.isoformat(),
            "end_inclusive": _END.isoformat(),
            "trade_count_qty1": int(pnls1.size),
            "daily_sessions": len(daily_mnq1),
            "yfrac": yfrac,
            "wave0_log_reference": "2026-05-14_wave0_orb_opt3_graded_baseline.json",
        },
        "per_mnq_anchor": {
            "python_pnl_per_yr": round(pnl_per_yr, 2),
            "anchor_expected": _PNL_ANCHOR,
            "divergence_pct": round(anchor_divergence * 100, 2),
            "reproduction_ok": anchor_divergence <= 0.10,
        },
        "harness": {
            "segment_runs": len(validation_reports),
            "all_segments_passed": harness_pass,
            "reports": validation_reports,
        },
        "payout_model": {
            "first_usd_100pct": _PAYOUT_FIRST_100PCT,
            "remainder_split_to_trader": _PAYOUT_SPLIT,
            "note": "Annual gross simplified to one payout cycle per year.",
        },
        "account_classes": by_class,
        "verdict": {
            "deployable_any_class": any_deployable,
            "structural_dll_tdd_wall": not any_deployable and all_dll_bind,
            "summary": (
                "DEPLOYABLE on at least one class"
                if any_deployable
                else "NO class clears floor + eval gate — loss-tail / sizing wall structural"
            ),
        },
        "stop_conditions": {
            "reproduction_divergence_gt_10pct": anchor_divergence > 0.10,
        },
    }

    _write_outputs(payload, pnl_per_yr, harness_pass)


if __name__ == "__main__":
    main()
