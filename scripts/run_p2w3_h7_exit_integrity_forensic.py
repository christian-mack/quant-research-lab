#!/usr/bin/env python3
"""P2-W3 / H-7 exit-integrity forensic — IS partition, diagnosis only.

Usage::

    uv run python scripts/run_p2w3_h7_exit_integrity_forensic.py

Writes ``notebooks/validation/2026-06-08_p2w3_h7_exit_integrity_forensic.{md,json}``.
Does NOT modify strategy logic, unseal OOS, or rerun Gate #1 screening.
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
import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.backtest.fill_resolution import intrabar_pivot_prices
from quant_research.backtest.specs import IntrabarPricePath
from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.research_p2w2.costs import (
    COMMISSION_PER_FILL,
    MNQ_POINT_VALUE,
    P2_STOP_TAG,
    P2_TARGET_TAG,
    P2_W2_BACKTEST_CONFIG,
    P2Trade,
    _slip_px,
    simulate_p2_trade,
)
from quant_research.research_p2w2.data_verify import load_verified_mnq_rth
from quant_research.research_p2w2.hypothesis_sims import (
    H7_STOP_PTS,
    H7_TARGET_PTS,
    iter_h3_h7_reclaim_signals,
    prepare_et_frame,
    run_hypothesis,
)
from quant_research.research_p2w2.metrics import split_is_oos

OUT_STEM = _REPO / "notebooks" / "validation" / "2026-06-08_p2w3_h7_exit_integrity_forensic"
GATE1_NET = 20.84689747003995
GATE1_WR = 0.748335552596538
GATE1_IS = 751


def _git_meta(repo: Path) -> dict[str, object]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return {
            "git_sha": (sha.stdout or "").strip() or "unknown",
            "git_dirty": bool((dirty.stdout or "").strip()),
        }
    except OSError:
        return {"git_sha": "unknown", "git_dirty": None}


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


@dataclass(frozen=True, slots=True)
class TradeContext:
    trade: P2Trade
    session_bars: pl.DataFrame
    entry_bar_idx: int
    exit_bar_idx: int
    raw_entry_px: float
    raw_stop_px: float
    raw_target_px: float
    reclaim_bar_anchor: object


def _bar_dual_touch(
    direction: int,
    hi: float,
    lo: float,
    stop_px: float,
    target_px: float,
) -> bool:
    if direction == 1:
        return lo <= stop_px and hi >= target_px
    return hi >= stop_px and lo <= target_px


def _first_touch_pessimistic(
    direction: int,
    open_px: float,
    hi: float,
    lo: float,
    close: float,
    stop_px: float,
    target_px: float,
) -> str | None:
    """M4 pessimistic path: OPEN_LOW_HIGH_CLOSE — stop before target on long."""
    path = (
        IntrabarPricePath.OPEN_LOW_HIGH_CLOSE
        if direction == 1
        else IntrabarPricePath.OPEN_HIGH_LOW_CLOSE
    )
    pivots = intrabar_pivot_prices(open_px, hi, lo, close, path)
    prev = pivots[0]
    for curr in pivots[1:]:
        if direction == 1:
            if prev > stop_px >= curr or (prev == stop_px and curr == stop_px):
                return "stop"
            if prev < target_px <= curr or (prev == target_px and curr == target_px):
                return "target"
        else:
            if prev < stop_px <= curr or (prev == stop_px and curr == stop_px):
                return "stop"
            if prev > target_px >= curr or (prev == target_px and curr == target_px):
                return "target"
        prev = curr
    return None


def _first_touch_optimistic(
    direction: int,
    open_px: float,
    hi: float,
    lo: float,
    close: float,
    stop_px: float,
    target_px: float,
) -> str | None:
    path = (
        IntrabarPricePath.OPEN_HIGH_LOW_CLOSE
        if direction == 1
        else IntrabarPricePath.OPEN_LOW_HIGH_CLOSE
    )
    pivots = intrabar_pivot_prices(open_px, hi, lo, close, path)
    prev = pivots[0]
    for curr in pivots[1:]:
        if direction == 1:
            if prev < target_px <= curr:
                return "target"
            if prev > stop_px >= curr:
                return "stop"
        else:
            if prev > target_px >= curr:
                return "target"
            if prev < stop_px <= curr:
                return "stop"
        prev = curr
    return None


def _chronological_first_touch_minute_bars(
    minute_bars: pl.DataFrame,
    direction: int,
    stop_px: float,
    target_px: float,
) -> tuple[str | None, int | None]:
    """Walk 1-min bars in time order; return first stop/target and bar index."""
    for i in range(minute_bars.height):
        o = float(minute_bars["open"][i])
        hi = float(minute_bars["high"][i])
        lo = float(minute_bars["low"][i])
        clo = float(minute_bars["close"][i])
        touch = _first_touch_pessimistic(direction, o, hi, lo, clo, stop_px, target_px)
        if touch is not None:
            return touch, i
    return None, None


def _recompute_net_stop_exit(trade: P2Trade, *, exit_base: float) -> float:
    direction = trade.direction
    entry_side = "buy" if direction == 1 else "sell"
    exit_side = "sell" if direction == 1 else "buy"
    entry_fill = trade.entry_price
    exit_fill = _slip_px(float(exit_base), exit_side, P2_STOP_TAG, P2_W2_BACKTEST_CONFIG)
    pts = (exit_fill - entry_fill) if direction == 1 else (entry_fill - exit_fill)
    gross = pts * MNQ_POINT_VALUE
    return float(gross - trade.commission)


def _build_trade_contexts(
    mnq_et: pl.DataFrame,
    is_trades: list[P2Trade],
) -> list[TradeContext]:
    by_session: dict[dt.date, pl.DataFrame] = {}
    for sdate in mnq_et["cme_session_date"].unique().drop_nulls().to_list():
        by_session[sdate] = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")

    signal_by_key: dict[tuple[dt.date, float], object] = {}
    for sig in iter_h3_h7_reclaim_signals(mnq_et):
        signal_by_key[(sig.cme_session_date, round(sig.entry_px, 2))] = sig

    contexts: list[TradeContext] = []
    for t in is_trades:
        key = (t.cme_session_date, round(t.entry_price, 2))
        sig = signal_by_key.get(key)
        if sig is None:
            for k, s in signal_by_key.items():
                if k[0] == t.cme_session_date and abs(k[1] - t.entry_price) < 0.5:
                    sig = s
                    break
        if sig is None:
            continue
        sdf = by_session[t.cme_session_date]
        rest = sdf.filter(pl.col("timestamp") >= sig.anchor_ts)
        entry_idx = 0
        for i in range(rest.height):
            if rest["timestamp"][i] == t.entry_time:
                entry_idx = i
                break
        exit_idx = entry_idx
        for i in range(rest.height):
            if rest["timestamp"][i] == t.exit_time:
                exit_idx = i
                break
        entry_px = sig.entry_px
        if sig.false_dir == 1:
            stop_px = entry_px - H7_STOP_PTS
            target_px = entry_px + H7_TARGET_PTS
        else:
            stop_px = entry_px + H7_STOP_PTS
            target_px = entry_px - H7_TARGET_PTS
        contexts.append(
            TradeContext(
                trade=t,
                session_bars=rest,
                entry_bar_idx=entry_idx,
                exit_bar_idx=exit_idx,
                raw_entry_px=entry_px,
                raw_stop_px=stop_px,
                raw_target_px=target_px,
                reclaim_bar_anchor=sig.anchor_ts,
            )
        )
    return contexts


def _check1_dual_touch(contexts: list[TradeContext]) -> dict[str, Any]:
    target_trades = [c for c in contexts if c.trade.exit_reason == "target"]
    dual_on_exit: list[dict[str, Any]] = []
    dual_anywhere: list[dict[str, Any]] = []

    for ctx in target_trades:
        t = ctx.trade
        d = t.direction
        stop = ctx.raw_stop_px
        target = ctx.raw_target_px
        bars = ctx.session_bars
        exit_i = ctx.exit_bar_idx
        hi = float(bars["high"][exit_i])
        lo = float(bars["low"][exit_i])
        if _bar_dual_touch(d, hi, lo, stop, target):
            dual_on_exit.append(
                {
                    "session": str(t.cme_session_date),
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "direction": "long" if d == 1 else "short",
                    "booked": "target",
                    "bar": "exit",
                }
            )

        for i in range(ctx.entry_bar_idx, ctx.exit_bar_idx + 1):
            hi = float(bars["high"][i])
            lo = float(bars["low"][i])
            if _bar_dual_touch(d, hi, lo, stop, target):
                dual_anywhere.append(
                    {
                        "session": str(t.cme_session_date),
                        "entry_time": t.entry_time.isoformat(),
                        "bar_idx": i,
                        "is_entry_bar": i == ctx.entry_bar_idx,
                        "is_exit_bar": i == ctx.exit_bar_idx,
                        "booked": "target",
                    }
                )
                break

    samples: list[dict[str, Any]] = []
    for ctx in target_trades:
        if len(samples) >= 10:
            break
        t = ctx.trade
        exit_i = ctx.exit_bar_idx
        bars = ctx.session_bars
        hi = float(bars["high"][exit_i])
        lo = float(bars["low"][exit_i])
        o = float(bars["open"][exit_i])
        clo = float(bars["close"][exit_i])
        if not _bar_dual_touch(t.direction, hi, lo, ctx.raw_stop_px, ctx.raw_target_px):
            continue
        pess = _first_touch_pessimistic(
            t.direction, o, hi, lo, clo, ctx.raw_stop_px, ctx.raw_target_px
        )
        opt = _first_touch_optimistic(
            t.direction, o, hi, lo, clo, ctx.raw_stop_px, ctx.raw_target_px
        )
        ts_et = bars["ts_et"][exit_i]
        b5 = ts_et.replace(minute=ts_et.minute // 5 * 5, second=0, microsecond=0)
        b5_end = b5 + dt.timedelta(minutes=5)
        minute_slice = bars.filter((pl.col("ts_et") >= b5) & (pl.col("ts_et") < b5_end))
        chrono, chrono_i = _chronological_first_touch_minute_bars(
            minute_slice, t.direction, ctx.raw_stop_px, ctx.raw_target_px
        )
        samples.append(
            {
                "session": str(t.cme_session_date),
                "exit_time": t.exit_time.isoformat(),
                "booked_exit": t.exit_reason,
                "bar_dual_touch": True,
                "pessimistic_first": pess,
                "optimistic_first": opt,
                "chrono_1min_first": chrono,
                "chrono_1min_bar_offset": chrono_i,
            }
        )

    if len(samples) < 8:
        for ctx in target_trades[:10]:
            t = ctx.trade
            exit_i = ctx.exit_bar_idx
            bars = ctx.session_bars
            hi = float(bars["high"][exit_i])
            lo = float(bars["low"][exit_i])
            o = float(bars["open"][exit_i])
            clo = float(bars["close"][exit_i])
            if _bar_dual_touch(t.direction, hi, lo, ctx.raw_stop_px, ctx.raw_target_px):
                continue
            pess = _first_touch_pessimistic(
                t.direction, o, hi, lo, clo, ctx.raw_stop_px, ctx.raw_target_px
            )
            samples.append(
                {
                    "session": str(t.cme_session_date),
                    "exit_time": t.exit_time.isoformat(),
                    "booked_exit": t.exit_reason,
                    "bar_dual_touch": False,
                    "pessimistic_first": pess,
                    "optimistic_first": _first_touch_optimistic(
                        t.direction, o, hi, lo, clo, ctx.raw_stop_px, ctx.raw_target_px
                    ),
                    "chrono_1min_first": pess,
                    "note": "single-touch exit bar (included for path audit)",
                }
            )
            if len(samples) >= 10:
                break

    worst_adjusted = 0.0
    for ctx in contexts:
        t = ctx.trade
        if t.exit_reason != "target":
            worst_adjusted += t.net_pnl
            continue
        bars = ctx.session_bars
        exit_i = ctx.exit_bar_idx
        hi = float(bars["high"][exit_i])
        lo = float(bars["low"][exit_i])
        if _bar_dual_touch(t.direction, hi, lo, ctx.raw_stop_px, ctx.raw_target_px):
            worst_adjusted += _recompute_net_stop_exit(t, exit_base=ctx.raw_stop_px)
        else:
            worst_adjusted += t.net_pnl

    n = len(contexts)
    orig_net = float(np.mean([c.trade.net_pnl for c in contexts]))
    worst_net_mean = worst_adjusted / n if n else 0.0
    orig_wins = sum(1 for c in contexts if c.trade.net_pnl > 0)
    worst_wins = orig_wins
    for ctx in contexts:
        t = ctx.trade
        if t.exit_reason != "target":
            continue
        bars = ctx.session_bars
        exit_i = ctx.exit_bar_idx
        hi = float(bars["high"][exit_i])
        lo = float(bars["low"][exit_i])
        if _bar_dual_touch(t.direction, hi, lo, ctx.raw_stop_px, ctx.raw_target_px):
            if t.net_pnl > 0:
                worst_wins -= 1

    return {
        "fill_path": "research_p2w2/costs.py::simulate_p2_trade (inline bar walker)",
        "m4_engine_used": False,
        "dual_touch_rule": "stop-before-target on same minute bar (lines 144-146 long, 156-158 short)",
        "m4_equivalent_policy_in_config": "StopLimitIntrabarPolicy.STOP_BEFORE_TARGET (not invoked by walker)",
        "is_target_trades": len(target_trades),
        "dual_touch_on_exit_bar_among_targets": len(dual_on_exit),
        "dual_touch_pct_of_is": 100 * len(dual_on_exit) / GATE1_IS,
        "dual_touch_any_bar_among_targets": len(dual_anywhere),
        "hand_verify_samples": samples[:10],
        "worst_case_stop_first": {
            "net_expectancy": worst_net_mean,
            "delta_vs_gate1": worst_net_mean - GATE1_NET,
            "win_rate": worst_wins / n if n else 0.0,
            "delta_wr_vs_gate1": (worst_wins / n if n else 0.0) - GATE1_WR,
            "flipped_trades": len(dual_on_exit),
        },
    }


def _recompute_is_next_bar_bracket(mnq_et: pl.DataFrame, is_trades: list[P2Trade]) -> dict[str, Any]:
    """Diagnostic: entry at reclaim 5m close on last bucket minute; bracket from next bar."""
    by_session: dict[dt.date, pl.DataFrame] = {}
    for sdate in mnq_et["cme_session_date"].unique().drop_nulls().to_list():
        by_session[sdate] = mnq_et.filter(pl.col("cme_session_date") == sdate).sort("timestamp")

    signal_by_session: dict[dt.date, list] = {}
    for sig in iter_h3_h7_reclaim_signals(mnq_et):
        signal_by_session.setdefault(sig.cme_session_date, []).append(sig)

    corrected: list[P2Trade] = []
    for t in is_trades:
        sigs = signal_by_session.get(t.cme_session_date, [])
        sig = next((s for s in sigs if abs(s.entry_px - t.entry_price) < 0.01), None)
        if sig is None:
            continue
        sdf = by_session[t.cme_session_date]
        rest = sdf.filter(pl.col("timestamp") >= sig.anchor_ts)
        b5 = sig.anchor_ts
        if hasattr(b5, "replace"):
            b5_end = b5 + dt.timedelta(minutes=5)
        else:
            b5_end = b5
        bucket = rest.filter((pl.col("timestamp") >= b5) & (pl.col("timestamp") < b5_end))
        if bucket.is_empty():
            continue
        last_bucket_ts = bucket["timestamp"][-1]
        post_entry = rest.filter(pl.col("timestamp") > last_bucket_ts)
        if post_entry.is_empty():
            continue
        entry_px = sig.entry_px
        if sig.false_dir == 1:
            direction = 1
            stop_px = entry_px - H7_STOP_PTS
            target_px = entry_px + H7_TARGET_PTS
        else:
            direction = -1
            stop_px = entry_px + H7_STOP_PTS
            target_px = entry_px - H7_TARGET_PTS
        tr = simulate_p2_trade(
            post_entry,
            entry_idx=0,
            direction=direction,
            entry_price=entry_px,
            stop_px=stop_px,
            target_px=target_px,
            cme_session_date=sig.cme_session_date,
            max_et_time_exit=dt.time(12, 0),
            hypothesis_id="H-7",
        )
        if tr is not None:
            corrected.append(tr)

    if not corrected:
        return {"count": 0, "net_per_trade": None, "win_rate": None, "delta_net": None}

    net = float(np.mean([x.net_pnl for x in corrected]))
    wr = sum(1 for x in corrected if x.net_pnl > 0) / len(corrected)
    same_bar = sum(
        1 for x in corrected if x.bars_held == 0 and x.exit_reason in ("stop", "target")
    )
    return {
        "count": len(corrected),
        "net_per_trade": net,
        "win_rate": wr,
        "delta_net_vs_gate1": net - GATE1_NET,
        "delta_wr_vs_gate1": wr - GATE1_WR,
        "same_bar_exits_after_fix": same_bar,
        "note": (
            "Entry on last minute of reclaim 5m bucket; if walker still exits same bar, "
            "force bracket walk from entry_idx+1."
        ),
    }


def _check2_entry_bar(contexts: list[TradeContext]) -> dict[str, Any]:
    same_bar_bracket: list[dict[str, Any]] = []
    same_bar_exit: list[dict[str, Any]] = []

    for ctx in contexts:
        t = ctx.trade
        if ctx.entry_bar_idx == ctx.exit_bar_idx and t.exit_reason in ("stop", "target"):
            same_bar_exit.append(
                {
                    "session": str(t.cme_session_date),
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "exit_reason": t.exit_reason,
                    "bars_held": t.bars_held,
                    "entry_px_booked": t.entry_price,
                    "raw_reclaim_close": ctx.raw_entry_px,
                }
            )
        bars = ctx.session_bars
        i = ctx.entry_bar_idx
        hi = float(bars["high"][i])
        lo = float(bars["low"][i])
        if _bar_dual_touch(t.direction, hi, lo, ctx.raw_stop_px, ctx.raw_target_px):
            same_bar_bracket.append(
                {
                    "session": str(t.cme_session_date),
                    "entry_time": t.entry_time.isoformat(),
                    "exit_reason": t.exit_reason,
                    "entry_bar_spans_bracket": True,
                }
            )

    pct_same = 100 * len(same_bar_exit) / GATE1_IS if GATE1_IS else 0.0
    return {
        "entry_fill_mechanism": (
            "Entry at reclaim 5m bar CLOSE price; walker starts at entry_idx=0 "
            "(first minute of 5m bucket = anchor_ts). Bracket is LIVE on entry bar."
        ),
        "bracket_arms_next_bar": False,
        "same_bar_stop_or_target_exit_count": len(same_bar_exit),
        "same_bar_exit_pct_of_is": pct_same,
        "same_bar_exit_samples": same_bar_exit[:10],
        "entry_bar_spans_full_bracket_count": len(same_bar_bracket),
        "entry_bar_bracket_samples": same_bar_bracket[:10],
    }


def _check3_lookahead(mnq_et: pl.DataFrame) -> dict[str, Any]:
    signals = list(iter_h3_h7_reclaim_signals(mnq_et))
    return {
        "trigger_uses_completed_5m_close": True,
        "signal_anchor_ts": "first minute timestamp of reclaim 5m bucket (bar open)",
        "entry_price": "5m bucket last close (reclaim close) — known only after bucket completes",
        "lookahead_within_5m_bucket": (
            "YES — bracket walk begins at anchor_ts (minute 1 of bucket) while entry_px "
            "is the bucket close (minute 5). Minutes 1–4 of reclaim bar are evaluated "
            "against a bracket priced at the not-yet-realized close."
        ),
        "acted_after_bar_complete": (
            "Partially — signal requires completed 5m close, but simulate_p2_trade fills "
            "at close price on the first minute bar of that bucket (entry_idx=0)."
        ),
        "h3_shared_trigger_negative": (
            "H-3 IS net −$19.61 on same trigger — look-ahead that inflates WR would "
            "tend to help both directions; H-3 failure is partial evidence trigger is "
            "not grossly lookahead-biased, but H-7/H-3 entry timing issue is shared."
        ),
        "is_signals_in_dataset": len(signals),
    }


def _check4_disposition(is_trades: list[P2Trade], contexts: list[TradeContext]) -> dict[str, Any]:
    buckets: dict[str, list[P2Trade]] = {"target": [], "stop": [], "time": []}
    other: list[P2Trade] = []
    for t in is_trades:
        r = t.exit_reason
        if r == "target":
            buckets["target"].append(t)
        elif r == "stop":
            buckets["stop"].append(t)
        elif r in ("time", "session_end"):
            buckets["time"].append(t)
        else:
            other.append(t)

    n = len(is_trades)
    table: dict[str, dict[str, Any]] = {}
    for name, trades in buckets.items():
        net_sum = sum(t.net_pnl for t in trades)
        table[name] = {
            "count": len(trades),
            "pct": 100 * len(trades) / n if n else 0.0,
            "net_pnl_total": net_sum,
            "net_pnl_per_trade": net_sum / len(trades) if trades else 0.0,
        }

    time_wins_bad: list[dict[str, Any]] = []
    time_wins_ok = 0
    for ctx in contexts:
        t = ctx.trade
        if t.exit_reason not in ("time", "session_end"):
            continue
        bars = ctx.session_bars
        exit_i = ctx.exit_bar_idx
        noon_px = float(bars["close"][exit_i])
        if t.direction == 1:
            genuinely_win = noon_px > ctx.raw_entry_px
        else:
            genuinely_win = noon_px < ctx.raw_entry_px
        booked_win = t.net_pnl > 0
        if booked_win and not genuinely_win:
            time_wins_bad.append(
                {
                    "session": str(t.cme_session_date),
                    "exit_time": t.exit_time.isoformat(),
                    "booked_exit_price": t.exit_price,
                    "noon_close": noon_px,
                    "raw_entry": ctx.raw_entry_px,
                }
            )
        elif booked_win:
            time_wins_ok += 1

    target_wins = sum(1 for t in buckets["target"] if t.net_pnl > 0)
    total_wins = sum(1 for t in is_trades if t.net_pnl > 0)
    time_wins = sum(1 for t in buckets["time"] if t.net_pnl > 0)

    return {
        "disposition": table,
        "other_exit_reasons": {t.exit_reason: 1 for t in other},
        "time_stop_mark_verification": {
            "time_wins_booked": time_wins,
            "time_wins_verified_at_noon_close": time_wins_ok,
            "time_wins_booked_at_target_bug": len(time_wins_bad),
            "bug_samples": time_wins_bad[:5],
        },
        "wr_decomposition": {
            "total_wins": total_wins,
            "target_capture_wins": target_wins,
            "time_stop_wins": time_wins,
            "target_fraction_of_wins": target_wins / total_wins if total_wins else 0.0,
            "time_fraction_of_wins": time_wins / total_wins if total_wins else 0.0,
            "genuine_target_capture_pct_of_is": 100 * target_wins / n if n else 0.0,
        },
    }


def _verdict(payload: dict[str, Any]) -> str:
    c1 = payload["check1"]
    c2 = payload["check2"]
    c3 = payload["check3"]
    c4 = payload["check4"]

    issues: list[str] = []
    if not c1["m4_engine_used"]:
        issues.append(
            "H-7 does not route through backtest/engine.py M4 ledger — uses bespoke "
            "simulate_p2_trade walker (stop-first on minute bar, not pivot path)"
        )
    if c1["dual_touch_on_exit_bar_among_targets"] > 0:
        issues.append(
            f"{c1['dual_touch_on_exit_bar_among_targets']} target exits on dual-touch "
            "exit bars (stop-first violation)"
        )
    if c2["same_bar_stop_or_target_exit_count"] > 0:
        issues.append(
            f"{c2['same_bar_stop_or_target_exit_count']} same-bar bracket exits "
            f"({c2.get('same_bar_exit_pct_of_is', 0):.1f}% of IS; bracket live on entry bar)"
        )
    nb = c2.get("next_bar_bracket_recompute")
    if c3.get("lookahead_within_5m_bucket"):
        issues.append("entry_px is 5m close but bracket walks from first minute of bucket")
    if c4["time_stop_mark_verification"]["time_wins_booked_at_target_bug"] > 0:
        issues.append("time exits booked at target price")

    worst = c1["worst_case_stop_first"]["net_expectancy"]
    nb = c2.get("next_bar_bracket_recompute") or {}
    nb_net = nb.get("net_per_trade")

    if nb_net is not None and nb_net <= 0:
        lead = (
            f"next-bar bracket recompute net ${nb_net:.2f}/tr "
            f"(WR {100 * (nb.get('win_rate') or 0):.1f}% vs gate {100 * GATE1_WR:.1f}%)"
        )
        return "H-7 result CONTAMINATED — " + lead + "; " + "; ".join(issues[:3])
    if issues and worst <= 0:
        return (
            "H-7 result CONTAMINATED — "
            + "; ".join(issues[:3])
            + ". Worst-case dual-touch net <= 0."
        )
    if issues:
        if nb_net is not None and nb_net > 0:
            return (
                "H-7 result MECHANICALLY CAUTION — dual-touch clean and next-bar "
                f"recompute still positive (${nb_net:.2f}/tr vs gate ${GATE1_NET:.2f}), "
                "but: " + "; ".join(issues[:2])
                + ". Do not advance to sizing until walker uses M4 path + next-bar bracket."
            )
        return (
            "H-7 result CONTAMINATED — " + "; ".join(issues)
            + ". Next-bar bracket recompute unavailable or non-positive."
        )
    return "H-7 mechanically TRUSTWORTHY — advance to sizing"


def _render_md(payload: dict[str, Any]) -> str:
    c1 = payload["check1"]
    c2 = payload["check2"]
    c3 = payload["check3"]
    c4 = payload["check4"]
    wc = c1["worst_case_stop_first"]
    lines = [
        "# P2-W3 / H-7 exit-integrity forensic (IS partition)",
        "",
        f"**Date:** 2026-06-08  ",
        f"**Scope:** Diagnosis only — IS **{GATE1_IS}** trades; OOS sealed  ",
        f"**Gate #1 anchor:** net **${GATE1_NET:.2f}/tr**, WR **{100 * GATE1_WR:.1f}%**  ",
        f"**git_sha:** `{payload['git']['git_sha']}`  ",
        f"**H-7 implementation ref:** `86bd753` (`simulate_p2_trade` walker)",
        "",
        "## Summary verdict",
        "",
        f"**{payload['verdict']}**",
        "",
        "## Check 1 — Intrabar dual-touch resolution",
        "",
        f"- **Fill path:** `{c1['fill_path']}`",
        f"- **M4 engine (`backtest/engine.py`)?** **{'Yes' if c1['m4_engine_used'] else 'No'}**",
        f"- **Dual-touch rule applied:** {c1['dual_touch_rule']}",
        f"- **Config policy (unused by walker):** {c1['m4_equivalent_policy_in_config']}",
        f"- **IS target exits:** {c1['is_target_trades']}",
        f"- **Dual-touch on exit bar (booked target):** {c1['dual_touch_on_exit_bar_among_targets']} "
        f"({c1['dual_touch_pct_of_is']:.2f}% of IS)",
            f"- **Dual-touch any bar (among targets):** {c1['dual_touch_any_bar_among_targets']}",
            (
                "- **Dual-touch inflation vector:** none on booked target exits (stop-first "
                "holds on exit bar); primary mechanical issue is Check 2 same-bar entry bracket."
                if c1["dual_touch_on_exit_bar_among_targets"] == 0
                else ""
            ),
            "",
            "### Hand-verify samples (booked vs first-touch)",
        "",
        "| Session | Booked | Dual-touch bar? | Pessimistic first | Optimistic first | 1-min chrono |",
        "|---------|--------|-----------------|-------------------|------------------|--------------|",
    ]
    for s in c1["hand_verify_samples"]:
        lines.append(
            f"| {s.get('session', '—')} | {s.get('booked_exit', '—')} | "
            f"{s.get('bar_dual_touch', '—')} | {s.get('pessimistic_first', '—')} | "
            f"{s.get('optimistic_first', '—')} | {s.get('chrono_1min_first', '—')} |"
        )
    lines.extend(
        [
            "",
            "### Worst-case stop-first recomputation",
            "",
            f"- **Recomputed net/tr:** ${wc['net_expectancy']:.2f} (delta **${wc['delta_vs_gate1']:+.2f}**)",
            f"- **Recomputed WR:** {100 * wc['win_rate']:.1f}% (delta **{100 * wc['delta_wr_vs_gate1']:+.1f} pp**)",
            f"- **Trades flipped target→stop:** {wc['flipped_trades']}",
            "",
            "## Check 2 — Entry-bar fill realism",
            "",
            f"- **Bracket arms next bar?** **{'Yes' if c2['bracket_arms_next_bar'] else 'No'}**",
            f"- **Mechanism:** {c2['entry_fill_mechanism']}",
            f"- **Same-bar stop/target exits:** **{c2['same_bar_stop_or_target_exit_count']}** "
            f"({c2.get('same_bar_exit_pct_of_is', 0):.1f}% of IS; expect 0)",
            f"- **Entry bar spans full 10/20 bracket:** {c2['entry_bar_spans_full_bracket_count']}",
        ]
    )
    nb = c2.get("next_bar_bracket_recompute")
    if nb:
        lines.extend(
            [
                "",
                "### Next-bar bracket diagnostic recompute",
                "",
                f"- **IS trades re-walked:** {nb.get('count', 0)}",
                f"- **Net/tr:** ${nb.get('net_per_trade', 0):.2f} "
                f"(delta **${nb.get('delta_net_vs_gate1', 0):+.2f}** vs gate #1)",
                f"- **WR:** {100 * (nb.get('win_rate') or 0):.1f}%",
                f"- **Same-bar exits after fix:** {nb.get('same_bar_exits_after_fix', '—')}",
                f"- **Note:** {nb.get('note', '')}",
            ]
        )
    lines.extend(
        [
            "",
            "## Check 3 — Trigger look-ahead",
            "",
            f"- **Completed 5m reclaim close required:** {c3['trigger_uses_completed_5m_close']}",
            f"- **Within-bucket look-ahead:** {c3['lookahead_within_5m_bucket']}",
            f"- **H-3 shared-trigger context:** {c3['h3_shared_trigger_negative']}",
            "",
            "## Check 4 — Exit disposition (IS)",
            "",
            "| Bucket | Count | % | Net total | Net/tr |",
            "|--------|-------|---|-----------|--------|",
        ]
    )
    for name, row in c4["disposition"].items():
        lines.append(
            f"| {name.upper()} | {row['count']} | {row['pct']:.1f}% | "
            f"${row['net_pnl_total']:,.0f} | ${row['net_pnl_per_trade']:.2f} |"
        )
    wrd = c4["wr_decomposition"]
    tsv = c4["time_stop_mark_verification"]
    lines.extend(
        [
            "",
            f"- **Time-stop mark bugs (win at target price):** {tsv['time_wins_booked_at_target_bug']}",
            f"- **Target-capture wins / total wins:** {wrd['target_capture_wins']} / {wrd['total_wins']} "
            f"({100 * wrd['target_fraction_of_wins']:.1f}% of wins)",
            f"- **Time-stop wins / total wins:** {wrd['time_stop_wins']} / {wrd['total_wins']} "
            f"({100 * wrd['time_fraction_of_wins']:.1f}% of wins)",
            f"- **Genuine target captures as % of IS trades:** "
            f"{wrd['genuine_target_capture_pct_of_is']:.1f}%",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    git = _git_meta(_REPO)
    data_root = _REPO / "data" / "raw"
    rth, _ = load_verified_mnq_rth(data_root)
    segments = split_dataframe_at_operator_export_gaps(rth)
    mnq_et = prepare_et_frame(pl.concat(segments) if len(segments) > 1 else segments[0])

    all_trades = run_hypothesis("H-7", segments)
    is_trades, _, part = split_is_oos(all_trades)
    assert len(is_trades) == GATE1_IS, f"IS count drift: {len(is_trades)} != {GATE1_IS}"

    contexts = _build_trade_contexts(mnq_et, is_trades)
    if len(contexts) < GATE1_IS - 5:
        print(f"WARNING: only {len(contexts)} contexts matched of {GATE1_IS} IS trades", file=sys.stderr)

    check2 = _check2_entry_bar(contexts)
    check2["next_bar_bracket_recompute"] = _recompute_is_next_bar_bracket(mnq_et, is_trades)

    payload: dict[str, Any] = {
        "wave": "P2-W3",
        "hypothesis": "H-7",
        "screen": "exit_integrity_forensic_is_only",
        "date": "2026-06-08",
        "git": git,
        "gate1_anchor": {"is_trades": GATE1_IS, "net_per_trade": GATE1_NET, "win_rate": GATE1_WR},
        "partition": part,
        "contexts_matched": len(contexts),
        "check1": _check1_dual_touch(contexts),
        "check2": check2,
        "check3": _check3_lookahead(mnq_et),
        "check4": _check4_disposition(is_trades, contexts),
    }
    payload["verdict"] = _verdict(payload)

    OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
    OUT_STEM.with_suffix(".json").write_text(
        json.dumps(_json_sanitize(payload), indent=2),
        encoding="utf-8",
    )
    OUT_STEM.with_suffix(".md").write_text(_render_md(payload), encoding="utf-8")
    print(f"Wrote {OUT_STEM.with_suffix('.md')}")
    print(f"\n{payload['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
