#!/usr/bin/env python3
"""Wave 1 Track 2 — Phase 3 step 3c: coherent cost-inclusive entry rebuilds.

Run: ``uv run python scripts/run_wave1_track2_phase3_step3c_coherent_rebuild.py``
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.data import data_loader
from quant_research.ict import pd_arrays as pd_mod
from quant_research.research_wave1.instrument_pipeline import load_continuous_rth_mnq_style
from quant_research.ict.ote_strategy import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    ENTRY_FVG_ONLY,
    ENTRY_OTE_ONLY,
    ENTRY_OTE_62,
    ENTRY_OTE_705,
    ET,
    OteSetup,
    OteStrategyConfig,
    scan_setups,
)

DATA_ROOT = _REPO / "data" / "raw"
PROTOCOL_START = dt.date(2020, 1, 1)
PROTOCOL_END = dt.date(2026, 4, 19)
OUT_STEM = _REPO / "notebooks" / "validation" / "2026-06-06_wave1_track2_phase3_step3c_coherent_rebuild"

MNQ_POINT_VALUE = 2.0
TICK_SIZE = 0.25
COMMISSION_RT = 1.98
SLIP_STOP_TIME = 0.50
SLIP_TARGET = 0.25
APEX_TIER1_DLL = 1000.0
TARGET_ANNUAL_USD = 30_000.0
FVG_AUDIT_THRESHOLD_TICKS = 10.0

# Running configuration count (deflation N tracking)
STEP3_CONFIGS = 5  # primary + 4 single-flip logs
STEP3B_UNIQUE_CONFIGS = 1  # FVG-only mis-paired (OTE-only duplicates 3c C1)
STEP3C_CONFIGS = 9  # C1×2 + C2×3×2 + C3×1

SESSION_WINDOWS: dict[str, tuple[dt.time, dt.time]] = {
    "W1_0930_1100": (dt.time(9, 30), dt.time(11, 0)),
    "W2_1000_1500": (dt.time(10, 0), dt.time(15, 0)),
    "W3_1300_1600": (dt.time(13, 0), dt.time(16, 0)),
}


def _git_sha() -> str:
    try:
        cp = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=_REPO,
            capture_output=True, text=True, check=False, timeout=30,
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


def _pnl_points(direction: str, entry: float, exit_price: float) -> float:
    if direction == DIRECTION_LONG:
        return exit_price - entry
    return entry - exit_price


def _in_window(ts: dt.datetime | None, start: dt.time, end: dt.time) -> bool:
    if ts is None:
        return False
    t = ts.astimezone(ET).time()
    return start <= t < end


@dataclass(frozen=True)
class SimTrade:
    session_date: str
    direction: str
    entry_price: float
    exit_price: float
    exit_reason: str
    gross_usd: float
    entry_timestamp: str
    entry_hour_et: int
    risk_points: float
    r_multiple: float


def _simulate_setup(
    setup: OteSetup,
    sess: pl.DataFrame,
) -> SimTrade | None:
    """Simulate one trade; entry/stop/target all from setup.entry_price."""
    if setup.entry_fill_index is None or setup.session_date is None:
        return None
    direction = setup.direction
    entry = setup.entry_price
    stop = setup.stop_arm_a
    target = setup.target_nearest
    fill_idx = setup.entry_fill_index

    highs = sess["high"].to_list()
    lows = sess["low"].to_list()
    closes = sess["close"].to_list()
    times = sess["timestamp"].to_list()
    is_long = direction == DIRECTION_LONG

    exit_reason = "time"
    exit_price = closes[-1]
    for i in range(fill_idx, sess.height):
        if is_long:
            if lows[i] <= stop:
                exit_reason, exit_price = "stop", stop
                break
            if highs[i] >= target:
                exit_reason, exit_price = "target", target
                break
        else:
            if highs[i] >= stop:
                exit_reason, exit_price = "stop", stop
                break
            if lows[i] <= target:
                exit_reason, exit_price = "target", target
                break

    gross_pts = _pnl_points(direction, entry, exit_price)
    risk = abs(entry - stop)
    r_mult = gross_pts / risk if risk > 0 else 0.0
    entry_ts = setup.entry_fill_timestamp
    entry_et = entry_ts.astimezone(ET) if entry_ts else None

    return SimTrade(
        session_date=setup.session_date.isoformat(),
        direction=direction,
        entry_price=entry,
        exit_price=exit_price,
        exit_reason=exit_reason,
        gross_usd=gross_pts * MNQ_POINT_VALUE,
        entry_timestamp=str(entry_ts),
        entry_hour_et=entry_et.hour if entry_et else -1,
        risk_points=risk,
        r_multiple=r_mult,
    )


def _net_usd(trade: SimTrade, *, slippage: bool) -> float:
    cost = COMMISSION_RT
    if slippage:
        if trade.exit_reason in ("stop", "time"):
            cost += SLIP_STOP_TIME
        elif trade.exit_reason == "target":
            cost += SLIP_TARGET
    return trade.gross_usd - cost


def _economics(
    trades: list[SimTrade],
    *,
    slippage: bool,
) -> dict[str, Any]:
    if not trades:
        return {"n_trades": 0}
    nets = [_net_usd(t, slippage=slippage) for t in trades]
    grosses = [t.gross_usd for t in trades]
    wins = [n for n in nets if n > 0]
    losses = [n for n in nets if n <= 0]
    by_year: dict[str, float] = defaultdict(float)
    for t, n in zip(trades, nets):
        by_year[t.session_date[:4]] += n
    n_years = max(len(by_year), 1)
    avg_win = statistics.mean(wins) if wins else 0.0
    avg_loss = statistics.mean(losses) if losses else 0.0
    return {
        "n_trades": len(trades),
        "trades_per_year": len(trades) / n_years,
        "total_net_usd": sum(nets),
        "annual_net_usd": sum(nets) / n_years,
        "avg_net_per_trade_usd": sum(nets) / len(trades),
        "avg_net_ticks": sum(nets) / len(trades) / (TICK_SIZE * MNQ_POINT_VALUE),
        "avg_gross_ticks": sum(grosses) / len(grosses) / (TICK_SIZE * MNQ_POINT_VALUE),
        "win_rate": len(wins) / len(trades),
        "avg_win_usd": avg_win,
        "avg_loss_usd": avg_loss,
        "reward_risk_ratio": abs(avg_win / avg_loss) if avg_loss else None,
        "avg_r": statistics.mean([t.r_multiple for t in trades]),
        "year_net_usd": dict(sorted(by_year.items())),
        "partial_years": ["2020", "2026"],
    }


def _hour_breakdown(trades: list[SimTrade], *, slippage: bool) -> dict[str, Any]:
    by_h: dict[int, list[float]] = defaultdict(list)
    for t in trades:
        if t.entry_hour_et >= 0:
            by_h[t.entry_hour_et].append(_net_usd(t, slippage=slippage))
    return {
        str(h): {
            "n": len(ps),
            "net_total": sum(ps),
            "net_avg": sum(ps) / len(ps),
            "win_rate": sum(1 for p in ps if p > 0) / len(ps),
        }
        for h, ps in sorted(by_h.items())
    }


def _dll_check(trades: list[SimTrade], *, slippage: bool, annual_net: float) -> dict[str, Any]:
    """Max session loss at qty sized for ~$30K/yr vs Apex tier-1 DLL."""
    if annual_net <= 0:
        return {
            "sizing_qty_for_30k_yr": None,
            "max_session_net_loss_usd_at_qty": None,
            "fits_apex_tier1_dll": False,
            "note": "Non-positive annual net — no sizing toward $30K/yr",
        }
    qty = TARGET_ANNUAL_USD / annual_net
    by_sess: dict[str, float] = defaultdict(float)
    for t in trades:
        by_sess[t.session_date] += _net_usd(t, slippage=slippage) * qty
    session_pnls = list(by_sess.values())
    max_loss = min(session_pnls) if session_pnls else 0.0
    return {
        "sizing_qty_for_30k_yr": round(qty, 2),
        "max_session_net_loss_usd_at_qty": round(max_loss, 2),
        "apex_tier1_dll_usd": APEX_TIER1_DLL,
        "fits_apex_tier1_dll": abs(max_loss) <= APEX_TIER1_DLL,
        "worst_session_date": min(by_sess, key=by_sess.get) if by_sess else None,
    }


def _audit_fvg_trades(
    trades: list[SimTrade],
    sessions: dict[dt.date, pl.DataFrame],
    setups_by_key: dict[tuple[str, int], OteSetup],
) -> dict[str, Any]:
    """Bar-by-bar audit on top 30 net-P&L trades when edge > threshold."""
    ranked = sorted(
        trades,
        key=lambda t: _net_usd(t, slippage=True),
        reverse=True,
    )[:30]
    ok = 0
    samples: list[dict[str, Any]] = []
    for t in ranked:
        setup = setups_by_key.get((t.session_date, 0))  # fallback
        # match by session+entry price
        key_candidates = [
            s for s in setups_by_key.values()
            if s.session_date and s.session_date.isoformat() == t.session_date
            and abs(s.entry_price - t.entry_price) < 0.01
        ]
        setup = key_candidates[0] if key_candidates else None
        if setup is None or setup.session_date is None:
            continue
        sess = sessions.get(setup.session_date)
        if sess is None:
            continue
        fi = setup.entry_fill_index
        if fi is None:
            continue
        lo = float(sess["low"][fi])
        hi = float(sess["high"][fi])
        reachable = (
            lo <= t.entry_price if t.direction == DIRECTION_LONG else hi >= t.entry_price
        )
        if reachable:
            ok += 1
        samples.append({
            "session": t.session_date,
            "entry": t.entry_price,
            "fill_index": fi,
            "reachable": reachable,
            "net_usd": _net_usd(t, slippage=True),
        })
    return {
        "audited": len(samples),
        "reachable_ok": ok,
        "all_reachable": ok == len(samples) if samples else False,
        "samples": samples[:5],
    }


def _run_config(
    label: str,
    setups: list[OteSetup],
    sessions: dict[dt.date, pl.DataFrame],
    *,
    window: tuple[dt.time, dt.time] | None = None,
) -> dict[str, Any]:
    trades: list[SimTrade] = []
    for setup in setups:
        if setup.session_date is None:
            continue
        if window and not _in_window(setup.entry_fill_timestamp, window[0], window[1]):
            continue
        sess = sessions.get(setup.session_date)
        if sess is None:
            continue
        sim = _simulate_setup(setup, sess)
        if sim is not None:
            trades.append(sim)

    comm = _economics(trades, slippage=False)
    slip = _economics(trades, slippage=True)
    return {
        "label": label,
        "n_trades": len(trades),
        "commission_only": comm,
        "commission_plus_slippage": slip,
        "hour_breakdown_net": _hour_breakdown(trades, slippage=True),
        "dll_check": _dll_check(
            trades, slippage=True, annual_net=slip.get("annual_net_usd", 0),
        ),
        "_trades": trades,
    }


def _render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Wave 1 Track 2 — Phase 3 step 3c: Coherent entry rebuilds",
        "",
        f"**Date:** 2026-06-06  ",
        f"**git_sha:** `{report['git_sha']}`  ",
        f"**Protocol:** {report['protocol_window'][0]} → {report['protocol_window'][1]}  ",
        "",
        "## Deflation N (running configuration count)",
        "",
        f"- Step 3 incoherent logs: **{report['deflation_n']['step3']}**",
        f"- Step 3b unique adds: **{report['deflation_n']['step3b']}**",
        f"- Step 3c coherent configs: **{report['deflation_n']['step3c']}**",
        f"- **Total standalone-OTE search N: {report['deflation_n']['total']}**",
        "",
        "## Cost model",
        "",
        report["cost_model"],
        "",
        "## Executive verdict",
        "",
        report["executive_verdict"],
        "",
    ]
    for section in report["configs"]:
        slip = section["commission_plus_slippage"]
        comm = section["commission_only"]
        lines.extend([
            f"### {section['label']}",
            "",
            f"- Trades: **{section['n_trades']:,}** ({slip.get('trades_per_year', 0):.0f}/yr)",
            f"- Net annual (comm only): **${comm.get('annual_net_usd', 0):,.0f}/MNQ**",
            f"- Net annual (comm+slip): **${slip.get('annual_net_usd', 0):,.0f}/MNQ**",
            f"- Net ticks/trade: **{slip.get('avg_net_ticks', 0):.2f}**",
            f"- WR: **{100 * slip.get('win_rate', 0):.1f}%** | R:R **{slip.get('reward_risk_ratio', 0):.2f}**",
            "",
            "**Year-by-year net (comm+slip):**",
        ])
        for y, p in slip.get("year_net_usd", {}).items():
            flag = " *(partial)*" if y in ("2020", "2026") else ""
            lines.append(f"- {y}: ${p:,.0f}{flag}")
        dll = section.get("dll_check", {})
        lines.append(
            f"- DLL fit ($30K/yr sizing): qty={dll.get('sizing_qty_for_30k_yr')}, "
            f"max session loss=${dll.get('max_session_net_loss_usd_at_qty')}, "
            f"fits tier-1={dll.get('fits_apex_tier1_dll')}"
        )
        lines.append("")
    if report.get("fvg_audit"):
        fa = report["fvg_audit"]
        lines.extend([
            "## Config 3 FVG audit (>10 ticks/trade trigger)",
            "",
            f"- Audited: {fa['audited']}, reachable: {fa['reachable_ok']}/{fa['audited']}",
            f"- Verdict: {fa['verdict']}",
            "",
        ])
    lines.extend(["## Stop conditions", ""])
    for k, v in report["stop_conditions"].items():
        lines.append(f"- **{k}:** {v}")
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
    sessions = _session_frames(mnq)

    print("Scanning OTE-only 70.5% ...", flush=True)
    setups_705 = scan_setups(
        mnq,
        config=OteStrategyConfig(entry_style=ENTRY_OTE_ONLY, entry_mode=ENTRY_OTE_705),
    )
    print(f"  -> {len(setups_705):,} setups", flush=True)

    print("Scanning OTE-only 62% ...", flush=True)
    setups_62 = scan_setups(
        mnq,
        config=OteStrategyConfig(entry_style=ENTRY_OTE_ONLY, entry_mode=ENTRY_OTE_62),
    )
    print(f"  -> {len(setups_62):,} setups", flush=True)

    print("Scanning FVG-only ...", flush=True)
    setups_fvg = scan_setups(
        mnq,
        config=OteStrategyConfig(entry_style=ENTRY_FVG_ONLY, entry_mode=ENTRY_OTE_705),
    )
    print(f"  -> {len(setups_fvg):,} setups", flush=True)

    results: list[dict[str, Any]] = []

    # Config 1
    results.append(_run_config("C1_OTE705_full_RTH", setups_705, sessions))
    results.append(_run_config("C1_OTE62_full_RTH", setups_62, sessions))

    # Config 2 — window variants
    for wname, window in SESSION_WINDOWS.items():
        results.append(_run_config(f"C2_{wname}_OTE705", setups_705, sessions, window=window))
        results.append(_run_config(f"C2_{wname}_OTE62", setups_62, sessions, window=window))

    # Config 3
    c3 = _run_config("C3_FVG_only_full_RTH", setups_fvg, sessions)
    results.append(c3)

    # Strip internal trade lists for JSON
    public_results = [{k: v for k, v in r.items() if k != "_trades"} for r in results]

    c1_705_slip = results[0]["commission_plus_slippage"]
    anchor_ok = abs(c1_705_slip.get("annual_net_usd", 0) - (-1185.66)) < 50

    fvg_slip = c3["commission_plus_slippage"]
    fvg_audit: dict[str, Any] | None = None
    if fvg_slip.get("avg_net_ticks", 0) > FVG_AUDIT_THRESHOLD_TICKS:
        setups_map = {
            (s.session_date.isoformat(), i): s
            for i, s in enumerate(setups_fvg)
            if s.session_date
        }
        fvg_audit = _audit_fvg_trades(c3["_trades"], sessions, setups_map)
        fvg_audit["verdict"] = (
            "AUDIT_REQUIRED"
            if not fvg_audit.get("all_reachable")
            else "All top-30 bar-reachable; edge magnitude still requires scrutiny"
        )
    else:
        fvg_audit = {
            "triggered": False,
            "avg_net_ticks": fvg_slip.get("avg_net_ticks"),
            "verdict": f"Below {FVG_AUDIT_THRESHOLD_TICKS}-tick threshold; no audit stop",
        }

    # Verdict
    positive_configs = [
        r["label"]
        for r in public_results
        if r["commission_plus_slippage"].get("annual_net_usd", 0) > 500
        and r["commission_plus_slippage"].get("avg_net_ticks", 0) > 1.0
    ]

    if positive_configs and fvg_slip.get("avg_net_ticks", 0) <= FVG_AUDIT_THRESHOLD_TICKS:
        exec_verdict = (
            f"Marginal/positive configs after costs: {positive_configs}. "
            "None clearly clears Apex DLL + material edge bar for step-4 screening."
        )
        proceed = False
    elif fvg_slip.get("avg_net_ticks", 0) > FVG_AUDIT_THRESHOLD_TICKS:
        exec_verdict = (
            "Config 3 FVG-only STILL shows >10 net ticks/trade after correct pairing. "
            f"Annual net ${fvg_slip.get('annual_net_usd', 0):,.0f}. Audit required before "
            "treating as edge."
        )
        proceed = False
    else:
        exec_verdict = (
            "**All coherent configs net-negative or marginal after full costs.** "
            "Standalone OTE/FVG does not show cost-surviving edge on MNQ. "
            "ICT track reassessment recommended (bias-gated path, different setup, or scope change)."
        )
        proceed = False

    report = {
        "wave": "Wave 1 Track 2 Phase 3 step 3c",
        "git_sha": git_sha,
        "protocol_window": [str(PROTOCOL_START), str(PROTOCOL_END)],
        "deflation_n": {
            "step3": STEP3_CONFIGS,
            "step3b": STEP3B_UNIQUE_CONFIGS,
            "step3c": STEP3C_CONFIGS,
            "total": STEP3_CONFIGS + STEP3B_UNIQUE_CONFIGS + STEP3C_CONFIGS,
            "note": "Step 3b OTE-only 705 duplicates C1 anchor; counted once under step3b unique.",
        },
        "cost_model": (
            f"Commission ${COMMISSION_RT}/RT. Slippage: ${SLIP_STOP_TIME} (1 tick) on stop/time "
            f"exits; ${SLIP_TARGET} (half-tick) on target. Limit entry: no entry slippage. "
            "Targets/stops always resolved from actual entry price."
        ),
        "c1_705_anchor_reproduces_3b": anchor_ok,
        "c1_705_annual_slip": c1_705_slip.get("annual_net_usd"),
        "configs": public_results,
        "fvg_audit": fvg_audit,
        "executive_verdict": exec_verdict,
        "stop_conditions": {
            "fvg_gt_10_ticks_audit": fvg_slip.get("avg_net_ticks", 0) > FVG_AUDIT_THRESHOLD_TICKS,
            "any_step4_candidate": proceed,
            "all_negative_or_marginal": len(positive_configs) == 0,
        },
    }

    OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
    OUT_STEM.with_suffix(".json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8",
    )
    OUT_STEM.with_suffix(".md").write_text(_render_md(report), encoding="utf-8")
    print(f"Wrote {OUT_STEM.with_suffix('.md')}", flush=True)
    print(f"C1 OTE705 anchor reproduces 3b: {anchor_ok} (${c1_705_slip.get('annual_net_usd', 0):,.0f}/yr)", flush=True)
    print(exec_verdict, flush=True)


if __name__ == "__main__":
    main()
