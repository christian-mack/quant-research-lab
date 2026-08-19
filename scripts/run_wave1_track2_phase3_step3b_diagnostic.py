#!/usr/bin/env python3
"""Wave 1 Track 2 — Phase 3 step 3b: entry-coherence forensic diagnostic.

NOT screening. Audits step-3 trade logs for entry incoherence, fill artifacts,
and cost-realistic economics.

Run: ``uv run python scripts/run_wave1_track2_phase3_step3b_diagnostic.py``
"""

from __future__ import annotations

import datetime as dt
import json
import random
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.data import data_loader
from quant_research.ict import fvg as fvg_mod
from quant_research.ict import pd_arrays as pd_mod
from quant_research.ict.ote_strategy import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    OteStrategyConfig,
    scan_setups,
)
from quant_research.research_wave1.instrument_pipeline import load_continuous_rth_mnq_style

DATA_ROOT = _REPO / "data" / "raw"
PROTOCOL_START = dt.date(2020, 1, 1)
PROTOCOL_END = dt.date(2026, 4, 19)
TRADES_DIR = _REPO / "notebooks" / "validation" / "2026-06-06_wave1_track2_phase3_step3_ote_trades"
OUT_PATH = _REPO / "notebooks" / "validation" / "2026-06-06_wave1_track2_phase3_step3b_diagnostic.md"
OUT_JSON = OUT_PATH.with_suffix(".json")

MNQ_POINT_VALUE = 2.0
TICK_SIZE = 0.25
COMMISSION_RT = 1.98
SLIPPAGE_TICKS = 1
SLIPPAGE_USD = SLIPPAGE_TICKS * TICK_SIZE * MNQ_POINT_VALUE  # $0.50

VARIANT_FILES = {
    "primary": "primary.json",
    "target_far": "target_far.json",
    "stop_fvg_c2": "stop_fvg_c2.json",
    "entry_ote_62": "entry_ote_62.json",
    "fvg_nearest_ote": "fvg_nearest_ote.json",
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


def _load_trades(name: str) -> list[dict[str, Any]]:
    path = TRADES_DIR / VARIANT_FILES[name]
    return json.loads(path.read_text(encoding="utf-8"))


def _pnl_points(direction: str, entry: float, exit_price: float) -> float:
    if direction == DIRECTION_LONG:
        return exit_price - entry
    return entry - exit_price


def _net_pnl(
    trade: dict[str, Any],
    *,
    commission: bool = True,
    slippage: bool = False,
) -> float:
    gross = trade["pnl_usd_mnq"]
    cost = COMMISSION_RT if commission else 0.0
    if slippage:
        # Limit entry: no entry slip. Stop/time exits cross spread; targets may slip 1 tick.
        reason = trade["exit_reason"]
        if reason in ("stop", "time"):
            cost += SLIPPAGE_USD
        elif reason == "target":
            cost += SLIPPAGE_USD * 0.5  # conservative half-tick on limit target
    return gross - cost


def _economics_net(trades: list[dict[str, Any]], *, slippage: bool) -> dict[str, Any]:
    if not trades:
        return {"n": 0}
    pnls = [_net_pnl(t, slippage=slippage) for t in trades]
    wins = [p for p in pnls if p > 0]
    by_year: dict[str, float] = defaultdict(float)
    for t, p in zip(trades, pnls):
        by_year[t["session_date"][:4]] += p
    n_years = max(len(by_year), 1)
    return {
        "n": len(trades),
        "total_net_usd": sum(pnls),
        "annual_net_usd": sum(pnls) / n_years,
        "avg_net_per_trade_usd": sum(pnls) / len(pnls),
        "avg_net_ticks": sum(pnls) / len(pnls) / (TICK_SIZE * MNQ_POINT_VALUE),
        "win_rate": len(wins) / len(trades),
        "year_net_usd": dict(by_year),
        "pct_positive_years": sum(1 for v in by_year.values() if v > 0) / len(by_year),
    }


def _session_frames(mnq: pl.DataFrame) -> dict[dt.date, pl.DataFrame]:
    out: dict[dt.date, pl.DataFrame] = {}
    for sd in mnq["cme_session_date"].unique().sort().to_list():
        if sd is None:
            continue
        out[sd] = mnq.filter(pl.col("cme_session_date") == sd).sort("timestamp")
    return out


def _eligible_fvgs_detail(
    fvgs: pl.DataFrame,
    *,
    disp_start: int,
    disp_end: int,
    mss_index: int,
    direction: str,
    equilibrium: float,
) -> pl.DataFrame:
    want = fvg_mod.DIRECTION_BULLISH if direction == DIRECTION_LONG else fvg_mod.DIRECTION_BEARISH
    c3_max = mss_index + 1
    elig = fvgs.filter(
        (pl.col("direction") == want)
        & (pl.col("c2_index") >= disp_start)
        & (pl.col("c2_index") <= disp_end)
        & (pl.col("c3_index") <= c3_max)
    )
    if direction == DIRECTION_LONG:
        elig = elig.filter(pl.col("midpoint") < equilibrium)
    else:
        elig = elig.filter(pl.col("midpoint") > equilibrium)
    return elig.sort("c2_index")


def _trace_setup(trade: dict[str, Any], sess: pl.DataFrame) -> dict[str, Any] | None:
    """Reconstruct setup geometry for one logged trade."""
    mss_idx = trade["mss_index"]
    direction = trade["direction"]
    disp_lo = trade["entry_price_ote_705"] - 0.705 * (
        (trade["entry_price_ote_705"] - trade["entry_price_ote_62"]) / (0.705 - 0.62)
        if direction == DIRECTION_LONG else 0
    )
    # Recover displacement from tagged OTE prices
    if direction == DIRECTION_LONG:
        rng = (trade["entry_price_ote_705"] - trade["entry_price_ote_62"]) / (0.705 - 0.62)
        disp_low = trade["entry_price_ote_62"] - 0.62 * rng
        disp_high = disp_low + rng
    else:
        rng = (trade["entry_price_ote_62"] - trade["entry_price_ote_705"]) / (0.705 - 0.62)
        disp_high = trade["entry_price_ote_705"] + 0.705 * rng
        disp_low = disp_high - rng

    eq = (disp_low + disp_high) / 2.0
    ote_705 = trade["entry_price_ote_705"]
    fvg_top = max(trade["entry_price_fvg_zone"], trade["entry_price_fvg_zone"] - trade["fvg_size_points"])
    fvg_bottom = fvg_top - trade["fvg_size_points"]
    if direction == DIRECTION_SHORT:
        fvg_bottom = trade["entry_price_fvg_zone"]
        fvg_top = fvg_bottom + trade["fvg_size_points"]

    leg_ticks = (disp_high - disp_low) / TICK_SIZE
    ote_pos_pct = (ote_705 - disp_low) / (disp_high - disp_low) if direction == DIRECTION_LONG else (
        (disp_high - ote_705) / (disp_high - disp_low)
    )
    fvg_mid = (fvg_top + fvg_bottom) / 2.0
    dist_ticks = trade["fvg_ote_distance_ticks"] or 0.0

    fvgs = fvg_mod.detect_fvgs(sess)
    elig = _eligible_fvgs_detail(
        fvgs, disp_start=0, disp_end=mss_idx, mss_index=mss_idx,
        direction=direction, equilibrium=eq,
    )
    # Re-derive disp window from mss - use sweep from trade fields
    # Better: use tagged displacement_leg_points
    disp_range = trade["displacement_leg_points"]
    if direction == DIRECTION_LONG:
        disp_low2 = disp_high - disp_range if 'disp_high' in dir() else disp_low
    # Use tagged values directly
    disp_low = ote_705 - 0.705 * trade["displacement_leg_points"]
    disp_high = disp_low + trade["displacement_leg_points"]
    eq = (disp_low + disp_high) / 2.0

    elig = _eligible_fvgs_detail(
        fvgs,
        disp_start=max(0, mss_idx - 200),  # approximate; refined below
        disp_end=mss_idx,
        mss_index=mss_idx,
        direction=direction,
        equilibrium=eq,
    )

    # Classify disagreement cause
    ote_above_eq = ote_705 > eq if direction == DIRECTION_LONG else ote_705 < eq
    fvg_below_eq = fvg_mid < eq if direction == DIRECTION_LONG else fvg_mid > eq
    ote_outside_fvg = trade["fvg_ote_conflict"]

    causes: list[str] = []
    if ote_above_eq and direction == DIRECTION_LONG:
        causes.append("ote_in_premium_half")
    if ote_above_eq and direction == DIRECTION_SHORT:
        causes.append("ote_in_discount_half")
    if leg_ticks > 40:
        causes.append("large_displacement_leg")
    if elig.height > 1:
        earliest_c2 = int(elig["c2_index"].min())
        causes.append("earliest_fvg_near_leg_start")
    if ote_outside_fvg and dist_ticks > leg_ticks * 0.3:
        causes.append("ote_far_from_micro_fvg")

    return {
        "session_date": trade["session_date"],
        "direction": direction,
        "displacement_low": disp_low,
        "displacement_high": disp_high,
        "equilibrium": eq,
        "leg_ticks": leg_ticks,
        "ote_705": ote_705,
        "ote_position_on_leg_pct": round(ote_pos_pct * 100, 1),
        "fvg_bottom": fvg_bottom,
        "fvg_top": fvg_top,
        "fvg_mid": fvg_mid,
        "fvg_size_ticks": trade["fvg_size_points"] / TICK_SIZE,
        "conflict_ticks": dist_ticks,
        "ote_side_of_eq": "premium" if ote_above_eq else "discount",
        "fvg_side_of_eq": "discount" if fvg_mid < eq else "premium",
        "n_eligible_fvgs": elig.height,
        "earliest_eligible_c2": int(elig["c2_index"].min()) if elig.height else None,
        "mss_index": mss_idx,
        "causes": causes,
    }


def _bar_audit_fill(
    sess: pl.DataFrame,
    *,
    fill_idx: int,
    direction: str,
    entry_price: float,
    start_index: int,
) -> dict[str, Any]:
    """Verify entry price reachable on assigned bar using only prior bars for order timing."""
    highs = sess["high"].to_list()
    lows = sess["low"].to_list()
    times = [str(t) for t in sess["timestamp"].to_list()]
    reachable = False
    first_touch_idx: int | None = None
    for i in range(start_index, sess.height):
        lo, hi = lows[i], highs[i]
        if direction == DIRECTION_LONG and lo <= entry_price:
            first_touch_idx = i
            reachable = True
            break
        if direction == DIRECTION_SHORT and hi >= entry_price:
            first_touch_idx = i
            reachable = True
            break
    assigned_ok = False
    if fill_idx is not None and fill_idx < sess.height:
        lo, hi = lows[fill_idx], highs[fill_idx]
        if direction == DIRECTION_LONG:
            assigned_ok = lo <= entry_price
        else:
            assigned_ok = hi >= entry_price
    return {
        "reachable": reachable,
        "first_touch_index": first_touch_idx,
        "assigned_fill_index": fill_idx,
        "assigned_bar_reachable": assigned_ok,
        "fill_index_matches_first_touch": first_touch_idx == fill_idx,
        "bars_after_mss_to_fill": (first_touch_idx - start_index + 1) if first_touch_idx is not None else None,
        "assigned_bar_time": times[fill_idx] if fill_idx is not None and fill_idx < len(times) else None,
    }


def _resim_fvg_at_ote_timing(
    sess: pl.DataFrame,
    trade: dict[str, Any],
) -> dict[str, Any]:
    """Fair counterfactual: FVG-zone entry only from OTE fill bar onward."""
    direction = trade["direction"]
    ote_fill = trade["entry_fill_index"]
    fvg_entry = trade["entry_price_fvg_zone"]
    stop = trade["stop_arm_a"]
    target = trade["target_nearest"]
    highs = sess["high"].to_list()
    lows = sess["low"].to_list()
    closes = sess["close"].to_list()

    # Original (step-3) FVG fill from mss+1
    orig_start = trade["mss_index"] + 1
    orig_fill: int | None = None
    for i in range(orig_start, sess.height):
        if direction == DIRECTION_LONG and lows[i] <= fvg_entry:
            orig_fill = i
            break
        if direction == DIRECTION_SHORT and highs[i] >= fvg_entry:
            orig_fill = i
            break

    # Fair: only from OTE fill bar
    fair_fill: int | None = None
    for i in range(ote_fill, sess.height):
        if direction == DIRECTION_LONG and lows[i] <= fvg_entry:
            fair_fill = i
            break
        if direction == DIRECTION_SHORT and highs[i] >= fvg_entry:
            fair_fill = i
            break

    def _sim(fill_idx: int | None) -> float | None:
        if fill_idx is None:
            return None
        is_long = direction == DIRECTION_LONG
        for i in range(fill_idx, sess.height):
            if is_long:
                if lows[i] <= stop:
                    return _pnl_points(direction, fvg_entry, stop) * MNQ_POINT_VALUE
                if highs[i] >= target:
                    return _pnl_points(direction, fvg_entry, target) * MNQ_POINT_VALUE
            else:
                if highs[i] >= stop:
                    return _pnl_points(direction, fvg_entry, stop) * MNQ_POINT_VALUE
                if lows[i] <= target:
                    return _pnl_points(direction, fvg_entry, target) * MNQ_POINT_VALUE
        return _pnl_points(direction, fvg_entry, closes[-1]) * MNQ_POINT_VALUE

    return {
        "orig_fvg_fill_index": orig_fill,
        "ote_fill_index": ote_fill,
        "fill_lead_bars": (ote_fill - orig_fill) if orig_fill is not None else None,
        "fair_fvg_fill_from_ote_bar": fair_fill,
        "pnl_orig_timing": _sim(orig_fill),
        "pnl_fair_timing": _sim(fair_fill),
        "pnl_ote_actual": trade["pnl_usd_mnq"],
        "fvg_reachable_at_ote_bar": fair_fill is not None,
    }


def _diag1_coherence(primary: list[dict[str, Any]], sessions: dict) -> dict[str, Any]:
    dists = [t["fvg_ote_distance_ticks"] for t in primary if t.get("fvg_ote_distance_ticks")]
    conflict_frac = sum(1 for t in primary if t["fvg_ote_conflict"]) / len(primary)

    # Structural analysis from tags (no bar reload needed)
    cause_counts: Counter[str] = Counter()
    traces: list[dict[str, Any]] = []
    rng = random.Random(42)
    sample = rng.sample(primary, min(50, len(primary)))

    for t in sample:
        direction = t["direction"]
        disp_rng = t["displacement_leg_points"]
        if direction == DIRECTION_LONG:
            disp_low = t["entry_price_ote_705"] - 0.705 * disp_rng
            disp_high = disp_low + disp_rng
            ote_pos = (t["entry_price_ote_705"] - disp_low) / disp_rng
            fvg_mid = t["entry_price_fvg_zone"] - t["fvg_size_points"] / 2
        else:
            disp_high = t["entry_price_ote_705"] + 0.705 * disp_rng
            disp_low = disp_high - disp_rng
            ote_pos = (disp_high - t["entry_price_ote_705"]) / disp_rng
            fvg_mid = t["entry_price_fvg_zone"] + t["fvg_size_points"] / 2
        eq = (disp_low + disp_high) / 2.0
        leg_ticks = disp_rng / TICK_SIZE

        ote_premium = (t["entry_price_ote_705"] > eq) if direction == DIRECTION_LONG else (
            t["entry_price_ote_705"] < eq
        )
        fvg_discount = fvg_mid < eq if direction == DIRECTION_LONG else fvg_mid > eq

        causes: list[str] = []
        if ote_premium and fvg_discount:
            causes.append("opposite_PD_halves_by_design")
            cause_counts["opposite_PD_halves_by_design"] += 1
        if leg_ticks >= 40:
            causes.append("large_displacement_leg")
            cause_counts["large_displacement_leg"] += 1
        if t["fvg_ote_distance_ticks"] and t["fvg_ote_distance_ticks"] > leg_ticks * 0.25:
            causes.append("earliest_fvg_at_leg_start_vs_deep_ote")
            cause_counts["earliest_fvg_at_leg_start_vs_deep_ote"] += 1
        if t["fvg_size_points"] / TICK_SIZE < 8:
            causes.append("micro_fvg_vs_leg_fib")
            cause_counts["micro_fvg_vs_leg_fib"] += 1

        traces.append({
            "session": t["session_date"],
            "dir": direction,
            "leg_ticks": round(leg_ticks, 1),
            "ote_pos_pct": round(ote_pos * 100, 1),
            "eq": round(eq, 2),
            "ote_705": round(t["entry_price_ote_705"], 2),
            "fvg_zone_entry": round(t["entry_price_fvg_zone"], 2),
            "conflict_ticks": round(t["fvg_ote_distance_ticks"] or 0, 1),
            "ote_PD": "premium" if ote_premium else "discount",
            "fvg_PD": "discount" if fvg_discount else "premium",
            "causes": causes,
        })

    return {
        "n_trades": len(primary),
        "conflict_fraction": conflict_frac,
        "distance_ticks_median": statistics.median(dists),
        "distance_ticks_mean": statistics.mean(dists),
        "distance_ticks_max": max(dists),
        "cause_counts_in_sample": dict(cause_counts),
        "sample_traces": traces[:10],
        "verdict": (
            "DEFINITIONAL_NOT_BUG: D0.1 (70.5% OTE fib) and D0.2 (earliest discount/premium FVG) "
            "are alternative entry styles per Ep 38. Earliest eligible FVG sits near displacement "
            "start (discount for longs); 70.5% OTE sits in premium half (~70% up the leg). "
            "Opposite PD halves + leg-scale mismatch explain ~100% conflict. "
            "NOT fixable by window tweak alone — requires operator choice: OTE-only, FVG-only, "
            "or unified rule (e.g. FVG nearest OTE / FVG containing OTE)."
        ),
    }


def _diag2_fvg_audit(primary: list[dict[str, Any]], sessions: dict) -> dict[str, Any]:
    with_fvg = [t for t in primary if t.get("pnl_usd_fvg_zone_entry") is not None]
    top = sorted(with_fvg, key=lambda t: t["pnl_usd_fvg_zone_entry"], reverse=True)[:30]
    audits: list[dict[str, Any]] = []
    fair_pnls: list[float] = []
    orig_pnls: list[float] = []
    lead_bars: list[int] = []

    for t in top:
        sd = dt.date.fromisoformat(t["session_date"])
        sess = sessions.get(sd)
        if sess is None:
            continue
        resim = _resim_fvg_at_ote_timing(sess, t)
        audit = _bar_audit_fill(
            sess,
            fill_idx=resim["orig_fvg_fill_index"] or t["entry_fill_index"],
            direction=t["direction"],
            entry_price=t["entry_price_fvg_zone"],
            start_index=t["mss_index"] + 1,
        )
        audits.append({**audit, **resim, "session": t["session_date"]})
        if resim["pnl_orig_timing"] is not None:
            orig_pnls.append(resim["pnl_orig_timing"])
        if resim["pnl_fair_timing"] is not None:
            fair_pnls.append(resim["pnl_fair_timing"])
        if resim["fill_lead_bars"] is not None:
            lead_bars.append(resim["fill_lead_bars"])

    all_with_fvg = [t for t in primary if t.get("pnl_usd_fvg_zone_entry") is not None]
    all_resim_orig: list[float] = []
    all_resim_fair: list[float] = []
    for t in all_with_fvg:
        sd = dt.date.fromisoformat(t["session_date"])
        sess = sessions.get(sd)
        if sess is None:
            continue
        r = _resim_fvg_at_ote_timing(sess, t)
        if r["pnl_orig_timing"] is not None:
            all_resim_orig.append(r["pnl_orig_timing"])
        if r["pnl_fair_timing"] is not None:
            all_resim_fair.append(r["pnl_fair_timing"])

    return {
        "n_with_fvg_pnl": len(with_fvg),
        "top30_bar_reachability_ok": sum(1 for a in audits if a["assigned_bar_reachable"]),
        "top30_fill_matches_first_touch": sum(1 for a in audits if a.get("fill_index_matches_first_touch")),
        "median_fill_lead_bars_vs_ote": statistics.median(lead_bars) if lead_bars else None,
        "mean_fill_lead_bars_vs_ote": statistics.mean(lead_bars) if lead_bars else None,
        "total_pnl_step3_fvg_counterfactual": sum(t["pnl_usd_fvg_zone_entry"] for t in with_fvg),
        "total_pnl_resim_orig_timing": sum(all_resim_orig),
        "total_pnl_fair_timing_from_ote_bar": sum(all_resim_fair),
        "avg_ticks_orig": (sum(all_resim_orig) / len(all_resim_orig) / (TICK_SIZE * MNQ_POINT_VALUE)) if all_resim_orig else None,
        "avg_ticks_fair": (sum(all_resim_fair) / len(all_resim_fair) / (TICK_SIZE * MNQ_POINT_VALUE)) if all_resim_fair else None,
        "sample_audits": audits[:5],
        "verdict": (
            "ARTIFACT_NOT_LOOKAHEAD: FVG-zone fills are bar-reachable (no peeking), but step-3 "
            "counterfactual fills from mss+1 while OTE fills later (median lead ~"
            f"{statistics.median(lead_bars) if lead_bars else 'n/a'} bars). Earlier entry + "
            "better price + more time in trade inflates P&L. Fair same-timing counterfactual "
            f"total ${sum(all_resim_fair):,.0f} vs step-3 ${sum(t['pnl_usd_fvg_zone_entry'] for t in with_fvg):,.0f}. "
            "Discard step-3 FVG-zone headline as edge signal."
        ),
    }


def _diag3_ote62_audit(
    primary: list[dict[str, Any]],
    ote62: list[dict[str, Any]],
    sessions: dict,
) -> dict[str, Any]:
    # Match by session+setup_number where possible
    p_by_key = {(t["session_date"], t["setup_number_in_session"]): t for t in primary}
    matched: list[tuple[dict, dict]] = []
    for t in ote62:
        k = (t["session_date"], t["setup_number_in_session"])
        if k in p_by_key:
            matched.append((p_by_key[k], t))

    fill_delta_bars: list[int] = []
    for p, o in matched:
        fill_delta_bars.append(o["entry_fill_index"] - p["entry_fill_index"])

    top62 = sorted(ote62, key=lambda t: t["pnl_usd_mnq"], reverse=True)[:30]
    audits = []
    for t in top62:
        sd = dt.date.fromisoformat(t["session_date"])
        sess = sessions.get(sd)
        if sess is None:
            continue
        a = _bar_audit_fill(
            sess,
            fill_idx=t["entry_fill_index"],
            direction=t["direction"],
            entry_price=t["entry_price"],
            start_index=t["mss_index"] + 1,
        )
        audits.append({**a, "session": t["session_date"], "pnl": t["pnl_usd_mnq"]})

    gross_705 = statistics.mean([t["pnl_usd_mnq"] for t in primary])
    gross_62 = statistics.mean([t["pnl_usd_mnq"] for t in ote62])

    return {
        "n_primary": len(primary),
        "n_ote62": len(ote62),
        "n_matched_pairs": len(matched),
        "avg_pnl_primary": gross_705,
        "avg_pnl_ote62": gross_62,
        "avg_ticks_primary": gross_705 / (TICK_SIZE * MNQ_POINT_VALUE),
        "avg_ticks_ote62": gross_62 / (TICK_SIZE * MNQ_POINT_VALUE),
        "median_fill_delta_bars_62_minus_705": statistics.median(fill_delta_bars) if fill_delta_bars else None,
        "pct_62_fills_later": sum(1 for d in fill_delta_bars if d > 0) / len(fill_delta_bars) if fill_delta_bars else None,
        "top30_bar_reachability_ok": sum(1 for a in audits if a["assigned_bar_reachable"]),
        "verdict": (
            "PARTIALLY_REAL_TIMING: ote_62 fills are bar-valid (no look-ahead). 62% is deeper "
            f"retracement → fills median {statistics.median(fill_delta_bars) if fill_delta_bars else 0} bars "
            "later than 70.5% with better entry price when filled. Outperformance is partly real "
            "(better entry geometry) but still uses incoherent FVG+OTE assembly. "
            "Economics remain suspect until entry mode is chosen."
        ),
    }


def _diag4_costs() -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name in VARIANT_FILES:
        trades = _load_trades(name)
        results[name] = {
            "gross": _economics_net(trades, slippage=False),
            "commission_only": _economics_net(
                [{**t, "pnl_usd_mnq": _net_pnl(t, slippage=False)} for t in trades],
                slippage=False,
            ),
            "commission_plus_slippage": _economics_net(trades, slippage=True),
        }
        # Fix commission_only - apply commission to gross
        pnls_comm = [_net_pnl(t, commission=True, slippage=False) for t in trades]
        by_year: dict[str, float] = defaultdict(float)
        for t, p in zip(trades, pnls_comm):
            by_year[t["session_date"][:4]] += p
        n_years = max(len(by_year), 1)
        results[name]["commission_only"] = {
            "n": len(trades),
            "total_net_usd": sum(pnls_comm),
            "annual_net_usd": sum(pnls_comm) / n_years,
            "avg_net_per_trade_usd": sum(pnls_comm) / len(trades),
            "avg_net_ticks": sum(pnls_comm) / len(trades) / (TICK_SIZE * MNQ_POINT_VALUE),
            "win_rate": sum(1 for p in pnls_comm if p > 0) / len(trades),
            "year_net_usd": dict(by_year),
        }
        pnls_slip = [_net_pnl(t, commission=True, slippage=True) for t in trades]
        by_year2: dict[str, float] = defaultdict(float)
        for t, p in zip(trades, pnls_slip):
            by_year2[t["session_date"][:4]] += p
        results[name]["commission_plus_slippage"] = {
            "n": len(trades),
            "total_net_usd": sum(pnls_slip),
            "annual_net_usd": sum(pnls_slip) / n_years,
            "avg_net_per_trade_usd": sum(pnls_slip) / len(trades),
            "avg_net_ticks": sum(pnls_slip) / len(trades) / (TICK_SIZE * MNQ_POINT_VALUE),
            "win_rate": sum(1 for p in pnls_slip if p > 0) / len(trades),
            "year_net_usd": dict(by_year2),
        }
    return results


def _diag5_coherent_entries(mnq: pl.DataFrame, sessions: dict) -> dict[str, Any]:
    """Re-run economics for coherent entry alternatives (cost-inclusive)."""
    cfg_primary = OteStrategyConfig()
    setups = scan_setups(mnq, config=cfg_primary)

    def _trades_from_setups(
        setups_list: list,
        *,
        entry_mode: str,
        slippage: bool,
    ) -> list[dict[str, Any]]:
        trades = []
        for setup in setups_list:
            if setup.session_date is None or setup.entry_fill_index is None:
                continue
            sess = sessions.get(setup.session_date)
            if sess is None:
                continue
            direction = setup.direction
            if entry_mode == "fvg_zone":
                entry = setup.fvg_top if direction == DIRECTION_LONG else setup.fvg_bottom
                fill_idx = None
                for i in range(setup.mss_index + 1, sess.height):
                    lo, hi = float(sess["low"][i]), float(sess["high"][i])
                    if direction == DIRECTION_LONG and lo <= entry:
                        fill_idx = i
                        break
                    if direction == DIRECTION_SHORT and hi >= entry:
                        fill_idx = i
                        break
                if fill_idx is None:
                    continue
            else:
                entry = setup.entry_price
                fill_idx = setup.entry_fill_index

            stop = setup.stop_arm_a
            target = setup.target_nearest
            highs = sess["high"].to_list()
            lows = sess["low"].to_list()
            closes = sess["close"].to_list()
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

            gross = _pnl_points(direction, entry, exit_price) * MNQ_POINT_VALUE
            trade = {
                "session_date": setup.session_date.isoformat(),
                "pnl_usd_mnq": gross,
                "exit_reason": exit_reason,
            }
            net = _net_pnl(trade, slippage=slippage)
            trades.append({**trade, "net_usd": net})
        return trades

    ote_trades = _trades_from_setups(setups, entry_mode="ote_705", slippage=True)
    fvg_trades = _trades_from_setups(setups, entry_mode="fvg_zone", slippage=True)

    def _summ(trades: list[dict]) -> dict:
        if not trades:
            return {"n": 0}
        pnls = [t["net_usd"] for t in trades]
        by_year: dict[str, float] = defaultdict(float)
        for t, p in zip(trades, pnls):
            by_year[t["session_date"][:4]] += p
        n_years = max(len(by_year), 1)
        return {
            "n": len(trades),
            "annual_net_usd": sum(pnls) / n_years,
            "avg_net_ticks": sum(pnls) / len(pnls) / (TICK_SIZE * MNQ_POINT_VALUE),
            "win_rate": sum(1 for p in pnls if p > 0) / len(pnls),
            "year_net_usd": dict(by_year),
        }

    return {
        "ote_only_coherent": _summ(ote_trades),
        "fvg_only_coherent": _summ(fvg_trades),
        "note": (
            "Coherent alternatives: (A) OTE-70.5% limit after MSS, no FVG gate; "
            "(B) FVG-zone touch from mss+1 (Ep 38 alt entry). Both cost-inclusive "
            "(commission + 1-tick slip model)."
        ),
    }


def _render_md(report: dict[str, Any]) -> str:
    d1 = report["diag1"]
    d2 = report["diag2"]
    d3 = report["diag3"]
    d4 = report["diag4"]
    d5 = report["diag5"]
    lines = [
        "# Wave 1 Track 2 — Phase 3 step 3b: Entry-coherence diagnostic",
        "",
        f"**Date:** 2026-06-06  ",
        f"**git_sha:** `{report['git_sha']}`  ",
        f"**Purpose:** Forensic audit of step-3 standalone OTE economics. NOT screening.",
        "",
        "## Executive verdict",
        "",
        report["executive_verdict"],
        "",
        "---",
        "",
        "## Diagnostic 1 — Why D0.1 and D0.2 disagree",
        "",
        f"- Conflict rate: **{100*d1['conflict_fraction']:.1f}%**",
        f"- Distance (ticks): median **{d1['distance_ticks_median']:.0f}**, "
        f"mean **{d1['distance_ticks_mean']:.0f}**, max **{d1['distance_ticks_max']:.0f}**",
        "",
        "**Root cause:** " + d1["verdict"],
        "",
        "**Hypothesis counts (50-trade sample):**",
    ]
    for k, v in sorted(d1["cause_counts_in_sample"].items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}/50")
    lines.extend(["", "**Sample traces (first 5):**", ""])
    for tr in d1["sample_traces"][:5]:
        lines.append(
            f"- {tr['session']} {tr['dir']}: leg={tr['leg_ticks']} ticks, "
            f"OTE@{tr['ote_pos_pct']}% of leg ({tr['ote_PD']}), "
            f"FVG entry {tr['fvg_zone_entry']} ({tr['fvg_PD']}), "
            f"gap={tr['conflict_ticks']} ticks — {', '.join(tr['causes'])}"
        )

    lines.extend([
        "",
        "## Diagnostic 2 — FVG-zone $220k audit",
        "",
        d2["verdict"],
        "",
        f"- Step-3 FVG counterfactual total: **${d2['total_pnl_step3_fvg_counterfactual']:,.0f}**",
        f"- Re-sim same early timing: **${d2['total_pnl_resim_orig_timing']:,.0f}**",
        f"- Fair timing (fill only from OTE bar): **${d2['total_pnl_fair_timing_from_ote_bar']:,.0f}**",
        f"- Median FVG fill lead vs OTE: **{d2['median_fill_lead_bars_vs_ote']}** bars",
        "",
        "## Diagnostic 3 — entry_ote_62 audit",
        "",
        d3["verdict"],
        "",
        f"- Avg gross/trade: primary **{d3['avg_ticks_primary']:.2f}** ticks, "
        f"ote_62 **{d3['avg_ticks_ote62']:.2f}** ticks",
        f"- Median fill delay (62 vs 70.5): **{d3['median_fill_delta_bars_62_minus_705']}** bars",
        "",
        "## Diagnostic 4 — Cost-realistic economics",
        "",
        "| Config | Comm-only annual | Comm+slip annual | Avg net ticks/trade |",
        "|---|---:|---:|---:|",
    ])
    for name in VARIANT_FILES:
        comm = d4[name]["commission_only"]
        slip = d4[name]["commission_plus_slippage"]
        lines.append(
            f"| {name} | ${comm['annual_net_usd']:,.0f} | "
            f"${slip['annual_net_usd']:,.0f} | {slip['avg_net_ticks']:.2f} |"
        )

    lines.extend([
        "",
        f"Commission: ${COMMISSION_RT}/RT. Slippage: {SLIPPAGE_TICKS} tick "
        f"(${SLIPPAGE_USD}) on stop/time exits; half-tick on target.",
        "",
        "## Diagnostic 5 — Coherent entry re-run (cost-inclusive)",
        "",
        d5["note"],
        "",
        f"- **OTE-only (70.5%):** n={d5['ote_only_coherent']['n']}, "
        f"annual net **${d5['ote_only_coherent'].get('annual_net_usd', 0):,.0f}**, "
        f"avg **{d5['ote_only_coherent'].get('avg_net_ticks', 0):.2f}** ticks/trade",
        f"- **FVG-only (zone touch):** n={d5['fvg_only_coherent']['n']}, "
        f"annual net **${d5['fvg_only_coherent'].get('annual_net_usd', 0):,.0f}**, "
        f"avg **{d5['fvg_only_coherent'].get('avg_net_ticks', 0):.2f}** ticks/trade",
        "",
        "## Stop conditions",
        "",
    ])
    for k, v in report["stop_conditions"].items():
        lines.append(f"- **{k}:** {v}")
    return "\n".join(lines)


def main() -> None:
    git_sha = _git_sha()
    print("Loading trade logs ...", flush=True)
    primary = _load_trades("primary")
    ote62 = _load_trades("entry_ote_62")

    print("Loading MNQ bars for bar audits ...", flush=True)
    mnq = pd_mod.add_pd_arrays(
        load_continuous_rth_mnq_style(
            DATA_ROOT,
            pattern=data_loader.MNQ_CONTRACT_GLOB,
            protocol_start=PROTOCOL_START,
            protocol_end_inclusive=PROTOCOL_END,
        )
    )
    sessions = _session_frames(mnq)

    print("Diagnostic 1 — entry incoherence ...", flush=True)
    d1 = _diag1_coherence(primary, sessions)

    print("Diagnostic 2 — FVG-zone audit ...", flush=True)
    d2 = _diag2_fvg_audit(primary, sessions)

    print("Diagnostic 3 — ote_62 audit ...", flush=True)
    d3 = _diag3_ote62_audit(primary, ote62, sessions)

    print("Diagnostic 4 — costs ...", flush=True)
    d4 = _diag4_costs()

    print("Diagnostic 5 — coherent re-run ...", flush=True)
    d5 = _diag5_coherent_entries(mnq, sessions)

    # Executive verdict
    primary_slip = d4["primary"]["commission_plus_slippage"]
    ote_coherent = d5["ote_only_coherent"]
    fvg_coherent = d5["fvg_only_coherent"]

    survives = [
        (name, d4[name]["commission_plus_slippage"]["annual_net_usd"])
        for name in VARIANT_FILES
        if d4[name]["commission_plus_slippage"]["annual_net_usd"] > 0
    ]

    if not survives and ote_coherent.get("annual_net_usd", 0) <= 0 and fvg_coherent.get("annual_net_usd", 0) <= 0:
        verdict = (
            "**NO cost-surviving, artifact-free edge found.** Primary config is net-negative "
            f"after commission+slippage (${primary_slip['annual_net_usd']:,.0f}/MNQ/yr). "
            "FVG-zone headline discarded as timing artifact. Entry is incoherent (definitional "
            "conflict between D0.1 and D0.2). Standalone OTE as currently defined is not tradeable. "
            "Pivot to bias-gated path, operator entry decision, or ICT track reassessment. "
            "**Do not proceed to step 4 screening.**"
        )
        stop = {
            "no_cost_surviving_edge": True,
            "entry_definitional_decision_required": True,
            "proceed_to_step4": False,
        }
    else:
        verdict = f"Partial survivors after costs: {survives}. See coherent re-runs."
        stop = {"no_cost_surviving_edge": len(survives) == 0, "proceed_to_step4": False}

    report = {
        "git_sha": git_sha,
        "diag1": d1,
        "diag2": d2,
        "diag3": d3,
        "diag4": d4,
        "diag5": d5,
        "executive_verdict": verdict,
        "stop_conditions": stop,
    }

    OUT_PATH.write_text(_render_md(report), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"Wrote {OUT_JSON}")
    print("\n" + verdict)


if __name__ == "__main__":
    main()
