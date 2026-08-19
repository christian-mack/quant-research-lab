#!/usr/bin/env python3
"""Wave 0e — Tiered PA DLL/qty, bootstrap diagnosis, account-class survey (ORB+Opt3).

Usage (repo root, MNQ data under data/raw)::

    uv run python scripts/run_wave0e_orb_opt3_survey.py

Writes ``notebooks/validation/2026-05-17_wave0e_orb_opt3_survey.{md,json}``.
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
from quant_research.backtest.m6_metrics import protocol_year_fraction
from quant_research.backtest.schema import empty_trade_log
from quant_research.data import continuous_contract, data_loader, session
from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.modules import OrbStrategy, production_orb_opt3_funded_params
from quant_research.statistics.apex_eod_trailing import (
    ApexBalanceTier,
    apex_tier_index_for_equity,
    block_bootstrap_apex_eod_tiered_funded,
    diagnose_block_bootstrap_flat_funded_path,
    eval_pass_rate_calendar_days,
    simulate_apex_50k_eod_two_phase,
    simulate_apex_eod_two_phase,
    trades_to_daily_pnls_with_ny,
)

_CHI = ZoneInfo("America/Chicago")
_START = dt.date(2020, 1, 1)
_END = dt.date(2026, 4, 19)
_BOOT_IT = 10_000
_BOOT_SEED = 42
_DIAG_YEAR = 2023
_TIER_FLOOR = 36_000.0
_TIER_TARGET = 60_000.0
_TIER_STRETCH = 100_000.0
_GATE_BOOT = 0.80
_GATE_EVAL = 0.50
_MNQ_PER_MINI = 10.0


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
class Wave0eAccount:
    key: str
    label: str
    starting_balance: float
    trailing_dd: float
    profit_target: float
    lock_equity: float
    post_lock_floor: float
    eval_max_mini: int
    tiers: tuple[ApexBalanceTier, ...]
    target_qty_mnq: tuple[float, ...]


ACCOUNTS: tuple[Wave0eAccount, ...] = (
    Wave0eAccount(
        "25k",
        "$25K EOD",
        25_000,
        1_000,
        1_500,
        26_000,
        25_000,
        4,
        pa_25k_tiers(),
        (10.0, 15.0, 20.0),
    ),
    Wave0eAccount(
        "50k",
        "$50K EOD",
        50_000,
        2_000,
        3_000,
        52_000,
        50_000,
        6,
        pa_50k_tiers(),
        (20.0, 25.0, 30.0, 35.0, 40.0),
    ),
    Wave0eAccount(
        "100k",
        "$100K EOD",
        100_000,
        3_000,
        6_000,
        103_000,
        100_000,
        8,
        pa_100k_tiers(),
        (30.0, 40.0, 50.0, 60.0),
    ),
    Wave0eAccount(
        "150k",
        "$150K EOD",
        150_000,
        4_000,
        9_000,
        154_000,
        150_000,
        12,
        pa_150k_tiers(),
        (40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0),
    ),
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


def _tier_payload(result: object) -> dict[str, object]:
    r = result
    ts = getattr(r, "tier_summary", None)
    return dict(ts) if ts else {}


def _econ_tier(ann: float) -> str:
    if ann >= _TIER_STRETCH:
        return "stretch_or_above"
    if ann >= _TIER_TARGET:
        return "target_band"
    if ann >= _TIER_FLOOR:
        return "floor_band"
    return "below_floor"


def _bootstrap_bias_flag(d20: dict[str, object]) -> tuple[bool, str]:
    un = float(d20["unconditional_survival_fraction"])
    cond = d20["conditional_survival_within_10pct_expected_count"]
    if cond is None or (isinstance(cond, float) and math.isnan(cond)):
        return False, "conditional_rate_unavailable"
    cond_f = float(cond)
    if un < 0.35 and cond_f > un + 0.12:
        return True, "conditional_survival_substantially_exceeds_unconditional"
    return False, "no_strong_artifact_flag"


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
    yfrac = protocol_year_fraction(_START, _END)

    def _flat_50k_funded(d: np.ndarray, ny: list[dt.date]):
        return simulate_apex_50k_eod_two_phase(d, ny)

    diag_b20 = diagnose_block_bootstrap_flat_funded_path(
        pnls1 * 1.0,
        exit_sess,
        exit_ny,
        year=_DIAG_YEAR,
        block_len=20,
        n_target_trades=int(pnls1.size),
        n_iterations=_BOOT_IT,
        rng=np.random.default_rng(_BOOT_SEED),
        protocol_yfrac=yfrac,
        funded_sim=_flat_50k_funded,
    )
    diag_b1 = diagnose_block_bootstrap_flat_funded_path(
        pnls1 * 1.0,
        exit_sess,
        exit_ny,
        year=_DIAG_YEAR,
        block_len=1,
        n_target_trades=int(pnls1.size),
        n_iterations=_BOOT_IT,
        rng=np.random.default_rng(_BOOT_SEED + 1),
        protocol_yfrac=yfrac,
        funded_sim=_flat_50k_funded,
    )
    bias_flag, bias_reason = _bootstrap_bias_flag(diag_b20)
    surv_gap = float(diag_b20["unconditional_survival_fraction"]) - float(
        diag_b1["unconditional_survival_fraction"]
    )

    proposed_bootstrap_revision = (
        "Stratified resampling: partition trade indices by calendar year of exit_ny; "
        "resample blocks within each stratum so bootstrap paths match source year fractions; "
        "or circular block bootstrap without replacement across years. **Not implemented "
        "in Wave 0e — operator approval required.**"
    )

    if surv_gap > 0.08:
        diag_class = (
            "Serial dependence (block-20 vs iid gap) contributes to survival estimate; "
            "combine with year-count analysis."
        )
    elif bias_flag:
        diag_class = (
            "Likely overweight of high-impact calendar year in tails (see conditional survival)."
        )
    else:
        diag_class = "Low unconditional survival may reflect path fragility; year-bias not dominant by coarse flags."

    diagnosis_block = {
        "block20": diag_b20,
        "block1_iid_trades": diag_b1,
        "survival_gap_block20_minus_block1": surv_gap,
        "methodology_bias_flag": bias_flag,
        "bias_reason": bias_reason,
        "diagnosis_class": diag_class,
        "proposed_bootstrap_revision": proposed_bootstrap_revision,
        "stop_recommendation_strict_reading": (
            "If diagnosis_class implies resampling artifact, pause before trusting "
            "unconditional block-20 survival; conditional rates and block-1 baseline "
            "are diagnostic only."
        ),
    }

    survey_rows: list[dict[str, object]] = []
    joint_hits: list[dict[str, object]] = []
    any_funded_pass = False

    for acct in ACCOUNTS:
        eval_cap_mnq = float(acct.eval_max_mini) * _MNQ_PER_MINI
        eval_dll = float(apex_tier_index_for_equity(acct.starting_balance, acct.tiers)[1].dll_limit)

        for tqty in acct.target_qty_mnq:
            fr = simulate_apex_eod_two_phase(
                daily1,
                ny_daily,
                starting_balance=acct.starting_balance,
                trailing_dd=acct.trailing_dd,
                dll_limit=0.0,
                lock_equity_threshold=acct.lock_equity,
                post_lock_floor=acct.post_lock_floor,
                balance_tiers=acct.tiers,
                target_qty_mnq=float(tqty),
                mnq_per_mini=_MNQ_PER_MINI,
            )
            if fr.survived:
                any_funded_pass = True
            ann = (fr.final_equity - acct.starting_balance) / yfrac if yfrac > 0 else 0.0

            eval_q = min(float(tqty), eval_cap_mnq)
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

            rng = np.random.default_rng(
                _BOOT_SEED + int(tqty) * 17 + sum(ord(c) for c in acct.key) * 31,
            )
            boot = block_bootstrap_apex_eod_tiered_funded(
                pnls1,
                exit_sess,
                exit_ny,
                target_qty_mnq=float(tqty),
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

            row = {
                "account_class": acct.key,
                "target_qty_mnq": tqty,
                "funded_survived": fr.survived,
                "final_equity": fr.final_equity,
                "total_pnl": fr.final_equity - acct.starting_balance,
                "avg_annual_pnl_est": round(ann, 2),
                "max_peak_to_trough_dd": fr.max_peak_to_trough_dd,
                "dll_pause_days": fr.dll_failure_days,
                "tier_payload": _tier_payload(fr),
                "eval": ev,
                "bootstrap_funded_survival_block20": boot_frac,
                "gates": {
                    "funded": bool(fr.survived),
                    "bootstrap_ge_80": boot_frac >= _GATE_BOOT,
                    "eval_ge_50pct": float(ev["pass_rate"]) >= _GATE_EVAL,
                },
                "tier_vs_36_60_100k": _econ_tier(ann),
            }
            survey_rows.append(row)
            g = row["gates"]
            if g["funded"] and g["bootstrap_ge_80"] and g["eval_ge_50pct"]:
                joint_hits.append(
                    {"account_class": acct.key, "target_qty_mnq": tqty, "avg_annual_pnl_est": ann},
                )

    joint_hits.sort(key=lambda x: float(x["avg_annual_pnl_est"]), reverse=True)
    closest = sorted(
        survey_rows,
        key=lambda r: float(r["avg_annual_pnl_est"]),
        reverse=True,
    )[:20]

    stop_flags = {
        "bootstrap_methodology_bias_suggested": bias_flag,
        "funded_survival_any_pair": any_funded_pass,
        "joint_all_three_gates_any": len(joint_hits) > 0,
        "material_change_vs_wave0d_expected": True,
    }

    payload: dict[str, object] = {
        "wave": "0e",
        "git": meta_git,
        "apex_rules_note": "May 2026 operator-confirmed PA tier DLL/MNQ caps; 1 mini = 10 MNQ.",
        "protocol": {
            "start": _START.isoformat(),
            "end_inclusive": _END.isoformat(),
            "trade_count_qty1": int(pnls1.size),
            "daily_sessions": len(daily1),
            "yfrac": yfrac,
        },
        "deliverable_2_bootstrap_diagnosis": diagnosis_block,
        "deliverable_3_survey": survey_rows,
        "joint_gates_passing": joint_hits,
        "closest_by_pnl_sample": closest,
        "stop_conditions": stop_flags,
    }

    out_dir = _REPO / "notebooks" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "2026-05-17_wave0e_orb_opt3_survey.json"
    md_path = out_dir / "2026-05-17_wave0e_orb_opt3_survey.md"

    json_path.write_text(
        json.dumps(_json_safe(payload), indent=2, allow_nan=False),
        encoding="utf-8",
    )

    lines = [
        "# Wave 0e — Tiered PA rules + bootstrap diagnosis + survey",
        "",
        "> **Wave 0d is obsolete** for PA contract limits, TDD values, and tier-DLL behavior.",
        "",
        f"**Git:** `{meta_git['git_sha']}` dirty={meta_git['git_dirty']}  ",
        f"**UTC:** {dt.datetime.now(dt.UTC).isoformat()}  ",
        "",
        "## Bootstrap diagnosis ($50K flat q=1 MNQ, block-20 vs block-1)",
        "",
        f"- Unconditional survival (block 20): **{float(diag_b20['unconditional_survival_fraction']):.4f}**",
        f"- Unconditional survival (block 1): **{float(diag_b1['unconditional_survival_fraction']):.4f}**",
        f"- Gap (20 − 1): **{surv_gap:.4f}**",
        f"- Conditional survival (|2023 count − expected| ≤10%): **{diag_b20['conditional_survival_within_10pct_expected_count']}**",
        f"- **Bias flag:** {bias_flag} ({bias_reason})",
        f"- **Diagnosis class:** {diag_class}",
        "",
        "See JSON `deliverable_2_bootstrap_diagnosis` for full counts and `proposed_bootstrap_revision`.",
        "",
        "## Joint gates (funded + bootstrap≥80% + eval≥50%)",
        "",
    ]
    if joint_hits:
        for h in joint_hits[:15]:
            lines.append(
                f"- **{h['account_class']}** @ **{h['target_qty_mnq']} MNQ**: ~**${h['avg_annual_pnl_est']:,.0f}**/yr est.",
            )
    else:
        lines.append("**None** — inspect `deliverable_3_survey` and `closest_by_pnl_sample`.")

    lines += [
        "",
        "## STOP flags",
        "",
        f"- **Any funded survival:** {any_funded_pass}",
        f"- **Joint triple gate:** {len(joint_hits) > 0}",
        f"- **Bootstrap bias flag:** {bias_flag}",
        "",
        f"JSON: `{json_path.name}`",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"wrote_json": str(json_path), "wrote_md": str(md_path)}, indent=2))


if __name__ == "__main__":
    main()
