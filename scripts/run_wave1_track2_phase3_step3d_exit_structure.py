#!/usr/bin/env python3
"""Wave 1 Track 2 — Phase 3 step 3d: realistic OTE exit-structure test.

Frozen OTE 70.5% entry; five pre-registered stop+target combinations through M4
with harness enforcement.

Run: ``uv run python scripts/run_wave1_track2_phase3_step3d_exit_structure.py``
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

import polars as pl

from quant_research.data import data_loader
from quant_research.indicators.atr import add_atr
from quant_research.ict import pd_arrays as pd_mod
from quant_research.ict.ote_execution import (
    OteExecutedTrade,
    economics_summary,
    execute_setups_on_sessions,
    ote_research_backtest_config,
)
from quant_research.ict.ote_exit_structure import STEP3D_COMBOS, remap_setups_for_combo
from quant_research.ict.ote_strategy import (
    ENTRY_OTE_705,
    ENTRY_OTE_ONLY,
    OteStrategyConfig,
    scan_setups_with_stats,
)
from quant_research.research_wave1.instrument_pipeline import load_continuous_rth_mnq_style

DATA_ROOT = _REPO / "data" / "raw"
PROTOCOL_START = dt.date(2020, 1, 1)
PROTOCOL_END = dt.date(2026, 4, 19)
OUT_STEM = (
    _REPO / "notebooks" / "validation" / "2026-06-07_wave1_track2_phase3_step3d_exit_structure"
)
EVAL_YEARS = (2021, 2022, 2023, 2024, 2025)
APEX_TIER1_DLL = 1000.0
TARGET_ANNUAL_USD = 30_000.0
DEFLATION_N = 20  # step3 5 + 3b 1 + 3c 9 + 3d 5

ENTRY_CFG = OteStrategyConfig(entry_style=ENTRY_OTE_ONLY, entry_mode=ENTRY_OTE_705)


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


def _session_frames(mnq: pl.DataFrame) -> dict[dt.date, pl.DataFrame]:
    out: dict[dt.date, pl.DataFrame] = {}
    for sd in mnq["cme_session_date"].unique().sort().to_list():
        if sd is None:
            continue
        out[sd] = mnq.filter(pl.col("cme_session_date") == sd).sort("timestamp")
    return out


def _dll_check(trades: list[OteExecutedTrade], annual_net: float) -> dict[str, object]:
    if annual_net <= 0:
        return {"fits_apex_tier1_dll": False, "note": "Non-positive annual net"}
    qty = TARGET_ANNUAL_USD / annual_net
    by_sess: dict[str, float] = {}
    for t in trades:
        if t.session_date is None:
            continue
        by_sess[t.session_date] = by_sess.get(t.session_date, 0.0) + t.net_pnl * qty
    max_loss = min(by_sess.values()) if by_sess else 0.0
    return {
        "sizing_qty_for_30k_yr": round(qty, 2),
        "max_session_net_loss_usd_at_qty": round(max_loss, 2),
        "fits_apex_tier1_dll": abs(max_loss) <= APEX_TIER1_DLL,
        "worst_session_date": min(by_sess, key=by_sess.get) if by_sess else None,
    }


def _exit_rates(trades: list[OteExecutedTrade]) -> dict[str, float]:
    if not trades:
        return {"stop_rate": 0.0, "target_rate": 0.0, "time_rate": 0.0, "other_rate": 0.0}
    counts: Counter[str] = Counter()
    for t in trades:
        r = t.exit_reason.lower()
        if "stop" in r:
            counts["stop"] += 1
        elif "target" in r:
            counts["target"] += 1
        elif r in ("time", "flatten", "close", "end_of_series_flatten"):
            counts["time"] += 1
        else:
            counts["other"] += 1
    n = len(trades)
    return {
        "stop_rate": counts["stop"] / n,
        "target_rate": counts["target"] / n,
        "time_rate": counts["time"] / n,
        "other_rate": counts["other"] / n,
        "stop_count": counts["stop"],
        "target_count": counts["target"],
        "time_count": counts["time"],
        "other_count": counts["other"],
    }


def _year_concentration(year_net: dict[str, float]) -> dict[str, Any]:
    if not year_net:
        return {"dominant_year": None, "dominant_share": 0.0, "positive_years": 0}
    total = sum(year_net.values())
    pos_years = sum(1 for v in year_net.values() if v > 0)
    if total <= 0:
        return {"dominant_year": None, "dominant_share": 0.0, "positive_years": pos_years}
    dom_yr = max(year_net, key=lambda y: year_net[y])
    return {
        "dominant_year": dom_yr,
        "dominant_share": year_net[dom_yr] / total,
        "positive_years": pos_years,
    }


def _render(report: dict[str, Any]) -> str:
    lines = [
        "# Wave 1 Track 2 — Phase 3 step 3d: OTE exit-structure test",
        "",
        f"**Date:** 2026-06-07  |  **git_sha:** `{report['git_sha']}`",
        f"**Deflation N:** {report['deflation_n']} (step3 5 + step3b 1 + step3c 9 + step3d 5)",
        "",
        "**Entry (frozen):** OTE 70.5% full RTH (`ote_only`). Exit structures vary per combo.",
        "",
        "## Diagnostic framing",
        "",
        report["diagnostic_verdict"],
        "",
        "## Results by combination",
        "",
    ]
    for cid, cfg in report["combinations"].items():
        v = cfg.get("validation_report", {})
        passed = v.get("passed", False)
        econ = cfg.get("frame_b", {})
        ex = cfg.get("exit_rates", {})
        yr = econ.get("year_net_usd", {})
        lines.append(
            f"### {cid} — {cfg.get('label', '')} — harness **{'PASS' if passed else 'FAIL'}**"
        )
        lines.append("")
        lines.append(f"- Stop / Target: **{cfg.get('stop_rule')}** + **{cfg.get('target_rule')}**")
        lines.append(f"- Exit remap rejects: **{sum(cfg.get('exit_rejects', {}).values()):,}**")
        lines.append(f"- Booked: **{cfg.get('booked', 0):,}**")
        lines.append(
            f"- WR: **{100 * econ.get('win_rate', 0):.1f}%** | "
            f"Avg win: **${econ.get('avg_win_usd', 0):.2f}** | "
            f"Avg loss: **${econ.get('avg_loss_usd', 0):.2f}** | "
            f"R:R: **{econ.get('reward_risk_ratio') or 0:.2f}**"
        )
        lines.append(f"- Net ticks/trade: **{econ.get('avg_net_ticks', 0):.2f}**")
        lines.append(f"- Frame B annual net: **${econ.get('annual_net_usd', 0):,.0f}/MNQ**")
        if yr:
            lines.append("- Year-by-year ($/MNQ):")
            for y, n in yr.items():
                lines.append(f"  - {y}: ${n:,.0f}")
        lines.append(
            f"- Exit rates: stop **{100 * ex.get('stop_rate', 0):.1f}%** | "
            f"target **{100 * ex.get('target_rate', 0):.1f}%** | "
            f"time **{100 * ex.get('time_rate', 0):.1f}%**"
        )
        dll = cfg.get("dll_check", {})
        lines.append(
            f"- Apex DLL fit ($30K/yr): **{'YES' if dll.get('fits_apex_tier1_dll') else 'NO'}**"
        )
        lines.append("- Harness:")
        for c in v.get("checks", []):
            mark = "PASS" if c["passed"] else "**FAIL**"
            lines.append(f"  - {c['check_id']}: {mark} — {c['message']}")
        lines.append("")
    lines.extend(
        [
            "## Verdict",
            "",
            report["verdict"],
            "",
            "## Operator summary",
            "",
            report["operator_summary"],
        ]
    )
    return "\n".join(lines)


def _build_verdict(combos: dict[str, Any]) -> tuple[str, str, str]:
    candidates: list[str] = []
    all_near_zero = True
    all_2022_driven = True
    for cid, cfg in combos.items():
        if not cfg.get("validation_report", {}).get("passed"):
            continue
        econ = cfg.get("frame_b", {})
        annual = econ.get("annual_net_usd", 0)
        ticks = econ.get("avg_net_ticks", 0)
        yr = econ.get("year_net_usd", {})
        conc = _year_concentration(yr)
        dll = cfg.get("dll_check", {})
        if annual > 500 and ticks > 0.5 and conc.get("positive_years", 0) >= 3:
            all_near_zero = False
        if conc.get("dominant_year") != "2022" or conc.get("dominant_share", 1) < 0.7:
            all_2022_driven = False
        if dll.get("fits_apex_tier1_dll") and annual > 0 and conc.get("positive_years", 0) >= 3:
            candidates.append(cid)

    if candidates:
        verdict = (
            f"**Genuine candidate(s):** {', '.join(candidates)} — harness-clean, multi-year "
            "positive, fits Apex tier-1 DLL. Proceed to account-class survey on winning structure."
        )
        diagnostic = "At least one realistic exit structure recovers tradeable edge from the OTE 70.5% entry."
    elif all_near_zero:
        verdict = (
            "**OTE entry has no persistent edge independent of exit.** All combinations are "
            "near-zero or negative despite reachable targets at structured R:R. OTE closes "
            "definitively — pivot to H7 opening gap or TTrades CISD."
        )
        diagnostic = (
            "No realistic exit structure recovers meaningful edge. Target-hit rates improve "
            "on fixed/ATR/2R exits vs baseline T1, but net economics stay near breakeven."
        )
    elif all_2022_driven:
        verdict = (
            "**Regime-dependence kill.** Edge appears concentrated in 2022 across exit "
            "structures — not a tradeable persistent edge. OTE closes definitively."
        )
        diagnostic = "Year-by-year P&L remains 2022-dominated even with improved exit structures."
    else:
        verdict = (
            "**Marginal economics, no DLL fit.** Some combos show modest positive Frame B net "
            "but fail Apex tier-1 DLL at $30K/yr sizing. Not a survey candidate."
        )
        diagnostic = (
            "Exit redesign improves target-hit rates but does not produce account-viable edge."
        )

    op_lines = [
        "| Combo | Harness | Annual/MNQ | Ticks/tr | Target% | DLL |",
        "|-------|---------|------------|----------|---------|-----|",
    ]
    for cid, cfg in combos.items():
        vpass = cfg.get("validation_report", {}).get("passed", False)
        econ = cfg.get("frame_b", {})
        ex = cfg.get("exit_rates", {})
        dll = cfg.get("dll_check", {})
        op_lines.append(
            f"| {cid} | {'PASS' if vpass else 'FAIL'} | "
            f"${econ.get('annual_net_usd', 0):,.0f} | {econ.get('avg_net_ticks', 0):.2f} | "
            f"{100 * ex.get('target_rate', 0):.0f}% | {'YES' if dll.get('fits_apex_tier1_dll') else 'NO'} |"
        )
    op_lines.append("")
    op_lines.append(
        f"**Does realistic exit recover OTE entry edge?** {'Yes' if candidates else 'No'}."
    )
    if candidates:
        op_lines.append(f"**Winning structure(s):** {', '.join(candidates)}")
    return diagnostic, verdict, "\n".join(op_lines)


def main() -> None:
    git_sha = _git_sha()
    bt_cfg = ote_research_backtest_config()
    print("Loading MNQ + ATR ...", flush=True)
    mnq = pd_mod.add_pd_arrays(
        add_atr(
            load_continuous_rth_mnq_style(
                DATA_ROOT,
                pattern=data_loader.MNQ_CONTRACT_GLOB,
                protocol_start=PROTOCOL_START,
                protocol_end_inclusive=PROTOCOL_END,
            )
        )
    )
    sessions = _session_frames(mnq)
    print("Scanning OTE 70.5% entry (frozen) ...", flush=True)
    scan = scan_setups_with_stats(mnq, config=ENTRY_CFG)
    print(f"  base setups passed scan: {len(scan.setups):,}", flush=True)

    results: dict[str, Any] = {}
    for cid, combo in STEP3D_COMBOS.items():
        print(f"Running {cid} ({combo.stop_rule} + {combo.target_rule}) ...", flush=True)
        remapped, exit_rejects = remap_setups_for_combo(scan.setups, sessions, combo)
        combined_rejects = dict(scan.geometry_rejects)
        for k, v in exit_rejects.items():
            combined_rejects[k] = combined_rejects.get(k, 0) + v
        batch = execute_setups_on_sessions(
            remapped,
            sessions,
            config=bt_cfg,
            geometry_rejects=combined_rejects,
        )
        batch.setups_detected = scan.setups_detected
        batch.setups_passed_scan = len(remapped)
        frame_b = economics_summary(batch.trades, eval_years=EVAL_YEARS)
        full = economics_summary(batch.trades)
        vrep = batch.validation_report.to_dict() if batch.validation_report else {"passed": False}
        v1 = next((c for c in vrep.get("checks", []) if c["check_id"] == "V1"), None)
        print(
            f"  booked={batch.setups_filled:,} V1={'PASS' if v1 and v1['passed'] else 'FAIL'} "
            f"target_hit={100 * _exit_rates(batch.trades).get('target_rate', 0):.1f}%",
            flush=True,
        )
        results[cid] = {
            "label": combo.rationale,
            "stop_rule": combo.stop_rule,
            "target_rule": combo.target_rule,
            "exit_rejects": exit_rejects,
            "scan_geometry_rejects": scan.geometry_rejects,
            "ledger_geometry_rejects": batch.ledger_geometry_rejects,
            "booked": batch.setups_filled,
            "frame_b": frame_b,
            "full_protocol": full,
            "exit_rates": _exit_rates(batch.trades),
            "year_concentration": _year_concentration(frame_b.get("year_net_usd", {})),
            "dll_check": _dll_check(batch.trades, frame_b.get("annual_net_usd", 0)),
            "validation_report": vrep,
        }

    diagnostic, verdict, operator = _build_verdict(results)
    report: dict[str, Any] = {
        "git_sha": git_sha,
        "deflation_n": DEFLATION_N,
        "entry_config": "OTE 70.5% ote_only full RTH",
        "scan_setups_passed": len(scan.setups),
        "scan_detected": scan.setups_detected,
        "combinations": results,
        "diagnostic_verdict": diagnostic,
        "verdict": verdict,
        "operator_summary": operator,
    }
    OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
    OUT_STEM.with_suffix(".json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    OUT_STEM.with_suffix(".md").write_text(_render(report), encoding="utf-8")
    print(f"\nWrote {OUT_STEM.with_suffix('.md')}", flush=True)
    print(verdict, flush=True)


if __name__ == "__main__":
    main()
