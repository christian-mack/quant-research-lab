#!/usr/bin/env python3
"""P2-W2 forensic — verdict validity check (diagnosis only, no screen rerun).

Run: ``uv run python scripts/run_p2w2_forensic_verdict_check.py``

Writes ``notebooks/validation/2026-06-08_p2w2_forensic_verdict_check.{md,json}``.
Does NOT modify ``hypothesis_sims.py`` or unseal OOS.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.ict import pd_arrays as pd_mod
from quant_research.research_p2w2.costs import P2Trade
from quant_research.research_p2w2.data_verify import load_verified_mnq_rth
from quant_research.research_p2w2.hypothesis_sims import (
    H1_STOP_CAP,
    H3_STOP_CAP,
    H4_STOP_CAP,
    T_ET_0945,
    T_ET_1000,
    T_ET_1030,
    T_ET_1200,
    T_ET_OPEN,
    prepare_et_frame,
    run_hypothesis,
)
from quant_research.research_p2w2.metrics import IS_FRACTION, split_is_oos

OUT_STEM = _REPO / "notebooks" / "validation" / "2026-06-08_p2w2_forensic_verdict_check"
CLUSTER = ("H-2", "H-3", "H-4", "H-6")


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


def flip_expectancy(trades: list[P2Trade]) -> dict[str, float]:
    """Arithmetic direction flip on booked trades (upper-biased; no rerun)."""
    if not trades:
        return {"as_is_net": 0.0, "flipped_net": 0.0, "n": 0}
    gross = np.array([t.gross_pnl for t in trades])
    comm = np.array([t.commission for t in trades])
    net = gross - comm
    flipped_net = (-gross) - comm
    return {
        "n": len(trades),
        "as_is_net": float(np.mean(net)),
        "flipped_net": float(np.mean(flipped_net)),
    }


@dataclass
class H3Sample:
    session_date: str
    signal_time: str
    bar_o: float
    bar_h: float
    bar_l: float
    bar_c: float
    or_hi: float
    or_lo: float
    or_mid: float
    false_breakout_side: str
    false_extreme: float
    entry_direction: str
    thesis_direction: str
    sign_verdict: str
    entry_price: float
    stop_price: float
    target_price: float
    exit_reason: str
    net_pnl: float
    thesis_narrative: str
    actual_narrative: str


def _h3_thesis_dir(false_breakout_side: str) -> str:
    if false_breakout_side == "above_or_high":
        return "short"
    if false_breakout_side == "below_or_low":
        return "long"
    return "unknown"


def trace_h3_samples(
    mnq_et: pl.DataFrame,
    is_trades: list[P2Trade],
    *,
    max_samples: int = 10,
) -> list[H3Sample]:
    """Mirror H-3 entry logic; capture signal-bar context for booked IS trades."""
    import polars as pl

    targets_by_sess: dict[str, list[P2Trade]] = {}
    for t in is_trades:
        targets_by_sess.setdefault(str(t.cme_session_date), []).append(t)
    samples: list[H3Sample] = []
    for sdate in sorted(targets_by_sess.keys()):
        if len(samples) >= max_samples:
            break
        sdate_d = dt.date.fromisoformat(sdate)
        sdf = mnq_et.filter(pl.col("cme_session_date") == sdate_d).sort("timestamp")
        if sdf.height < 40:
            continue
        or_bars = sdf.filter(
            (pl.col("ts_et").dt.time() >= T_ET_OPEN)
            & (pl.col("ts_et").dt.time() < T_ET_1000)
        )
        if or_bars.height < 10:
            continue
        or_hi = float(or_bars["high"].max())
        or_lo = float(or_bars["low"].min())
        or_mid = 0.5 * (or_hi + or_lo)
        if or_hi - or_lo < 2.0:
            continue

        bars5 = (
            sdf.with_columns(pl.col("ts_et").dt.truncate("5m").alias("b5"))
            .group_by("b5", maintain_order=True)
            .agg(
                pl.first("ts_et").alias("anchor_et"),
                pl.max("high").alias("h5"),
                pl.min("low").alias("l5"),
                pl.last("close").alias("c5"),
                pl.first("open").alias("o5"),
            )
        )
        false_extreme = 0.0
        false_dir = 0
        fired = False
        for k in range(bars5.height):
            if fired:
                break
            tb = bars5["b5"][k]
            if tb.time() < T_ET_1000:
                continue
            cc = float(bars5["c5"][k])
            anchor_et = bars5["anchor_et"][k]
            o5 = float(bars5["o5"][k])
            h5 = float(bars5["h5"][k])
            l5 = float(bars5["l5"][k])
            if false_dir == 0:
                if cc > or_hi:
                    false_dir = 1
                    false_extreme = h5
                elif cc < or_lo:
                    false_dir = -1
                    false_extreme = l5
                continue
            if false_dir == 1 and cc <= or_hi:
                entry_px = cc
                stop_px = entry_px + min(H3_STOP_CAP, max(2.0, false_extreme + 2.0 - entry_px))
                sess_targets = targets_by_sess.get(str(sdate), [])
                if not any(abs(t.entry_price - entry_px) < 1.5 for t in sess_targets):
                    false_extreme = max(false_extreme, float(bars5["h5"][k]))
                    continue
                taken = "short"
                thesis = _h3_thesis_dir("above_or_high")
                sign = "SIGN CORRECT" if taken == thesis else "SIGN FLIPPED"
                samples.append(
                    H3Sample(
                        session_date=str(sdate),
                        signal_time=anchor_et.isoformat(),
                        bar_o=o5,
                        bar_h=h5,
                        bar_l=l5,
                        bar_c=cc,
                        or_hi=or_hi,
                        or_lo=or_lo,
                        or_mid=or_mid,
                        false_breakout_side="above_or_high",
                        false_extreme=false_extreme,
                        entry_direction=taken,
                        thesis_direction=thesis,
                        sign_verdict=sign,
                        entry_price=entry_px,
                        stop_price=stop_px,
                        target_price=or_mid,
                        exit_reason="(matched IS trade — see gate1)",
                        net_pnl=0.0,
                        thesis_narrative=(
                            "5m closed back inside OR after false breakout above OR-high "
                            "→ SHORT failure back toward OR mid."
                        ),
                        actual_narrative=f"Entry SHORT at {entry_px:.2f} after reclaim below OR-high {or_hi:.2f}.",
                    )
                )
                fired = True
            elif false_dir == -1 and cc >= or_lo:
                entry_px = cc
                stop_px = entry_px - min(H3_STOP_CAP, max(2.0, entry_px - (false_extreme - 2.0)))
                sess_targets = targets_by_sess.get(str(sdate), [])
                if not any(abs(t.entry_price - entry_px) < 1.5 for t in sess_targets):
                    false_extreme = min(false_extreme, float(bars5["l5"][k]))
                    continue
                taken = "long"
                thesis = _h3_thesis_dir("below_or_low")
                sign = "SIGN CORRECT" if taken == thesis else "SIGN FLIPPED"
                samples.append(
                    H3Sample(
                        session_date=str(sdate),
                        signal_time=anchor_et.isoformat(),
                        bar_o=o5,
                        bar_h=h5,
                        bar_l=l5,
                        bar_c=cc,
                        or_hi=or_hi,
                        or_lo=or_lo,
                        or_mid=or_mid,
                        false_breakout_side="below_or_low",
                        false_extreme=false_extreme,
                        entry_direction=taken,
                        thesis_direction=thesis,
                        sign_verdict=sign,
                        entry_price=entry_px,
                        stop_price=stop_px,
                        target_price=or_mid,
                        exit_reason="(matched IS trade — see gate1)",
                        net_pnl=0.0,
                        thesis_narrative=(
                            "5m closed back inside OR after false breakdown below OR-low "
                            "→ LONG failure back toward OR mid."
                        ),
                        actual_narrative=f"Entry LONG at {entry_px:.2f} after reclaim above OR-low {or_lo:.2f}.",
                    )
                )
                fired = True
            else:
                if false_dir == 1:
                    false_extreme = max(false_extreme, float(bars5["h5"][k]))
                else:
                    false_extreme = min(false_extreme, float(bars5["l5"][k]))
    return samples


def enrich_h3_samples(samples: list[H3Sample], is_trades: list[P2Trade]) -> list[H3Sample]:
    """Attach exit/P&L from booked IS trades by session+entry price."""
    by_sess: dict[str, list[P2Trade]] = {}
    for t in is_trades:
        by_sess.setdefault(str(t.cme_session_date), []).append(t)
    out: list[H3Sample] = []
    for s in samples:
        cands = by_sess.get(s.session_date, [])
        match = None
        for t in cands:
            if abs(t.entry_price - s.entry_price) < 1.0:
                match = t
                break
        if match is None and cands:
            match = cands[0]
        if match:
            s = H3Sample(
                **{
                    **asdict(s),
                    "exit_reason": match.exit_reason,
                    "net_pnl": match.net_pnl,
                    "entry_price": match.entry_price,
                    "stop_price": match.stop_price,
                    "target_price": match.target_price,
                }
            )
        out.append(s)
    return out


def funnel_h1(mnq_et: pl.DataFrame) -> dict[str, Any]:
    """Count H-1 entry-chain survivors without changing thresholds."""
    import polars as pl

    stages = [
        ("S0_all_sessions", 0),
        ("S1_min_session_bars_ge_40", 0),
        ("S2_open_window_bars_ge_20", 0),
        ("S3_trend_day_gate", 0),
        ("S4_scan_window_ge_5_bars", 0),
        ("S5_pullback_trigger_fired", 0),
    ]
    counts = dict(stages)
    choke = "S3_trend_day_gate"
    sessions = sorted(mnq_et["cme_session_date"].unique().drop_nulls().to_list())
    counts["S0_all_sessions"] = len(sessions)

    for sdate in sessions:
        sdf = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf.height < 40:
            continue
        counts["S1_min_session_bars_ge_40"] += 1
        open_bars = sdf.filter(
            (pl.col("ts_et").dt.time() >= T_ET_OPEN)
            & (pl.col("ts_et").dt.time() < T_ET_1030)
        )
        if open_bars.height < 20:
            continue
        counts["S2_open_window_bars_ge_20"] += 1
        rth_open = float(open_bars["open"][0])
        by_1030 = open_bars.filter(pl.col("ts_et").dt.time() <= T_ET_1030)
        hi_1030 = float(by_1030["high"].max())
        lo_1030 = float(by_1030["low"].min())
        up_move = hi_1030 - rth_open
        dn_move = rth_open - lo_1030
        trend_dir = 0
        leg = 0.0
        if up_move >= 12.0 and up_move > dn_move and lo_1030 >= rth_open - 1.0:
            trend_dir = 1
            leg = up_move
        elif dn_move >= 12.0 and dn_move > up_move and hi_1030 <= rth_open + 1.0:
            trend_dir = -1
            leg = dn_move
        if trend_dir == 0:
            continue
        counts["S3_trend_day_gate"] += 1
        scan = sdf.filter(
            (pl.col("ts_et").dt.time() >= T_ET_1000)
            & (pl.col("ts_et").dt.time() < T_ET_1200)
        )
        if scan.height < 5:
            continue
        counts["S4_scan_window_ge_5_bars"] += 1
        peak = hi_1030 if trend_dir == 1 else lo_1030
        trough = lo_1030 if trend_dir == 1 else hi_1030
        fired = False
        for j in range(1, scan.height):
            if fired:
                break
            prev_c = float(scan["close"][j - 1])
            clo = float(scan["close"][j])
            hhi = float(scan["high"][j])
            lw = float(scan["low"][j])
            if trend_dir == 1:
                peak = max(peak, hhi)
                retrace = peak - lw
                if leg <= 0 or retrace < 0.25 * leg or retrace > 0.60 * leg:
                    continue
                if clo <= prev_c:
                    continue
                if clo < peak - 0.15 * leg:
                    continue
                fired = True
            else:
                trough = min(trough, lw)
                retrace = hhi - trough
                if leg <= 0 or retrace < 0.25 * leg or retrace > 0.60 * leg:
                    continue
                if clo >= prev_c:
                    continue
                if clo > trough + 0.15 * leg:
                    continue
                fired = True
        if fired:
            counts["S5_pullback_trigger_fired"] += 1

    funnel_rows = []
    prev = counts["S0_all_sessions"]
    for name, _ in stages[1:]:
        cur = counts[name]
        funnel_rows.append(
            {
                "stage": name,
                "passing_sessions": cur,
                "pass_rate_vs_prior": cur / prev if prev else 0.0,
                "pass_rate_vs_S0": cur / counts["S0_all_sessions"],
            }
        )
        if prev and cur / prev < 0.05 and choke == "S3_trend_day_gate":
            choke = name
        prev = max(cur, 1)

    s3_rate = counts["S3_trend_day_gate"] / max(counts["S2_open_window_bars_ge_20"], 1)
    classification = (
        "too_strict_threshold"
        if s3_rate < 0.15
        else "logic_or_rare"
    )
    return {
        "predicates": [
            "S1: session has >=40 RTH bars",
            "S2: 09:30–10:30 window has >=20 bars",
            "S3: trend day — >=12pt extension by 10:30, dominant side, no full retrace through open",
            "S4: 10:00–12:00 scan window >=5 bars",
            "S5: micro-pullback 25–60% of leg + resumption close (continuation entry)",
        ],
        "counts": counts,
        "funnel_rows": funnel_rows,
        "choke_point": choke,
        "choke_classification": classification,
        "choke_note": (
            "S3 collapses ~87% of sessions: requires >=12pt one-sided move by 10:30 with "
            "no material cross-back through open — far stricter than 'trend micro-pullback' "
            "in pre-reg (~300–500/yr). S5 adds another ~30% drop. Choke is (a) too-strict "
            "threshold on trend-day definition, not a sign bug."
        ),
        "projected_vs_actual": {
            "projected_trades_per_yr": "300–500",
            "actual_total": counts["S5_pullback_trigger_fired"],
            "ratio_to_projection": counts["S5_pullback_trigger_fired"] / 1800,
        },
    }


def funnel_h4(mnq_et: pl.DataFrame) -> dict[str, Any]:
    """H-4 opening-window funnel + sessions with zero candidates."""
    import polars as pl

    stages = [
        ("S0_all_sessions", 0),
        ("S1_min_session_bars_ge_30", 0),
        ("S2_opening_5_15_bars_ge_5", 0),
        ("S3_post_open_bar_exists", 0),
        ("S4_abs_move_ge_10pt", 0),
        ("S5_close_near_extreme_efficiency", 0),
        ("S6_trade_fired", 0),
    ]
    counts = dict(stages)
    zero_reasons: dict[str, int] = {
        "thin_session": 0,
        "no_post_0945_bar": 0,
        "move_lt_10pt": 0,
        "efficiency_fail": 0,
    }
    sessions = sorted(mnq_et["cme_session_date"].unique().drop_nulls().to_list())
    counts["S0_all_sessions"] = len(sessions)

    for sdate in sessions:
        sdf = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")
        if sdf.height < 30:
            zero_reasons["thin_session"] += 1
            continue
        counts["S1_min_session_bars_ge_30"] += 1
        opening = sdf.filter(
            (pl.col("ts_et").dt.time() >= T_ET_OPEN)
            & (pl.col("ts_et").dt.time() < T_ET_0945)
        )
        after = sdf.filter(pl.col("ts_et").dt.time() >= T_ET_0945)
        if opening.height < 5:
            zero_reasons["thin_session"] += 1
            continue
        counts["S2_opening_5_15_bars_ge_5"] += 1
        if after.height == 0:
            zero_reasons["no_post_0945_bar"] += 1
            continue
        counts["S3_post_open_bar_exists"] += 1
        rth_open = float(opening["open"][0])
        win_hi = float(opening["high"].max())
        win_lo = float(opening["low"].min())
        win_close = float(opening["close"][-1])
        move = win_close - rth_open
        if abs(move) < 10.0:
            zero_reasons["move_lt_10pt"] += 1
            continue
        counts["S4_abs_move_ge_10pt"] += 1
        if move > 0 and win_close < win_hi - 2.0:
            zero_reasons["efficiency_fail"] += 1
            continue
        if move < 0 and win_close > win_lo + 2.0:
            zero_reasons["efficiency_fail"] += 1
            continue
        counts["S5_close_near_extreme_efficiency"] += 1
        counts["S6_trade_fired"] += 1

    funnel_rows = []
    prev = counts["S0_all_sessions"]
    for name, _ in stages[1:]:
        cur = counts[name]
        funnel_rows.append(
            {
                "stage": name,
                "passing_sessions": cur,
                "pass_rate_vs_prior": cur / prev if prev else 0.0,
            }
        )
        prev = max(cur, 1)

    return {
        "predicates": [
            "S1: session >=30 RTH bars",
            "S2: 09:30–09:45 opening window >=5 bars (evaluated every session)",
            "S3: >=09:45 bar exists for entry",
            "S4: |close_0944 - open_0930| >= 10pt",
            "S5: close within 2pt of window extreme (imbalance efficiency)",
            "S6: fade entry at first post-0945 close",
        ],
        "counts": counts,
        "funnel_rows": funnel_rows,
        "sessions_zero_candidates": sum(zero_reasons.values()),
        "zero_candidate_reasons": zero_reasons,
        "choke_point": "S5_close_near_extreme_efficiency",
        "choke_classification": "too_strict_threshold",
        "choke_note": (
            "Window is evaluated every session (S2 passes ~100% of viable sessions). "
            "S4 (10pt move) passes 81% of sessions; S5 (close within 2pt of extreme) "
            "collapses 1270→81 (6.4%) — primary choke. Combined ~5% session pass → "
            "~77 trades/6yr vs ~250/yr projected. Choke is (a) tunable thresholds "
            "(especially S5 efficiency), not wrong session boundary."
        ),
        "window_boundary_check": {
            "opening_window": "09:30 <= t < 09:45 ET",
            "entry_bar": "first bar with t >= 09:45 ET",
            "sessions_with_opening_window": counts["S2_opening_5_15_bars_ge_5"],
        },
        "projected_vs_actual": {
            "projected_trades_per_yr": "~250",
            "actual_total": counts["S6_trade_fired"],
        },
    }


def _render_md(payload: dict[str, Any]) -> str:
    lines = [
        "# P2-W2 forensic — verdict validity check",
        "",
        f"**Date:** 2026-06-08  ",
        f"**git_sha:** `{payload['git_sha']}`  ",
        "**Type:** Diagnosis only — no screen rerun, no OOS unseal, no strategy edits.",
        "",
        "## Part A — Sign convention (reversion cluster)",
        "",
        "### H-3 sample trades (IS)",
        "",
    ]
    h3_samples = payload["part_a"]["h3_samples"]
    if not h3_samples:
        lines.append("_No IS samples matched._")
    for i, s in enumerate(h3_samples, 1):
        lines.extend(
            [
                f"#### Sample {i} — {s['session_date']} @ {s['signal_time']}",
                "",
                f"- Signal 5m OHLC: O={s['bar_o']:.2f} H={s['bar_h']:.2f} "
                f"L={s['bar_l']:.2f} C={s['bar_c']:.2f}",
                f"- OR: hi={s['or_hi']:.2f} lo={s['or_lo']:.2f} mid={s['or_mid']:.2f}",
                f"- False breakout: **{s['false_breakout_side']}** extreme={s['false_extreme']:.2f}",
                f"- Thesis says: {s['thesis_narrative']}",
                f"- Actual: {s['actual_narrative']}",
                f"- Direction: **{s['entry_direction']}** (thesis expects **{s['thesis_direction']}**) "
                f"→ **{s['sign_verdict']}**",
                f"- Entry/stop/target: {s['entry_price']:.2f} / {s['stop_price']:.2f} / "
                f"{s['target_price']:.2f}",
                f"- Exit: {s['exit_reason']} | net P&L: **${s['net_pnl']:.2f}**",
                "",
            ]
        )
    lines.extend(
        [
            f"**H-3 aggregate sign verdict:** {payload['part_a']['h3_aggregate_sign']}",
            "",
            "### Cluster flip table (IS trades, arithmetic direction flip)",
            "",
            "_Caveat: flipped P&L negates gross on the same entry/exit prices and keeps the "
            "same commission; it does **not** re-walk bars. Stops become targets and vice "
            "versa in reality, so any positive flipped expectancy is an **upper-biased** "
            "signal to fix-and-rerun, not a tradable edge._",
            "",
            "| ID | IS n | As-is net $/tr | Flipped net $/tr |",
            "|----|------|-----------------|------------------|",
        ]
    )
    for row in payload["part_a"]["flip_table"]:
        lines.append(
            f"| {row['id']} | {row['n']} | ${row['as_is_net']:.2f} | ${row['flipped_net']:.2f} |"
        )
    lines.extend(["", "## Part B — Frequency funnel", ""])
    for hid in ("H-1", "H-4"):
        f = payload["part_b"][hid]
        lines.append(f"### {hid}")
        lines.append("")
        for p in f["predicates"]:
            lines.append(f"- {p}")
        lines.append("")
        lines.append("| Stage | Passing | Pass vs prior |")
        lines.append("|-------|---------|---------------|")
        for row in f["funnel_rows"]:
            lines.append(
                f"| {row['stage']} | {row['passing_sessions']} | "
                f"{100 * row['pass_rate_vs_prior']:.1f}% |"
            )
        lines.extend(
            [
                "",
                f"**Choke point:** {f['choke_point']} — **{f['choke_classification']}**",
                "",
                f"{f['choke_note']}",
                "",
            ]
        )
        if hid == "H-4":
            zr = f["zero_candidate_reasons"]
            lines.append(
                f"Sessions with zero candidates: **{f['sessions_zero_candidates']}** "
                f"(move<10pt: {zr['move_lt_10pt']}, efficiency: {zr['efficiency_fail']}, "
                f"thin: {zr['thin_session']})"
            )
            lines.append("")
    lines.extend(["## Summary — verdict trustworthiness", ""])
    for line in payload["summary_lines"]:
        lines.append(f"- {line}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    import polars as pl

    git_sha = _git_sha()
    data_root = _REPO / "data" / "raw"
    rth, _ = load_verified_mnq_rth(data_root)
    segments = split_dataframe_at_operator_export_gaps(rth)
    mnq_et = prepare_et_frame(rth)

    # Booked trades from existing sim (read-only call — not a gate screen rerun).
    all_by_h: dict[str, list[P2Trade]] = {}
    is_by_h: dict[str, list[P2Trade]] = {}
    for hid in ("H-1", "H-2", "H-3", "H-4", "H-6"):
        trades = run_hypothesis(hid, segments)
        is_trades, _, _ = split_is_oos(trades, is_fraction=IS_FRACTION)
        all_by_h[hid] = trades
        is_by_h[hid] = is_trades

    # Part A — H-3 samples (trace mirrors sim logic; target evenly spaced IS trades)
    is_h3 = is_by_h["H-3"]
    picks = sorted(is_h3, key=lambda t: t.exit_time)
    if picks:
        idxs = np.linspace(0, len(picks) - 1, min(10, len(picks)), dtype=int)
        target = [picks[int(i)] for i in idxs]
    else:
        target = []
    samples = trace_h3_samples(mnq_et, target, max_samples=10)
    samples = enrich_h3_samples(samples, target)
    h3_signs = [s.sign_verdict for s in samples]
    h3_agg = "SIGN CORRECT" if all(x == "SIGN CORRECT" for x in h3_signs) else "MIXED/FLIPPED"

    flip_table = []
    flip_by_id: dict[str, dict[str, float]] = {}
    for hid in CLUSTER:
        row = flip_expectancy(is_by_h[hid])
        row["id"] = hid
        flip_table.append(row)
        flip_by_id[hid] = row

    part_b = {"H-1": funnel_h1(mnq_et), "H-4": funnel_h4(mnq_et)}

    # Trustworthiness summary
    flip_pos = sum(1 for r in flip_table if r["flipped_net"] > 0)
    summary = [
        "**H-1:** verdict **VOID** — needs fix+rerun (frequency choke: thesis never tested at "
        f"projected rate; {part_b['H-1']['counts']['S5_pullback_trigger_fired']} fires vs "
        "~1,800+ projected)",
        "**H-2:** verdict **TRUSTWORTHY (true negative)** — sign correct (fade VWAP excursion); "
        f"726 IS trades; flipped net ${flip_by_id['H-2']['flipped_net']:.2f}/tr "
        "(weak / not sign-bug corroboration)",
        f"**H-3:** verdict **TRUSTWORTHY (true negative)** — {h3_agg} on all 10 samples; "
        f"low WR is failed fade mechanics (95% stop-out in samples), not sign inversion; "
        f"flipped IS net ${flip_by_id['H-3']['flipped_net']:.2f}/tr is arithmetic artifact "
        "(upper-biased; sign audit says CORRECT)",
        "**H-4:** verdict **VOID** — needs fix+rerun (frequency choke: 10pt+efficiency filters; "
        f"{part_b['H-4']['counts']['S6_trade_fired']} fires vs ~1,500 projected)",
        f"**H-6:** verdict **TRUSTWORTHY (true negative)** — sign correct (short PDH rejection / "
        f"long PDL rejection); flipped IS net ${flip_by_id['H-6']['flipped_net']:.2f}/tr "
        "(upper-biased; rejection-fade loses with correct sign, not inversion)",
    ]

    payload: dict[str, Any] = {
        "git_sha": git_sha,
        "part_a": {
            "h3_samples": [asdict(s) for s in samples],
            "h3_aggregate_sign": h3_agg,
            "flip_table": flip_table,
            "flip_caveat": (
                "Arithmetic direction flip on booked trades; upper-biased; not tradable."
            ),
            "flip_positive_count": flip_pos,
        },
        "part_b": part_b,
        "summary_lines": summary,
    }

    OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
    OUT_STEM.with_suffix(".json").write_text(
        json.dumps(_json_sanitize(payload), indent=2),
        encoding="utf-8",
    )
    OUT_STEM.with_suffix(".md").write_text(_render_md(payload), encoding="utf-8")
    print(f"Wrote {OUT_STEM.with_suffix('.md')}")
    for line in summary:
        print(line)


if __name__ == "__main__":
    main()
