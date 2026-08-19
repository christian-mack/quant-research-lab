#!/usr/bin/env python3
"""Wave 1 Stage 1 Track 1b — H8b MES–MNQ divergence coarse screen.

Writes ``notebooks/validation/2026-05-29_wave1_stage1_track1b_h8b_*.{md,json}``.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.data import data_loader, session
from quant_research.data.quality import (
    KNOWN_GAPS,
    find_missing_trading_days,
    find_unexpected_missing_days,
    split_dataframe_at_operator_export_gaps,
)
from quant_research.research_wave1.instrument_pipeline import (
    instrument_raw_coverage,
    load_continuous_rth_mnq_style,
)
from quant_research.research_wave1.track1_hypothesis_sims import (
    prepare_et_frame,
    simulate_h8b,
)
from quant_research.research_wave1.track1_metrics import (
    GATE_EVAL_YEARS,
    GateResult,
    TradeRow,
    block_bootstrap_session_mean_annual_ci,
    daily_pnls_qty1_et,
    daily_sharpe_annualized,
    deflated_sharpe_joint_from_trial_stats,
    evaluate_gates,
    session_pnl_arrays,
    summarize_trade_sharpe_moments,
)

_TRACK1_JSON = (
    _REPO / "notebooks" / "validation" / "2026-05-26_wave1_stage1_track1_quant_screen.json"
)
_ARTIFACT_DATE = "2026-05-29"


def _git_sha(repo: Path) -> str:
    try:
        cp = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return (cp.stdout or "").strip() or "unknown"
    except OSError:
        return "unknown"


def _json_sanitize(obj: object) -> object:
    if obj is None:
        return None
    if isinstance(obj, str | bool):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_json_sanitize(v) for v in obj]
    if isinstance(obj, int | np.integer):  # type: ignore[arg-type]
        return int(obj)
    if isinstance(obj, float | np.floating):  # type: ignore[arg-type]
        x = float(obj)
        return None if math.isnan(x) or math.isinf(x) else x
    if isinstance(obj, dt.datetime | dt.date):
        return obj.isoformat()
    return str(obj)


def _gate_score(gr: GateResult) -> int:
    return sum(
        [
            bool(gr.gate1_pass),
            bool(gr.gate2_pass),
            bool(gr.gate3_pass),
            bool(gr.gate4_pass),
            bool(gr.gate5_pass),
        ]
    )


def _gate_gap_text(gr: GateResult) -> dict[str, str]:
    """Human-readable numerical gap for each failed gate."""
    gaps: dict[str, str] = {}
    g1 = gr.gate1_detail
    if not gr.gate1_pass:
        if g1.get("qty_design") is None:
            gaps["G1"] = f"avg annual qty=1 {g1.get('avg_annual_pnl_usd_qty1')} <= 0"
        else:
            worst = g1.get("worst_session_loss_usd_at_qty_design")
            gaps["G1"] = f"worst session {worst} not > -$1000 at qty={g1.get('qty_design')}"
    g2 = gr.gate2_detail
    if not gr.gate2_pass:
        gaps["G2"] = f"{g2.get('avg_trades_per_week'):.3f} trades/wk < 3.0"
    g3 = gr.gate3_detail
    if not gr.gate3_pass:
        gaps["G3"] = f"win rate {float(g3.get('win_rate', 0)):.3f} < 0.60"
    g4 = gr.gate4_detail
    if not gr.gate4_pass:
        gaps["G4"] = f"R:R {g4.get('rr')} outside [0.8, 1.5]"
    g5 = gr.gate5_detail
    if not gr.gate5_pass:
        gaps["G5"] = (
            f"profitable years {g5.get('profitable_year_count_strict_gt_0')} < 4 "
            f"(need >=4 of {list(GATE_EVAL_YEARS)})"
        )
    return gaps


def _load_rth_window(
    data_root: Path,
    pattern: str,
    protocol_start: dt.date,
    protocol_end_inc: dt.date,
) -> pl.DataFrame:
    return load_continuous_rth_mnq_style(
        data_root,
        pattern=pattern,
        protocol_start=protocol_start,
        protocol_end_inclusive=protocol_end_inc,
    )


def _mes_data_coverage_report(
    mes_rth: pl.DataFrame,
    mnq_rth: pl.DataFrame,
) -> dict[str, Any]:
    mes_missing = find_missing_trading_days(mes_rth)
    mnq_missing = find_missing_trading_days(mnq_rth)
    mes_unexpected = find_unexpected_missing_days(mes_rth)
    mnq_unexpected = find_unexpected_missing_days(mnq_rth)
    mes_only_unexpected = sorted(set(mes_unexpected) - set(mnq_unexpected))
    mnq_only_unexpected = sorted(set(mnq_unexpected) - set(mes_unexpected))

    chi = ZoneInfo(session.CT_TIMEZONE)
    ts0 = dt.datetime.combine(dt.date(2021, 1, 1), dt.time.min).replace(tzinfo=chi)
    ts1 = dt.datetime.combine(dt.date(2026, 1, 1), dt.time.min).replace(tzinfo=chi)
    mes_eval = mes_rth.filter((pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts1))
    mnq_eval = mnq_rth.filter((pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts1))
    mes_eval_unexp = find_unexpected_missing_days(mes_eval)
    mnq_eval_unexp = find_unexpected_missing_days(mnq_eval)
    mes_only_eval = sorted(set(mes_eval_unexp) - set(mnq_eval_unexp))

    known_gap_checks: list[dict[str, Any]] = []
    for g in KNOWN_GAPS:
        mes_in = [d for d in mes_missing if g.contains(d)]
        mnq_in = [d for d in mnq_missing if g.contains(d)]
        known_gap_checks.append(
            {
                "gap": f"{g.start_date}..{g.end_date}",
                "description": g.description,
                "mes_missing_days_in_gap": len(mes_in),
                "mnq_missing_days_in_gap": len(mnq_in),
            }
        )

    inner_sessions = (
        mes_rth.select("cme_session_date")
        .unique()
        .join(mnq_rth.select("cme_session_date").unique(), on="cme_session_date", how="inner")
        .height
    )

    return {
        "mes_rth_bar_count": mes_rth.height,
        "mnq_rth_bar_count": mnq_rth.height,
        "mes_ct_first_bar": mes_rth["timestamp"].min() if mes_rth.height else None,
        "mes_ct_last_bar": mes_rth["timestamp"].max() if mes_rth.height else None,
        "mnq_ct_first_bar": mnq_rth["timestamp"].min() if mnq_rth.height else None,
        "mnq_ct_last_bar": mnq_rth["timestamp"].max() if mnq_rth.height else None,
        "overlapping_cme_session_dates": inner_sessions,
        "mes_unexpected_missing_all_range": [d.isoformat() for d in mes_unexpected],
        "mnq_unexpected_missing_all_range": [d.isoformat() for d in mnq_unexpected],
        "mes_only_unexpected_missing_all_range": [d.isoformat() for d in mes_only_unexpected],
        "mnq_only_unexpected_missing_all_range": [d.isoformat() for d in mnq_only_unexpected],
        "mes_only_unexpected_missing_eval_2021_2025": [d.isoformat() for d in mes_only_eval],
        "known_export_gap_comparison": known_gap_checks,
        "stop_surface_mes_extra_gaps": bool(mes_only_eval),
        "note": (
            "H8b sim uses inner join on timestamp within MNQ gap-split segments; "
            "sessions without aligned MES bars are excluded automatically."
        ),
    }


def _trial_stats_from_track1(hid: str, track1: dict[str, Any]) -> dict[str, object]:
    hyp = track1["hypotheses_best_variant_and_gates"][hid]
    sh = hyp["sharpe"]
    mom = sh.get("daily_moment_summary_qty1") or {}
    sr = sh.get("daily_sharpe_annualized_point")
    k_ex = mom.get("kurtosis_excess")
    ku_pearson = float(k_ex) + 3.0 if k_ex is not None and np.isfinite(float(k_ex)) else None
    return {
        "hypothesis_id": hid,
        "observed_daily_sharpe_annualized": sr,
        "n_observations_daily": mom.get("n"),
        "skewness_daily_fisher": mom.get("skew_fisher"),
        "kurtosis_pearson_daily": ku_pearson,
    }


def _h8b_combine_segments(
    mnq_segments: list[pl.DataFrame],
    mes_et_full: pl.DataFrame,
    stop_sweep: tuple[int, ...],
) -> dict[int, list[TradeRow]]:
    agg: dict[int, list[TradeRow]] = {int(s): [] for s in stop_sweep}
    for seg in mnq_segments:
        mnq_et = prepare_et_frame(seg)
        if mnq_et.is_empty():
            continue
        dates = mnq_et["cme_session_date"].unique().to_list()
        mes_seg = mes_et_full.filter(pl.col("cme_session_date").is_in(dates))
        if mes_seg.is_empty():
            continue
        part = simulate_h8b(mnq_et, mes_seg, stop_sweep_points=stop_sweep)
        for k in agg:
            agg[k].extend(part[k])
    return agg


def main() -> None:
    root = _REPO / "data" / "raw"
    mes_pat = data_loader.MES_CONTRACT_GLOB
    mnq_pat = data_loader.MNQ_CONTRACT_GLOB

    if not any(root.glob(mes_pat)):
        print(f"No MES files matching {mes_pat!r}; abort.", file=sys.stderr)
        sys.exit(2)
    if not any(root.glob(mnq_pat)):
        print(f"No MNQ files matching {mnq_pat!r}; abort.", file=sys.stderr)
        sys.exit(2)

    chi = ZoneInfo(session.CT_TIMEZONE)
    protocol_start = dt.date(2021, 1, 1)
    protocol_end_inc = dt.date(2025, 12, 31)
    ts0 = dt.datetime.combine(protocol_start, dt.time.min).replace(tzinfo=chi)
    ts_end_excl = dt.datetime.combine(protocol_end_inc + dt.timedelta(days=1), dt.time.min).replace(
        tzinfo=chi,
    )

    mes_cov = instrument_raw_coverage(root, pattern=mes_pat)
    mnq_cov = instrument_raw_coverage(root, pattern=mnq_pat)

    mnq_rth_full = _load_rth_window(root, mnq_pat, dt.date(2020, 1, 1), dt.date(2026, 12, 31))
    mes_rth_full = _load_rth_window(root, mes_pat, dt.date(2020, 1, 1), dt.date(2026, 12, 31))
    coverage = _mes_data_coverage_report(mes_rth_full, mnq_rth_full)

    mes_first = coverage["mes_ct_first_bar"]
    if mes_first is not None:
        mes_start_date = mes_first.date() if hasattr(mes_first, "date") else dt.date(2020, 1, 2)
        if mes_start_date > dt.date(2021, 6, 1):
            print(
                f"STOP: MES coverage starts {mes_start_date} — materially later than 2020.",
                file=sys.stderr,
            )
            sys.exit(3)

    mnq_window = mnq_rth_full.filter(
        (pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts_end_excl)
    ).sort("timestamp")
    mes_window = mes_rth_full.filter(
        (pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts_end_excl)
    ).sort("timestamp")
    mes_et_full = prepare_et_frame(mes_window)

    segments = split_dataframe_at_operator_export_gaps(mnq_window)
    h8b_sw = (8, 10)
    h8b_map = _h8b_combine_segments(segments, mes_et_full, h8b_sw)

    best_key = ""
    best_trades: list[TradeRow] = []
    best_gr: GateResult | None = None
    best_sc = (-1, -1e18)
    sweep_summary: dict[str, object] = {}
    for sp in h8b_sw:
        tl = h8b_map[sp]
        gr = evaluate_gates(tl)
        pnl = sum(t.pnl_usd_qty1 for t in tl if t.exit_et_date.year in GATE_EVAL_YEARS)
        sweep_summary[f"stop{sp}"] = {
            "trades": len(tl),
            "pnl_gate_years_qty1_sum": pnl,
            "gates_pass_score": _gate_score(gr),
        }
        sc = (_gate_score(gr), pnl)
        if sc > best_sc:
            best_sc = sc
            best_key = f"stop{sp}"
            best_trades = tl
            best_gr = gr
    assert best_gr is not None

    dail = daily_pnls_qty1_et(best_trades, GATE_EVAL_YEARS)
    sr_d = daily_sharpe_annualized(dail) if best_trades else float("nan")
    mom = summarize_trade_sharpe_moments(dail)
    k_sort, sess_pnl = session_pnl_arrays(best_trades, years_filter=GATE_EVAL_YEARS)
    boot = block_bootstrap_session_mean_annual_ci(
        k_sort,
        sess_pnl,
        block_len=20,
        n_iterations=1000,
        seed=42,
    )

    gate_gaps = _gate_gap_text(best_gr)
    survives = bool(best_gr.overall_survives)
    conditional = (
        not survives
        and best_gr.gate2_pass
        and best_gr.gate3_pass
        and best_gr.gate4_pass
        and best_gr.gate5_pass
        and not best_gr.gate1_pass
    )

    track1: dict[str, Any] = {}
    if _TRACK1_JSON.is_file():
        track1 = json.loads(_TRACK1_JSON.read_text(encoding="utf-8"))

    joint_ids = ["H1", "H2", "H8b", "H11", "H12"]
    joint_trials: list[dict[str, object]] = []
    for hid in joint_ids:
        if hid == "H8b":
            ku = (
                float(mom["kurtosis_excess"]) + 3.0
                if np.isfinite(float(mom["kurtosis_excess"]))
                else 3.0
            )
            joint_trials.append(
                {
                    "hypothesis_id": "H8b",
                    "observed_daily_sharpe_annualized": sr_d,
                    "n_observations_daily": mom["n"],
                    "skewness_daily_fisher": mom["skew_fisher"],
                    "kurtosis_pearson_daily": ku,
                }
            )
        elif track1:
            joint_trials.append(_trial_stats_from_track1(hid, track1))

    joint_n5 = deflated_sharpe_joint_from_trial_stats(joint_trials, n_trials=5)
    track1_n7 = track1.get("deflated_sharpe_track_n7") if track1 else None

    h11_psr_n5 = next(
        (
            c.get("probabilistic_sharpe_vs_track_null")
            for c in joint_n5["per_hypothesis_deflated_block"]  # type: ignore[union-attr]
            if c.get("hypothesis_id") == "H11"
        ),
        None,
    )
    h11_psr_n7 = None
    if track1_n7:
        for c in track1_n7.get("per_hypothesis_deflated_block", []):
            if c.get("hypothesis_order_index") == 5:
                h11_psr_n7 = c.get("probabilistic_sharpe_vs_track_null")

    stop_surfaces: list[str] = []
    if coverage.get("stop_surface_mes_extra_gaps"):
        stop_surfaces.append(
            "MES_HAS_UNEXPECTED_GAPS_NOT_IN_MNQ_EVAL_WINDOW: "
            f"{coverage.get('mes_only_unexpected_missing_eval_2021_2025')} — "
            "surfaced; H8b runs on inner-joined overlap only."
        )
    if survives:
        stop_surfaces.append(
            "H8b_SURVIVES_ALL_FIVE_GATES: first Track 1/1b Stage-1 survivor — Stage 2 candidate."
        )
    elif conditional:
        stop_surfaces.append("H8b_CONDITIONAL_STAGE2: passes G2–G5, fails G1 only (H11 pattern).")

    artifact = {
        "wave": "Wave1_Stage1_Track1b_H8b_MES_MNQ_divergence",
        "date": _ARTIFACT_DATE,
        "git_sha": _git_sha(_REPO),
        "protocol_calendar": {
            "start": protocol_start.isoformat(),
            "end_inclusive": protocol_end_inc.isoformat(),
            "year_filters_gates": list(GATE_EVAL_YEARS),
            "instrument_execution": "MNQ",
            "cross_feature_instrument": "MES",
            "h8b_spec": "trade WITH divergence leader (supersedes Track 1 H8 fade spec)",
            "macro_calendar_filter": "not applied (no calendar data — same as Track 1)",
            "commission_slippage": (
                "none coarse screen ($0); exit modeling minute-bar pessimistic dual touch."
            ),
        },
        "data_coverage": {
            "mes_raw_probe": mes_cov,
            "mnq_raw_probe": mnq_cov,
            "rth_coverage_report": coverage,
            "mnq_gap_split_segments": len(segments),
            "deferred_hypotheses": ["H9 (RTY pending)", "H10 (RTY pending for full cross set)"],
        },
        "H8b": {
            "selected_variant": best_key,
            "sweep_eval_summary": sweep_summary,
            "trades_gate_years_qty1": len(
                [t for t in best_trades if t.exit_et_date.year in GATE_EVAL_YEARS]
            ),
            "gates_full": {
                "gate1": {"pass": best_gr.gate1_pass, "detail": best_gr.gate1_detail},
                "gate2": {"pass": best_gr.gate2_pass, "detail": best_gr.gate2_detail},
                "gate3": {"pass": best_gr.gate3_pass, "detail": best_gr.gate3_detail},
                "gate4": {"pass": best_gr.gate4_pass, "detail": best_gr.gate4_detail},
                "gate5": {"pass": best_gr.gate5_pass, "detail": best_gr.gate5_detail},
                "overall_survives_track1b": survives,
                "conditional_stage2_candidate": conditional,
                "failed_gate_numerical_gaps": gate_gaps,
            },
            "sharpe": {
                "aggregation": (
                    "Daily realized USD P&L at qty=1 MNQ; calendar NY exit-date; sqrt(252) scale."
                ),
                "daily_sharpe_annualized_point": sr_d,
                "daily_moment_summary_qty1": mom,
            },
            "bootstrap_mean_annual_pnl_qty1_sessions": boot,
        },
        "deflated_sharpe_joint_n5_run_hypotheses": joint_n5,
        "deflated_sharpe_track1_n7_reference": {
            "source_artifact": str(_TRACK1_JSON),
            "H11_psr_vs_track_null": h11_psr_n7,
            "note": "N=7 includes three zero-SR blocked slots (H8/H9/H10 never run).",
        },
        "deflated_sharpe_H11_psr_comparison": {
            "H11_psr_n7_from_track1": h11_psr_n7,
            "H11_psr_n5_joint_rerun": h11_psr_n5,
            "demotion_note": (
                "Recompute at N=5 (actually-run hypotheses) vs N=7 (registered batch)."
            ),
        },
        "stop_surfaces_triggers": stop_surfaces,
    }

    out_dir = _REPO / "notebooks" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{_ARTIFACT_DATE}_wave1_stage1_track1b_h8b_screen"
    with (base.with_suffix(".json")).open("w", encoding="utf-8") as f:
        json.dump(_json_sanitize(artifact), f, indent=2)

    outcome = "SURVIVE" if survives else ("CONDITIONAL" if conditional else "KILLED")
    lines = [
        "# Wave 1 Stage 1 Track 1b — H8b MES–MNQ divergence coarse screen",
        "",
        f"**Artifact JSON:** `{base.with_suffix('.json')}`",
        "**Protocol:** MNQ execution; MES cross-feature; H8b trades **with** divergence leader.",
        f"**Evaluation years:** {list(GATE_EVAL_YEARS)} (Frame B excludes 2020).",
        "",
        "## Data coverage",
        f"- **MES** files: **{mes_cov['contract_file_count']}** (`{mes_pat}`)",
        f"- **MES RTH bars:** {coverage['mes_rth_bar_count']:,}; "
        f"**{coverage['mes_ct_first_bar']}** → **{coverage['mes_ct_last_bar']}**",
        f"- **MNQ RTH bars:** {coverage['mnq_rth_bar_count']:,}; overlapping sessions: "
        f"**{coverage['overlapping_cme_session_dates']}**",
        f"- **MES-only unexpected missing (2021–2025 eval):** "
        f"{coverage['mes_only_unexpected_missing_eval_2021_2025']}",
        "- **Known MNQ export gaps:** MES **has bars** for Jun–Jul 2024 and Feb–Mar 2026 "
        "holes where MNQ export is empty; H8b still cannot trade those MNQ days.",
        "",
        "## Operator summary",
        f"- **Outcome:** **{outcome}** (selected `{best_key}`)",
        f"- **Gates:** G1={'PASS' if best_gr.gate1_pass else 'FAIL'}, "
        f"G2={'PASS' if best_gr.gate2_pass else 'FAIL'}, "
        f"G3={'PASS' if best_gr.gate3_pass else 'FAIL'}, "
        f"G4={'PASS' if best_gr.gate4_pass else 'FAIL'}, "
        f"G5={'PASS' if best_gr.gate5_pass else 'FAIL'}",
    ]
    if gate_gaps:
        lines.append("- **Failed gate gaps:**")
        for gk, gv in gate_gaps.items():
            lines.append(f"  - **{gk}:** {gv}")
    lines.extend(
        [
            f"- **Daily Sharpe (ann.):** {sr_d}",
            f"- **Bootstrap mean annual CI95:** `{boot}`",
            "",
            "## Joint deflated Sharpe (N=5: H1, H2, H8b, H11, H12)",
            "```json",
            json.dumps(_json_sanitize(joint_n5), indent=2)[:12000],
            "```",
            "",
            "## H11 PSR: N=5 vs Track 1 N=7",
            f"- **H11 PSR @ N=7 (Track 1):** {h11_psr_n7}",
            f"- **H11 PSR @ N=5 (joint rerun):** {h11_psr_n5}",
        ]
    )
    base.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {base.with_suffix('.json')} and .md")
    print(f"H8b outcome: {outcome} ({best_key})")


if __name__ == "__main__":
    main()
