#!/usr/bin/env python3
"""Wave 1 engine remediation — clean M4 re-run for OTE 62%, OTE 70.5%, FVG-only.

Post P0 geometry guard + P1 OTE consolidation onto BacktestEngine.
P2 dual-touch calibration deferred.

Run: ``uv run python scripts/run_wave1_engine_remediation_ote_rerun.py``
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.data import data_loader
from quant_research.ict import pd_arrays as pd_mod
from quant_research.ict.ote_execution import (
    OteExecutedTrade,
    economics_summary,
    ote_research_backtest_config,
    run_config_backtest,
)
from quant_research.ict.ote_strategy import (
    ENTRY_FVG_ONLY,
    ENTRY_OTE_62,
    ENTRY_OTE_705,
    ENTRY_OTE_ONLY,
    OteStrategyConfig,
)
from quant_research.research_wave1.instrument_pipeline import load_continuous_rth_mnq_style

DATA_ROOT = _REPO / "data" / "raw"
PROTOCOL_START = dt.date(2020, 1, 1)
PROTOCOL_END = dt.date(2026, 4, 19)
OUT_STEM = _REPO / "notebooks" / "validation" / "2026-06-07_wave1_engine_remediation_and_ote_rerun"

EVAL_YEARS = (2021, 2022, 2023, 2024, 2025)
PARTIAL_YEARS = ("2020", "2026")
APEX_TIER1_DLL = 1000.0
TARGET_ANNUAL_USD = 30_000.0
TICK_VAL = 0.25 * 2.0

# Step 3c baselines (comm+slip, full 7-year protocol window)
STEP3C_BASELINES = {
    "OTE62_full": 5098.56,
    "OTE705_full": -2409.53,
    "FVG_only_full": 26184.55,
}

GEOMETRY_REJECT_STOP_FRAC = 0.30


def _git_sha() -> str:
    try:
        cp = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return (cp.stdout or "").strip() or "unknown"
    except OSError:
        return "unknown"


def _dll_check(trades: list[OteExecutedTrade], *, annual_net: float) -> dict[str, Any]:
    if annual_net <= 0:
        return {
            "sizing_qty_for_30k_yr": None,
            "max_session_net_loss_usd_at_qty": None,
            "apex_tier1_dll_usd": APEX_TIER1_DLL,
            "fits_apex_tier1_dll": False,
            "note": "Non-positive annual net — no sizing toward $30K/yr",
        }
    qty = TARGET_ANNUAL_USD / annual_net
    by_sess: dict[str, float] = defaultdict(float)
    for t in trades:
        if t.session_date is None:
            continue
        by_sess[t.session_date] += t.net_pnl * qty
    session_pnls = list(by_sess.values())
    max_loss = min(session_pnls) if session_pnls else 0.0
    return {
        "sizing_qty_for_30k_yr": round(qty, 2),
        "max_session_net_loss_usd_at_qty": round(max_loss, 2),
        "apex_tier1_dll_usd": APEX_TIER1_DLL,
        "fits_apex_tier1_dll": abs(max_loss) <= APEX_TIER1_DLL,
        "worst_session_date": min(by_sess, key=by_sess.get) if by_sess else None,
    }


def _year_breakdown(trades: list[OteExecutedTrade]) -> dict[str, float]:
    by_year: dict[str, float] = defaultdict(float)
    for t in trades:
        if t.session_date is None:
            continue
        by_year[t.session_date[:4]] += t.net_pnl
    return dict(sorted(by_year.items()))


def _run_label(label: str, config: OteStrategyConfig, mnq: pl.DataFrame) -> dict[str, Any]:
    print(f"Running {label} ...", flush=True)
    batch = run_config_backtest(
        mnq,
        config=config,
        backtest_config=ote_research_backtest_config(),
    )
    print(
        f"  chain_attempts={batch.setups_detected:,} "
        f"passed_scan={batch.setups_passed_scan:,} "
        f"geom_rejects={batch.geometry_reject_total:,} "
        f"({100 * batch.geometry_reject_rate:.1f}% of attempts) "
        f"filled={batch.setups_filled:,}",
        flush=True,
    )
    full_econ = economics_summary(batch.trades)
    frame_b = economics_summary(batch.trades, eval_years=EVAL_YEARS)
    year_net = _year_breakdown(batch.trades)
    annual_frame_b = frame_b.get("annual_net_usd", 0.0)
    return {
        "label": label,
        "setups_detected": batch.setups_detected,
        "setups_passed_scan": batch.setups_passed_scan,
        "geometry_rejects": batch.geometry_rejects,
        "geometry_reject_total": batch.geometry_reject_total,
        "geometry_reject_rate": batch.geometry_reject_rate,
        "setups_filled": batch.setups_filled,
        "n_trades": len(batch.trades),
        "full_protocol_economics": full_econ,
        "frame_b_economics": frame_b,
        "year_net_usd": year_net,
        "dll_check_frame_b": _dll_check(batch.trades, annual_net=annual_frame_b),
        "dll_check_full": _dll_check(
            batch.trades,
            annual_net=full_econ.get("annual_net_usd", 0.0),
        ),
    }


def _stop_conditions(results: dict[str, dict[str, Any]]) -> dict[str, str]:
    ote62 = results["OTE62"]
    fvg = results["FVG_only"]
    reject_rate = ote62["geometry_reject_rate"]
    frame_b_annual = ote62["frame_b_economics"].get("annual_net_usd", 0.0)
    fvg_annual = fvg["frame_b_economics"].get("annual_net_usd", 0.0)
    fvg_ticks = fvg["frame_b_economics"].get("avg_net_ticks", 0.0)

    stops: dict[str, str] = {}
    if reject_rate > GEOMETRY_REJECT_STOP_FRAC:
        stops["ote62_geometry_reject_gt_30pct"] = (
            f"TRIGGERED — {100 * reject_rate:.1f}% of OTE 62% setups rejected "
            f"(>{100 * GEOMETRY_REJECT_STOP_FRAC:.0f}% threshold)"
        )
    else:
        stops["ote62_geometry_reject_gt_30pct"] = (
            f"NOT triggered — {100 * reject_rate:.1f}% reject rate"
        )

    if frame_b_annual < 0:
        stops["ote62_frame_b_negative"] = (
            f"TRIGGERED — Frame B annual net ${frame_b_annual:,.0f}/MNQ "
            "(step-3c positive was partly artifact)"
        )
    else:
        stops["ote62_frame_b_negative"] = (
            f"NOT triggered — Frame B annual net ${frame_b_annual:,.0f}/MNQ"
        )

    # FVG collapse: post-guard should be << step3c $26k; near-zero or negative confirms diagnosis
    if fvg_annual > 5000 or fvg_ticks > 10:
        stops["fvg_artifact_not_collapsed"] = (
            f"TRIGGERED — FVG-only still ${fvg_annual:,.0f}/yr, "
            f"{fvg_ticks:.1f} ticks/trade after guard"
        )
    else:
        stops["fvg_artifact_not_collapsed"] = (
            f"NOT triggered — FVG-only ${fvg_annual:,.0f}/yr, "
            f"{fvg_ticks:.1f} ticks/trade (artifact collapsed)"
        )

    stops["dual_touch_p2"] = "DEFERRED — stop-first rule unchanged; uncalibrated"
    return stops


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Wave 1 — Engine remediation + clean OTE re-run",
        "",
        "**Date:** 2026-06-07  ",
        f"**git_sha:** `{report['git_sha']}`  ",
        f"**Protocol:** {report['protocol_window'][0]} → {report['protocol_window'][1]}  ",
        "",
        "## Scope",
        "",
        "- **P0:** Structural geometry guard (stop on loss side, target on profit side) — "
        "enforced in M4 bracket validation + OTE setup assembly.",
        "- **P1:** OTE fills consolidated onto M4 BacktestEngine with unified cost model "
        "($1.98 RT, 1 tick stop/time slip, ½ tick target, no entry slip).",
        "- **P2:** Dual-touch calibration **deferred** — stop-first rule retained.",
        "",
        "## Cost model (engine-native)",
        "",
        report["cost_model"],
        "",
        "## Comparison to step 3c (pre-remediation, comm+slip)",
        "",
        "| Config | Step 3c annual (full) | Clean M4 Frame B | Δ Frame B |",
        "|--------|----------------------:|-----------------:|----------:|",
    ]
    key_map = {
        "OTE62_full": "OTE62",
        "OTE705_full": "OTE705",
        "FVG_only_full": "FVG_only",
    }
    for step_key, baseline in STEP3C_BASELINES.items():
        cfg_key = key_map[step_key]
        fb = report["configs"][cfg_key]["frame_b_economics"].get("annual_net_usd", 0.0)
        delta = fb - baseline
        lines.append(f"| {cfg_key} | ${baseline:,.0f} | ${fb:,.0f} | ${delta:+,.0f} |")

    lines.extend(["", "## Results by config", ""])
    for cfg in report["configs"].values():
        fb = cfg["frame_b_economics"]
        full = cfg["full_protocol_economics"]
        lines.extend(
            [
                f"### {cfg['label']}",
                "",
                f"- Sweep-chain attempts (pre-geometry): **{cfg['setups_detected']:,}**",
                f"- Passed geometry scan: **{cfg.get('setups_passed_scan', 0):,}**",
                f"- Geometry rejects: **{cfg['geometry_reject_total']:,}** "
                f"({100 * cfg['geometry_reject_rate']:.1f}% of attempts) — {cfg['geometry_rejects']}",
                f"- Setups filled: **{cfg['setups_filled']:,}**",
                f"- Trades: **{cfg['n_trades']:,}**",
                "",
                "**Full protocol (comm+slip, engine-native):**",
                f"- Annual net: **${full.get('annual_net_usd', 0):,.0f}/MNQ**",
                f"- Net ticks/trade: **{full.get('avg_net_ticks', 0):.2f}**",
                f"- WR: **{100 * full.get('win_rate', 0):.1f}%** | "
                f"R:R **{full.get('reward_risk_ratio', 0):.2f}**",
                "",
                "**Frame B (2021–2025 eval years):**",
                f"- Annual net: **${fb.get('annual_net_usd', 0):,.0f}/MNQ**",
                f"- Net ticks/trade: **{fb.get('avg_net_ticks', 0):.2f}**",
                "",
                "**Year-by-year net (comm+slip):**",
            ]
        )
        for y, p in cfg["year_net_usd"].items():
            flag = " *(partial)*" if y in PARTIAL_YEARS else ""
            lines.append(f"- {y}: ${p:,.0f}{flag}")
        dll = cfg["dll_check_frame_b"]
        lines.append(
            f"- Apex DLL ($30K/yr sizing, Frame B): qty={dll.get('sizing_qty_for_30k_yr')}, "
            f"max session loss=${dll.get('max_session_net_loss_usd_at_qty')}, "
            f"fits tier-1={dll.get('fits_apex_tier1_dll')}, "
            f"worst={dll.get('worst_session_date')}"
        )
        lines.append("")

    lines.extend(["## Stop conditions", ""])
    for k, v in report["stop_conditions"].items():
        lines.append(f"- **{k}:** {v}")

    lines.extend(
        [
            "",
            "## Operator summary",
            "",
            report["operator_summary"],
        ]
    )
    return "\n".join(lines)


def main() -> None:
    git_sha = _git_sha()
    print("Loading MNQ ...", flush=True)
    mnq = pd_mod.add_pd_arrays(
        load_continuous_rth_mnq_style(
            DATA_ROOT,
            pattern=data_loader.MNQ_CONTRACT_GLOB,
            protocol_start=PROTOCOL_START,
            protocol_end_inclusive=PROTOCOL_END,
        )
    )
    print(f"  -> {mnq.height:,} bars", flush=True)

    configs = {
        "OTE705": (
            "OTE 70.5% full RTH",
            OteStrategyConfig(
                entry_style=ENTRY_OTE_ONLY,
                entry_mode=ENTRY_OTE_705,
            ),
        ),
        "OTE62": (
            "OTE 62% full RTH",
            OteStrategyConfig(
                entry_style=ENTRY_OTE_ONLY,
                entry_mode=ENTRY_OTE_62,
            ),
        ),
        "FVG_only": (
            "FVG-only full RTH",
            OteStrategyConfig(
                entry_style=ENTRY_FVG_ONLY,
                entry_mode=ENTRY_OTE_705,
            ),
        ),
    }

    results: dict[str, dict[str, Any]] = {}
    for key, (label, cfg) in configs.items():
        results[key] = _run_label(label, cfg, mnq)

    stops = _stop_conditions(results)
    ote62_fb = results["OTE62"]["frame_b_economics"].get("annual_net_usd", 0.0)
    fvg_fb = results["FVG_only"]["frame_b_economics"].get("annual_net_usd", 0.0)
    operator_summary = (
        f"P0 geometry guard + P1 M4 consolidation complete. "
        f"Clean OTE 62% Frame B: ${ote62_fb:,.0f}/MNQ/yr "
        f"(step 3c was ${STEP3C_BASELINES['OTE62_full']:,.0f}). "
        f"FVG-only collapsed to ${fvg_fb:,.0f}/yr (was ${STEP3C_BASELINES['FVG_only_full']:,.0f} artifact). "
        f"Geometry reject rate OTE 62%: {100 * results['OTE62']['geometry_reject_rate']:.1f}%. "
        f"Dual-touch (P2) unchanged."
    )

    report: dict[str, Any] = {
        "git_sha": git_sha,
        "protocol_window": [str(PROTOCOL_START), str(PROTOCOL_END)],
        "eval_years": list(EVAL_YEARS),
        "cost_model": (
            "Commission $0.99/fill ($1.98 RT) in BacktestEngine; "
            "slippage 1 tick default (stop/time), 0 entry (limit touch), "
            "0.5 tick target — applied once per fill in engine."
        ),
        "step3c_baselines_comm_slip_full": STEP3C_BASELINES,
        "configs": results,
        "stop_conditions": stops,
        "operator_summary": operator_summary,
        "p2_note": "Stop-first dual-touch not recalibrated; revisit only if OTE 62% "
        "within ~1 tick/trade of viability threshold.",
    }

    OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
    OUT_STEM.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    OUT_STEM.with_suffix(".md").write_text(_render_md(report), encoding="utf-8")
    print(f"\nWrote {OUT_STEM.with_suffix('.md')}", flush=True)
    print(operator_summary, flush=True)


if __name__ == "__main__":
    main()
