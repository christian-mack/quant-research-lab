#!/usr/bin/env python3
"""Wave 0f — Failure-profile diagnosis + low-qty sweep (ORB+Opt3, tiered Apex).

Usage (repo root)::

    uv run python scripts/run_wave0f_orb_opt3_failure_profile.py

Reads ``notebooks/validation/2026-05-17_wave0e_orb_opt3_survey.json`` for Wave 0e
(account_class, target_qty) pairs. Writes
``notebooks/validation/2026-05-17_wave0f_orb_opt3_failure_profile.{md,json}``.
"""

from __future__ import annotations

# ruff: noqa: E402, E501
import datetime as dt
import json
import math
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
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
from quant_research.statistics.apex_eod_trailing import (
    ApexBalanceTier,
    apex_tier_index_for_equity,
    block_bootstrap_apex_eod_tiered_funded,
    eval_pass_rate_calendar_days,
    simulate_apex_eod_two_phase,
    simulate_apex_eod_two_phase_tiered_with_trace,
    trades_to_daily_pnls_with_ny,
)

_CHI = ZoneInfo("America/Chicago")
_START = dt.date(2020, 1, 1)
_END = dt.date(2026, 4, 19)
_BOOT_IT = 10_000
_BOOT_SEED_BASE = 4242
_TIER_FLOOR = 36_000.0
_GATE_BOOT = 0.80
_GATE_EVAL = 0.50
_MNQ_PER_MINI = 10.0
_WAVE0E_JSON = _REPO / "notebooks" / "validation" / "2026-05-17_wave0e_orb_opt3_survey.json"


def pa_25k_tiers() -> tuple[ApexBalanceTier, ...]:
    return (
        ApexBalanceTier(25_000, 25_999, 1, 500),
        ApexBalanceTier(26_000, 26_999, 2, 500),
        ApexBalanceTier(27_000, float("inf"), 2, 1_250),
    )


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
class Acct:
    key: str
    starting_balance: float
    trailing_dd: float
    profit_target: float
    lock_equity: float
    post_lock_floor: float
    eval_max_mini: int
    tiers: tuple[ApexBalanceTier, ...]


ACCOUNT_BY_KEY: dict[str, Acct] = {
    "25k": Acct("25k", 25_000, 1_000, 1_500, 26_000, 25_000, 4, pa_25k_tiers()),
    "50k": Acct("50k", 50_000, 2_000, 3_000, 52_000, 50_000, 6, pa_50k_tiers()),
    "100k": Acct("100k", 100_000, 3_000, 6_000, 103_000, 100_000, 8, pa_100k_tiers()),
    "150k": Acct("150k", 150_000, 4_000, 9_000, 154_000, 150_000, 12, pa_150k_tiers()),
}

LOW_QTY_SWEEP: dict[str, tuple[float, ...]] = {
    "25k": (1.0, 2.0, 3.0, 5.0, 7.0, 10.0),
    "50k": (1.0, 2.0, 5.0, 10.0, 15.0, 20.0),
    "100k": (5.0, 10.0, 15.0, 20.0, 25.0, 30.0),
    "150k": (10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0),
}


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
    if ann >= 100_000.0:
        return "stretch_or_above"
    if ann >= 60_000.0:
        return "target_band"
    if ann >= 36_000.0:
        return "floor_band"
    return "below_floor"


def _row_date(d: object) -> dt.date:
    if isinstance(d, dt.date):
        return d
    return dt.date.fromisoformat(str(d))


def _failure_enumeration(
    trace: list[dict[str, object]],
    *,
    survived: bool,
    trailing_dd: float,
) -> dict[str, object]:
    breaches = [r for r in trace if r["trail_breach_after_session"]]
    if not breaches:
        return {
            "failure_sessions": [],
            "primary_failure_mode": None,
            "catastrophic_vs_cumulative_hint": None,
            "dll_pauses_before_primary_breach": None,
            "note": "no_trailing_breach_sessions_recorded" if survived else "unexpected_empty_breaches",
        }
    primary = breaches[0]
    fb = float(primary["session_pnl"])
    idx0 = int(primary["session_index"])
    dll_before = sum(
        1
        for r in trace
        if int(r["session_index"]) < idx0 and r.get("dll_new_pause_this_session")
    )
    locked_at_breach = bool(primary["locked_close"])
    primary_failure_mode = (
        "trailing_breach_post_lock" if locked_at_breach else "trailing_breach_pre_lock"
    )
    mag = abs(fb)
    if mag >= 0.45 * float(trailing_dd):
        hint = "lean_single_catastrophic_session"
    elif dll_before >= 20:
        hint = "lean_cumulative_erosion_dll_heavy"
    else:
        hint = "mixed_or_gradual"
    return {
        "failure_sessions": [
            {
                "session_index": int(primary["session_index"]),
                "ny_date": primary["ny_date"],
                "failure_mode": primary_failure_mode,
                "session_pnl": float(primary["session_pnl"]),
                "equity_open": float(primary["equity_open"]),
                "equity_close": float(primary["equity_close"]),
                "margin_to_floor_open": float(primary["margin_to_floor_open"]),
                "margin_to_floor_close": float(primary["margin_to_floor_close"]),
                "tier_index_open": int(primary["tier_index_open"]),
                "locked_at_close": bool(primary["locked_close"]),
            },
        ],
        "all_breach_session_indices": [int(r["session_index"]) for r in breaches[:5]],
        "primary_failure_mode": primary_failure_mode,
        "refined_submode_post_or_pre_lock": primary_failure_mode,
        "catastrophic_vs_cumulative_hint": hint,
        "dll_new_pause_sessions_before_primary_breach": dll_before,
        "breach_session_loss_magnitude_vs_trailing_dd": mag / float(trailing_dd),
    }


def _session_loss_distribution(trace: list[dict[str, object]]) -> dict[str, object]:
    pnls = sorted(float(r["session_pnl"]) for r in trace)
    arr = np.array(pnls, dtype=np.float64)
    worst = {"n10": pnls[:10], "n25": pnls[:25], "n50": pnls[:50]}
    dll_by_tier = Counter(
        int(r["tier_index_open"]) for r in trace if r.get("dll_new_pause_this_session")
    )
    return {
        "session_count": len(trace),
        "pnl_mean": float(np.mean(arr)) if arr.size else None,
        "pnl_std": float(np.std(arr)) if arr.size else None,
        "pnl_min": float(np.min(arr)) if arr.size else None,
        "pnl_p05": float(np.percentile(arr, 5)) if arr.size else None,
        "pnl_p95": float(np.percentile(arr, 95)) if arr.size else None,
        "worst_session_pnls": worst,
        "dll_pause_sessions_by_tier_index": dict(sorted(dll_by_tier.items())),
    }


def _yearly_attribution(trace: list[dict[str, object]], acct: Acct) -> dict[str, object]:
    pnl_y: dict[int, float] = defaultdict(float)
    dll_y: dict[int, int] = defaultdict(int)
    tier_time: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    demotion_y: Counter[int] = Counter()
    prev_t: int | None = None
    for r in trace:
        y = _row_date(r["ny_date"]).year
        pnl_y[y] += float(r["session_pnl"])
        if r.get("dll_new_pause_this_session"):
            dll_y[y] += 1
        tix = int(r["tier_index_open"])
        tier_time[y][str(tix)] += 1
        if prev_t is not None and tix < prev_t:
            demotion_y[y] += 1
        prev_t = tix
    breach_years = [
        _row_date(r["ny_date"]).year for r in trace if r["trail_breach_after_session"]
    ]
    failure_year = breach_years[0] if breach_years else None
    return {
        "pnl_by_year": {str(k): round(v, 2) for k, v in sorted(pnl_y.items())},
        "dll_pause_sessions_by_year": {str(k): v for k, v in sorted(dll_y.items())},
        "sessions_per_tier_by_year": {str(y): dict(m) for y, m in sorted(tier_time.items())},
        "failure_calendar_year_first_breach": failure_year,
        "tier_demotion_events_by_year": dict(demotion_y),
        "concentration_note": (
            "single_year_failure"
            if failure_year is not None and len(set(breach_years)) == 1
            else "multi_year_breach_days" if breach_years else "no_breach"
        ),
    }


def _run_one_survey_row(
    acct: Acct,
    target_qty: float,
    daily1: np.ndarray,
    ny_daily: list[dt.date],
    pnls1: np.ndarray,
    exit_ny: list[dt.date],
    exit_sess: list[int],
    exit_times_list: list[object],
    yfrac: float,
    boot_seed: int,
) -> dict[str, object]:
    fr = simulate_apex_eod_two_phase(
        daily1,
        ny_daily,
        starting_balance=acct.starting_balance,
        trailing_dd=acct.trailing_dd,
        dll_limit=0.0,
        lock_equity_threshold=acct.lock_equity,
        post_lock_floor=acct.post_lock_floor,
        balance_tiers=acct.tiers,
        target_qty_mnq=float(target_qty),
        mnq_per_mini=_MNQ_PER_MINI,
    )
    ann = (fr.final_equity - acct.starting_balance) / yfrac if yfrac > 0 else 0.0
    eval_cap_mnq = float(acct.eval_max_mini) * _MNQ_PER_MINI
    eval_q = min(float(target_qty), eval_cap_mnq)
    eval_dll = float(apex_tier_index_for_equity(acct.starting_balance, acct.tiers)[1].dll_limit)
    ev_pn = pnls1 * eval_q
    ev = eval_pass_rate_calendar_days(
        ev_pn,
        exit_ny,
        exit_sess,
        exit_times_list,
        starting_balance=acct.starting_balance,
        trailing_dd=acct.trailing_dd,
        profit_target=acct.profit_target,
        dll_limit=eval_dll,
        lock_equity_threshold=acct.lock_equity,
        post_lock_floor=acct.post_lock_floor,
        window_calendar_days=30,
    )
    rng = np.random.default_rng(boot_seed)
    boot = block_bootstrap_apex_eod_tiered_funded(
        pnls1,
        exit_sess,
        exit_ny,
        target_qty_mnq=float(target_qty),
        block_len=20,
        n_target_trades=int(pnls1.size),
        n_iterations=_BOOT_IT,
        rng=rng,
        starting_balance=acct.starting_balance,
        trailing_dd=acct.trailing_dd,
        balance_tiers=acct.tiers,
        lock_equity_threshold=acct.lock_equity,
        post_lock_floor=acct.post_lock_floor,
        mnq_per_mini=_MNQ_PER_MINI,
    )
    boot_frac = float(np.mean(boot["survived"].astype(np.float64)))
    return {
        "account_class": acct.key,
        "target_qty_mnq": target_qty,
        "funded_survived": fr.survived,
        "final_equity": fr.final_equity,
        "avg_annual_pnl_est": round(ann, 2),
        "max_peak_to_trough_dd": fr.max_peak_to_trough_dd,
        "dll_pause_days": fr.dll_failure_days,
        "tier_payload": fr.tier_summary or {},
        "eval_pass_rate": float(ev["pass_rate"]),
        "bootstrap_funded_survival_block20": boot_frac,
        "gates": {
            "funded": bool(fr.survived),
            "bootstrap_ge_80": boot_frac >= _GATE_BOOT,
            "eval_ge_50pct": float(ev["pass_rate"]) >= _GATE_EVAL,
        },
        "tier_vs_36_60_100k": _econ_tier(ann),
    }


def main() -> None:
    root_raw = _REPO / "data" / "raw"
    if not any(root_raw.glob("MNQ *.Last.txt")):
        print("No MNQ contract files under data/raw; abort.", file=sys.stderr)
        sys.exit(2)
    if not _WAVE0E_JSON.is_file():
        print(f"Missing {_WAVE0E_JSON}; run Wave 0e survey first.", file=sys.stderr)
        sys.exit(2)

    meta_git = _git_meta(_REPO)
    wave0e = json.loads(_WAVE0E_JSON.read_text(encoding="utf-8"))
    wave0e_rows: list[dict[str, object]] = wave0e["deliverable_3_survey"]
    yfrac = float(wave0e["protocol"]["yfrac"])

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
    _, daily1, ny_daily = trades_to_daily_pnls_with_ny(exit_sess, exit_ny, pnls1)

    deliverable1: list[dict[str, object]] = []
    modes_counter: Counter[str] = Counter()
    hints_counter: Counter[str] = Counter()
    failure_years: list[int] = []

    seen_pairs: set[tuple[str, float]] = set()
    for row in wave0e_rows:
        key = str(row["account_class"])
        tq = float(row["target_qty_mnq"])
        if (key, tq) in seen_pairs:
            continue
        seen_pairs.add((key, tq))
        acct = ACCOUNT_BY_KEY[key]
        res, trace = simulate_apex_eod_two_phase_tiered_with_trace(
            daily1,
            ny_daily,
            starting_balance=acct.starting_balance,
            trailing_dd=acct.trailing_dd,
            lock_equity_threshold=acct.lock_equity,
            post_lock_floor=acct.post_lock_floor,
            balance_tiers=acct.tiers,
            target_qty_mnq=tq,
            mnq_per_mini=_MNQ_PER_MINI,
        )
        fe = _failure_enumeration(
            trace,
            survived=res.survived,
            trailing_dd=acct.trailing_dd,
        )
        dist = _session_loss_distribution(trace)
        yatt = _yearly_attribution(trace, acct)
        if fe.get("primary_failure_mode"):
            modes_counter[str(fe["primary_failure_mode"])] += 1
        if fe.get("catastrophic_vs_cumulative_hint"):
            hints_counter[str(fe["catastrophic_vs_cumulative_hint"])] += 1
        fy = yatt.get("failure_calendar_year_first_breach")
        if isinstance(fy, int):
            failure_years.append(fy)

        deliverable1.append(
            {
                "account_class": key,
                "target_qty_mnq": tq,
                "funded_survived": res.survived,
                "failure_enumeration": fe,
                "session_pnl_distribution": dist,
                "yearly_attribution": yatt,
            },
        )

    deliverable4: list[dict[str, object]] = []
    lowest_funded_pass: dict[str, dict[str, object] | None] = {k: None for k in ACCOUNT_BY_KEY}
    lowest_triple_pass: dict[str, dict[str, object] | None] = {k: None for k in ACCOUNT_BY_KEY}
    joint_all: list[dict[str, object]] = []
    gate_fail_counts = Counter({"funded": 0, "bootstrap": 0, "eval": 0})
    fifty_k_q1_survived: bool | None = None

    for key, qtys in LOW_QTY_SWEEP.items():
        acct = ACCOUNT_BY_KEY[key]
        for tq in qtys:
            boot_seed = _BOOT_SEED_BASE + int(tq) * 19 + sum(ord(c) for c in key)
            r = _run_one_survey_row(
                acct,
                tq,
                daily1,
                ny_daily,
                pnls1,
                exit_ny,
                exit_sess,
                exit_times_list,
                yfrac,
                boot_seed,
            )
            if key == "50k" and tq == 1.0:
                fifty_k_q1_survived = bool(r["funded_survived"])
            if not r["gates"]["funded"]:
                gate_fail_counts["funded"] += 1
            elif not r["gates"]["bootstrap_ge_80"]:
                gate_fail_counts["bootstrap"] += 1
            elif not r["gates"]["eval_ge_50pct"]:
                gate_fail_counts["eval"] += 1
            g = r["gates"]
            if g["funded"] and g["bootstrap_ge_80"] and g["eval_ge_50pct"]:
                joint_all.append(r)
                prev = lowest_triple_pass[key]
                if prev is None or float(tq) < float(prev["target_qty_mnq"]):
                    lowest_triple_pass[key] = dict(r)
            if r["funded_survived"]:
                prev2 = lowest_funded_pass[key]
                if prev2 is None or float(tq) < float(prev2["target_qty_mnq"]):
                    lowest_funded_pass[key] = dict(r)
            deliverable4.append(
                {
                    **r,
                    "trace_omitted": True,
                },
            )

    joint_all.sort(key=lambda x: float(x["avg_annual_pnl_est"]), reverse=True)
    best_joint = joint_all[0] if joint_all else None

    closest_no_joint: list[dict[str, object]] = []
    for r in sorted(deliverable4, key=lambda x: float(x["avg_annual_pnl_est"]), reverse=True)[:30]:
        ann = float(r["avg_annual_pnl_est"])
        gap_floor = max(0.0, _TIER_FLOOR - ann)
        closest_no_joint.append(
            {
                "account_class": r["account_class"],
                "target_qty_mnq": r["target_qty_mnq"],
                "avg_annual_pnl_est": ann,
                "gap_to_36k_floor": round(gap_floor, 2),
                "gates": r["gates"],
            },
        )

    stop_flags = {
        "50k_qty1_funded_survival": fifty_k_q1_survived,
        "50k_incompatible_sizing_only": fifty_k_q1_survived is False,
        "any_joint_triple_pass": len(joint_all) > 0,
        "low_qty_any_funded_survival": any(lowest_funded_pass[k] is not None for k in lowest_funded_pass),
    }

    binding_mode = modes_counter.most_common(1)[0][0] if modes_counter else "n/a"
    year_conc = (
        "distributed"
        if len(set(failure_years)) > 4
        else f"concentrated_{Counter(failure_years).most_common(3)}"
    )

    deliverable5 = {
        "binding_failure_mode_summary": (
            f"Most common labeled primary mode across Wave 0e pairs: {binding_mode}. "
            f"Catastrophic vs cumulative hints (counts): {dict(hints_counter)}."
        ),
        "failure_year_concentration": year_conc,
        "lowest_qty_funded_survival_by_class": {
            k: (
                {
                    "target_qty_mnq": v["target_qty_mnq"],
                    "avg_annual_pnl_est": v["avg_annual_pnl_est"],
                }
                if v
                else None
            )
            for k, v in lowest_funded_pass.items()
        },
        "lowest_qty_triple_gate_by_class": {
            k: (
                {
                    "target_qty_mnq": v["target_qty_mnq"],
                    "avg_annual_pnl_est": v["avg_annual_pnl_est"],
                }
                if v
                else None
            )
            for k, v in lowest_triple_pass.items()
        },
        "best_joint_gate_combo": best_joint,
        "gate_fail_counts_low_qty_sweep": dict(gate_fail_counts),
        "repair_lever_opinion": (
            "If modes skew post_lock: reduce tail loss before lock (stops/size). "
            "If pre_lock / never_locked: trail eats equity before HWM progress — "
            "tighter risk or regime gating. If lean cumulative DLL-heavy: sub-ceiling qty "
            "and/or skip high-vol regimes. Compare yearly attribution for 2023 weight."
        ),
    }

    payload: dict[str, object] = {
        "wave": "0f",
        "git": meta_git,
        "wave0e_reference": str(_WAVE0E_JSON.name),
        "protocol": wave0e["protocol"],
        "deliverable_1_wave0e_failure_profiles": deliverable1,
        "aggregate_wave0e_failure_modes": dict(modes_counter),
        "aggregate_catastrophic_vs_cumulative_hints": dict(hints_counter),
        "deliverable_4_low_qty_sweep": deliverable4,
        "deliverable_5_diagnosis_summary": deliverable5,
        "joint_gate_passing_low_qty": joint_all,
        "closest_to_floor_tier_low_qty_sample": closest_no_joint,
        "stop_conditions": stop_flags,
    }

    out_dir = _REPO / "notebooks" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "2026-05-17_wave0f_orb_opt3_failure_profile.json"
    md_path = out_dir / "2026-05-17_wave0f_orb_opt3_failure_profile.md"
    json_path.write_text(
        json.dumps(_json_safe(payload), indent=2, allow_nan=False),
        encoding="utf-8",
    )

    lines = [
        "# Wave 0f — Failure profile + low-qty survivability (ORB+Opt3)",
        "",
        f"**Git:** `{meta_git['git_sha']}` dirty={meta_git['git_dirty']}  ",
        f"**UTC:** {dt.datetime.now(dt.UTC).isoformat()}  ",
        "",
        "## Headline",
        "",
        f"- **$50 funded survival @ 1 MNQ:** {fifty_k_q1_survived}",
        f"- **Any low-qty funded survival:** {stop_flags['low_qty_any_funded_survival']}",
        f"- **Any triple-gate pass (low-qty sweep):** {stop_flags['any_joint_triple_pass']}",
        f"- **50K incompatible (qty=1 fails funded):** {stop_flags['50k_incompatible_sizing_only']}",
        "",
        "## Wave 0e failure-mode aggregates",
        "",
        f"- Primary modes: `{dict(modes_counter)}`",
        f"- Catastrophic vs cumulative hints: `{dict(hints_counter)}`",
        "",
        "## Lowest qty with funded survival (by class)",
        "",
    ]
    for k, v in lowest_funded_pass.items():
        if v:
            lines.append(
                f"- **{k}:** qty **{v['target_qty_mnq']}** MNQ → ~**${v['avg_annual_pnl_est']:,.0f}**/yr est.",
            )
        else:
            lines.append(f"- **{k}:** **none** in sweep")
    lines += [
        "",
        "## Triple gate (low-qty sweep)",
        "",
    ]
    if best_joint:
        lines.append(
            f"- Best passing: **{best_joint['account_class']}** @ **{best_joint['target_qty_mnq']}** MNQ — ~**${float(best_joint['avg_annual_pnl_est']):,.0f}**/yr.",
        )
    else:
        lines.append("**None** — see `gate_fail_counts_low_qty_sweep` in JSON.")
    lines += [
        "",
        f"Full JSON: `{json_path.name}`",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"wrote_json": str(json_path), "wrote_md": str(md_path)}, indent=2))


if __name__ == "__main__":
    main()
