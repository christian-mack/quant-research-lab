#!/usr/bin/env python3
"""Wave 1 Track 2 — Phase 3 step 3: standalone OTE 6-year MNQ backtest.

Unconstrained RTH collection (no bias gate), primary + 4 single-axis variant logs,
rich per-trade tagging for step-4 constraint/overlap analysis.

Run: ``uv run python scripts/run_wave1_track2_phase3_step3_ote_backtest.py``
"""

from __future__ import annotations

import datetime as dt
import json
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
from quant_research.ict import bias_module as bm
from quant_research.research_wave1.instrument_pipeline import load_continuous_rth_mnq_style
from quant_research.ict import pd_arrays as pd_mod
from quant_research.ict.ote_strategy import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    ENTRY_OTE_62,
    ENTRY_OTE_705,
    ET,
    FVG_NEAREST_OTE,
    OteSetup,
    OteStrategyConfig,
    STOP_FVG_C2,
    STOP_SWEPT_EXTREME,
    TARGET_FAR,
    TARGET_NEAREST,
    ote_fib_price,
    scan_setups,
)

DATA_ROOT = _REPO / "data" / "raw"
PROTOCOL_START = dt.date(2020, 1, 1)
PROTOCOL_END = dt.date(2026, 4, 19)
OUT_STEM = _REPO / "notebooks" / "validation" / "2026-06-06_wave1_track2_phase3_step3_ote_backtest"
TRADES_DIR = OUT_STEM.parent / "2026-06-06_wave1_track2_phase3_step3_ote_trades"

MNQ_POINT_VALUE = 2.0
TICK_SIZE = 0.25

PRIMARY_CFG = OteStrategyConfig()
SCAN_CONFIGS: dict[str, OteStrategyConfig] = {
    "primary": PRIMARY_CFG,
    "entry_ote_62": OteStrategyConfig(entry_mode=ENTRY_OTE_62),
    "fvg_nearest_ote": OteStrategyConfig(fvg_tiebreak=FVG_NEAREST_OTE),
}

# Derived from primary setups (no re-scan): single-axis flips on stop/target only.
DERIVED_VARIANTS: dict[str, tuple[str, str]] = {
    "target_far": (STOP_SWEPT_EXTREME, TARGET_FAR),
    "stop_fvg_c2": (STOP_FVG_C2, TARGET_NEAREST),
}

MIN_SETUPS_STOP = 100
CONFLICT_SURFACE_FRAC = 0.30
STRONG_EDGE_ANNUAL = 2000.0


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


def _bias_maps(
    mnq: pl.DataFrame,
    correlated: dict[str, pl.DataFrame],
) -> tuple[dict[dt.date, str], dict[dt.date, str]]:
    c1 = bm.BiasConfig(pairing_timeframe="5m", smt_required=False)
    c2 = bm.BiasConfig(pairing_timeframe="5m", smt_required=True)
    c1_map: dict[dt.date, str] = {}
    for sb in bm.run_bias_series(mnq, config=c1, correlated_rth=correlated):
        if sb.p_eq is None:
            c1_map[sb.session_date] = bm.BIAS_NONE
        else:
            b, _ = bm.emit_bias(sb.bullish, sb.bearish, smt_required=False)
            c1_map[sb.session_date] = b
    c2_map: dict[dt.date, str] = {}
    for sb in bm.run_bias_series(mnq, config=c2, correlated_rth=correlated):
        if sb.p_eq is None:
            c2_map[sb.session_date] = bm.BIAS_NONE
        else:
            b, _ = bm.emit_bias(sb.bullish, sb.bearish, smt_required=True)
            c2_map[sb.session_date] = b
    return c1_map, c2_map


def _session_frames(mnq: pl.DataFrame) -> dict[dt.date, pl.DataFrame]:
    out: dict[dt.date, pl.DataFrame] = {}
    for sd in mnq["cme_session_date"].unique().sort().to_list():
        if sd is None:
            continue
        out[sd] = mnq.filter(pl.col("cme_session_date") == sd).sort("timestamp")
    return out


def _fvg_zone_entry(setup: OteSetup) -> float:
    return setup.fvg_top if setup.direction == DIRECTION_LONG else setup.fvg_bottom


def _risk_points(entry: float, stop: float) -> float:
    return abs(entry - stop)


def _pnl_points(direction: str, entry: float, exit_price: float) -> float:
    if direction == DIRECTION_LONG:
        return exit_price - entry
    return entry - exit_price


def _active_stop(setup: OteSetup, stop_arm: str) -> float:
    return setup.stop_arm_a if stop_arm == STOP_SWEPT_EXTREME else setup.stop_arm_b


def _active_target(setup: OteSetup, target_mode: str) -> float:
    return setup.target_nearest if target_mode == TARGET_NEAREST else setup.target_far


def _simulate_exit(
    sess: pl.DataFrame,
    *,
    fill_idx: int,
    direction: str,
    entry: float,
    stop: float,
    target: float,
) -> tuple[str, float, int, Any]:
    highs = sess["high"].to_list()
    lows = sess["low"].to_list()
    closes = sess["close"].to_list()
    times = sess["timestamp"].to_list()
    n = len(highs)
    end = n - 1
    is_long = direction == DIRECTION_LONG
    for i in range(fill_idx, n):
        if is_long:
            if lows[i] <= stop:
                return "stop", stop, i, times[i]
            if highs[i] >= target:
                return "target", target, i, times[i]
        else:
            if highs[i] >= stop:
                return "stop", stop, i, times[i]
            if lows[i] <= target:
                return "target", target, i, times[i]
    return "time", closes[end], end, times[end]


def _entry_fill_idx(
    sess: pl.DataFrame,
    *,
    direction: str,
    entry_price: float,
    start_index: int,
) -> int | None:
    for i in range(start_index, sess.height):
        lo = float(sess["low"][i])
        hi = float(sess["high"][i])
        if direction == DIRECTION_LONG and lo <= entry_price:
            return i
        if direction == DIRECTION_SHORT and hi >= entry_price:
            return i
    return None


def _enrich_trade(
    setup: OteSetup,
    sess: pl.DataFrame,
    *,
    variant: str,
    stop_arm: str,
    target_mode: str,
    entry_mode: str,
    fvg_tiebreak: str,
    setup_number: int,
    bias_c1: str,
    bias_c2: str,
) -> dict[str, Any] | None:
    if setup.entry_fill_index is None or setup.session_date is None:
        return None

    fill_idx = setup.entry_fill_index
    entry = setup.entry_price
    direction = setup.direction
    stop_active = _active_stop(setup, stop_arm)
    target_active = _active_target(setup, target_mode)

    exit_reason, exit_price, exit_idx, exit_ts = _simulate_exit(
        sess,
        fill_idx=fill_idx,
        direction=direction,
        entry=entry,
        stop=stop_active,
        target=target_active,
    )

    risk_primary = _risk_points(entry, stop_active)
    pnl_pts = _pnl_points(direction, entry, exit_price)
    pnl_usd = pnl_pts * MNQ_POINT_VALUE

    _, exit_near, _, _ = _simulate_exit(
        sess, fill_idx=fill_idx, direction=direction,
        entry=entry, stop=setup.stop_arm_a, target=setup.target_nearest,
    )
    _, exit_far, _, _ = _simulate_exit(
        sess, fill_idx=fill_idx, direction=direction,
        entry=entry, stop=setup.stop_arm_a, target=setup.target_far,
    )
    _, exit_stop_b, _, _ = _simulate_exit(
        sess, fill_idx=fill_idx, direction=direction,
        entry=entry, stop=setup.stop_arm_b, target=setup.target_nearest,
    )

    r_a_near = _pnl_points(direction, entry, exit_near) / _risk_points(entry, setup.stop_arm_a)
    r_a_far = _pnl_points(direction, entry, exit_far) / _risk_points(entry, setup.stop_arm_a)
    r_b_near = _pnl_points(direction, entry, exit_stop_b) / _risk_points(entry, setup.stop_arm_b)

    fvg_entry = _fvg_zone_entry(setup)
    ote_705 = ote_fib_price(direction, setup.displacement_low, setup.displacement_high, 0.705)
    ote_62 = ote_fib_price(direction, setup.displacement_low, setup.displacement_high, 0.62)

    fvg_fill_idx = _entry_fill_idx(
        sess, direction=direction, entry_price=fvg_entry,
        start_index=setup.mss_index + 1,
    )
    fvg_pnl_usd: float | None = None
    if fvg_fill_idx is not None:
        _, ep, _, _ = _simulate_exit(
            sess, fill_idx=fvg_fill_idx, direction=direction,
            entry=fvg_entry, stop=setup.stop_arm_a, target=setup.target_nearest,
        )
        fvg_pnl_usd = _pnl_points(direction, fvg_entry, ep) * MNQ_POINT_VALUE

    entry_ts = setup.entry_fill_timestamp
    entry_et = entry_ts.astimezone(ET) if entry_ts else None
    sweep_depth_ticks = abs(setup.swept_extreme - setup.sweep_level) / TICK_SIZE
    disp_size = setup.displacement_high - setup.displacement_low
    fvg_size = setup.fvg_top - setup.fvg_bottom

    trade_dir_bias = bm.BIAS_LONG if direction == DIRECTION_LONG else bm.BIAS_SHORT
    agrees_c1 = bias_c1 == trade_dir_bias
    agrees_c2 = bias_c2 == trade_dir_bias

    return {
        "variant": variant,
        "session_date": setup.session_date.isoformat(),
        "setup_number_in_session": setup_number,
        "direction": direction,
        "entry_timestamp": str(entry_ts),
        "entry_time_et": entry_et.strftime("%H:%M:%S") if entry_et else None,
        "entry_hour_et": entry_et.hour if entry_et else None,
        "exit_timestamp": str(exit_ts),
        "exit_reason": exit_reason,
        "entry_price": entry,
        "exit_price": exit_price,
        "pnl_points": pnl_pts,
        "pnl_usd_mnq": pnl_usd,
        "risk_points_primary": risk_primary,
        "r_multiple_primary": (pnl_pts / risk_primary if risk_primary > 0 else None),
        "stop_arm_a": setup.stop_arm_a,
        "stop_arm_b": setup.stop_arm_b,
        "stop_active": stop_active,
        "target_nearest": setup.target_nearest,
        "target_nearest_kind": setup.target_nearest_kind,
        "target_far": setup.target_far,
        "target_far_kind": setup.target_far_kind,
        "target_active": target_active,
        "exit_price_target_nearest": exit_near,
        "exit_price_target_far": exit_far,
        "exit_price_stop_arm_b": exit_stop_b,
        "r_multiple_stop_a_target_nearest": r_a_near,
        "r_multiple_stop_a_target_far": r_a_far,
        "r_multiple_stop_b_target_nearest": r_b_near,
        "fvg_ote_conflict": setup.fvg_ote_conflict,
        "fvg_ote_distance_ticks": setup.fvg_ote_distance_ticks,
        "entry_price_ote_active": entry,
        "entry_price_ote_705": ote_705,
        "entry_price_ote_62": ote_62,
        "entry_price_fvg_zone": fvg_entry,
        "pnl_usd_fvg_zone_entry": fvg_pnl_usd,
        "displacement_leg_points": disp_size,
        "fvg_size_points": fvg_size,
        "sweep_depth_ticks": sweep_depth_ticks,
        "sweep_level": setup.sweep_level,
        "swept_extreme": setup.swept_extreme,
        "mss_swing_broken": setup.mss_swing_broken,
        "bias_c1": bias_c1,
        "bias_c2": bias_c2,
        "bias_agrees_c1": agrees_c1,
        "bias_agrees_c2": agrees_c2,
        "config_target_mode": target_mode,
        "config_stop_arm": stop_arm,
        "config_entry_mode": entry_mode,
        "config_fvg_tiebreak": fvg_tiebreak,
        "signal_timestamp": str(setup.signal_timestamp),
        "mss_index": setup.mss_index,
        "entry_fill_index": fill_idx,
        "exit_bar_index": exit_idx,
    }


def _setups_to_trades(
    setups: list[OteSetup],
    sessions: dict[dt.date, pl.DataFrame],
    bias_c1: dict[dt.date, str],
    bias_c2: dict[dt.date, str],
    *,
    variant: str,
    stop_arm: str,
    target_mode: str,
    entry_mode: str,
    fvg_tiebreak: str,
) -> list[dict[str, Any]]:
    per_session_count: dict[dt.date, int] = defaultdict(int)
    trades: list[dict[str, Any]] = []
    for setup in setups:
        if setup.session_date is None:
            continue
        per_session_count[setup.session_date] += 1
        sess = sessions.get(setup.session_date)
        if sess is None:
            continue
        row = _enrich_trade(
            setup,
            sess,
            variant=variant,
            stop_arm=stop_arm,
            target_mode=target_mode,
            entry_mode=entry_mode,
            fvg_tiebreak=fvg_tiebreak,
            setup_number=per_session_count[setup.session_date],
            bias_c1=bias_c1.get(setup.session_date, bm.BIAS_NONE),
            bias_c2=bias_c2.get(setup.session_date, bm.BIAS_NONE),
        )
        if row is not None:
            trades.append(row)
    return trades


def _economics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {"n_trades": 0}
    pnls = [t["pnl_usd_mnq"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    by_year: dict[str, float] = defaultdict(float)
    for t in trades:
        by_year[t["session_date"][:4]] += t["pnl_usd_mnq"]
    n_years = max(len(by_year), 1)
    rs = [t["r_multiple_primary"] for t in trades if t["r_multiple_primary"] is not None]
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    return {
        "n_trades": len(trades),
        "total_pnl_usd": sum(pnls),
        "annual_pnl_usd": sum(pnls) / n_years,
        "win_rate": len(wins) / len(trades),
        "avg_win_usd": avg_win,
        "avg_loss_usd": avg_loss,
        "reward_risk_ratio": (abs(avg_win / avg_loss) if avg_loss else None),
        "avg_r": (sum(rs) / len(rs)) if rs else None,
        "year_pnl_usd": dict(by_year),
    }


def _frequency_stats(trades: list[dict[str, Any]], n_sessions: int) -> dict[str, Any]:
    if not trades:
        return {"n_trades": 0}
    per_sess = Counter(t["session_date"] for t in trades)
    counts = list(per_sess.values())
    n_years = max(len({t["session_date"][:4] for t in trades}), 1)
    multi = sum(1 for c in counts if c > 1)
    return {
        "n_trades": len(trades),
        "trades_per_year": len(trades) / n_years,
        "sessions_with_trade": len(per_sess),
        "sessions_with_multiple_trades": multi,
        "pct_sessions_multiple": multi / len(per_sess) if per_sess else 0.0,
        "avg_setups_per_session_with_trade": sum(counts) / len(per_sess) if per_sess else 0.0,
        "max_trades_one_session": max(counts) if counts else 0,
        "setup_count_distribution": {str(k): v for k, v in sorted(Counter(counts).items())},
        "n_sessions_in_data": n_sessions,
    }


def _conflict_diag(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {}
    n = len(trades)
    conflict = [t for t in trades if t["fvg_ote_conflict"]]
    frac = len(conflict) / n
    ote_pnls = [t["pnl_usd_mnq"] for t in trades]
    fvg_pnls = [
        t["pnl_usd_fvg_zone_entry"]
        for t in trades
        if t["pnl_usd_fvg_zone_entry"] is not None
    ]
    conflict_fvg = [
        t["pnl_usd_fvg_zone_entry"]
        for t in conflict
        if t["pnl_usd_fvg_zone_entry"] is not None
    ]
    return {
        "n_trades": n,
        "n_conflict": len(conflict),
        "conflict_fraction": frac,
        "ote_total_pnl_usd": sum(ote_pnls),
        "fvg_zone_total_pnl_usd": sum(fvg_pnls) if fvg_pnls else None,
        "fvg_zone_n_filled": len(fvg_pnls),
        "conflict_subset_ote_pnl": sum(t["pnl_usd_mnq"] for t in conflict),
        "conflict_subset_fvg_pnl": sum(conflict_fvg) if conflict_fvg else None,
        "pnl_delta_fvg_minus_ote": (
            (sum(fvg_pnls) - sum(ote_pnls)) if fvg_pnls else None
        ),
    }


def _target_fork_diag(
    primary: list[dict[str, Any]],
    far_log: list[dict[str, Any]],
) -> dict[str, Any]:
    def _subset_stats(trades: list[dict[str, Any]], r_key: str) -> dict[str, Any]:
        if not trades:
            return {}
        wins = sum(1 for t in trades if t["pnl_usd_mnq"] > 0)
        rs = [t[r_key] for t in trades if t.get(r_key) is not None]
        by_year: dict[str, float] = defaultdict(float)
        for t in trades:
            by_year[t["session_date"][:4]] += t["pnl_usd_mnq"]
        n_years = max(len(by_year), 1)
        return {
            "n_trades": len(trades),
            "win_rate": wins / len(trades),
            "avg_r": sum(rs) / len(rs) if rs else None,
            "annual_pnl_usd": sum(t["pnl_usd_mnq"] for t in trades) / n_years,
            "year_pnl_usd": dict(by_year),
        }

    return {
        "nearest_counterfactual_primary_entry": _subset_stats(
            primary, "r_multiple_stop_a_target_nearest",
        ),
        "far_counterfactual_primary_entry": _subset_stats(
            primary, "r_multiple_stop_a_target_far",
        ),
        "far_variant_active_log": _subset_stats(far_log, "r_multiple_primary"),
        "note": (
            "Nearest counterfactual uses primary-entry fills with stop A + nearest target; "
            "far counterfactual uses primary-entry fills with stop A + far target; "
            "far_variant_active_log is the dedicated target_far single-flip trade log."
        ),
    }


def _bias_overlap_preview(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {}
    agree = [t for t in trades if t["bias_agrees_c1"]]
    disagree = [t for t in trades if not t["bias_agrees_c1"]]
    clear = [t for t in trades if t["bias_c1"] != bm.BIAS_NONE]
    return {
        "fraction_bias_agrees_c1": len(agree) / len(trades),
        "fraction_on_clear_bias_session": len(clear) / len(trades),
        "agree_c1_economics": _economics(agree),
        "disagree_or_no_bias_c1_economics": _economics(disagree),
    }


def _hour_preview(trades: list[dict[str, Any]]) -> dict[str, Any]:
    if not trades:
        return {}
    by_hour: dict[int, list[float]] = defaultdict(list)
    for t in trades:
        h = t.get("entry_hour_et")
        if h is not None:
            by_hour[h].append(t["pnl_usd_mnq"])
    return {
        str(h): {
            "n": len(ps),
            "total_pnl": sum(ps),
            "avg_pnl": sum(ps) / len(ps),
            "win_rate": sum(1 for p in ps if p > 0) / len(ps),
        }
        for h, ps in sorted(by_hour.items())
    }


def _render_md(report: dict[str, Any]) -> str:
    freq = report["frequency"]
    econ = report["economics_primary"]
    conflict = report["conflict"]
    lines = [
        "# Wave 1 Track 2 — Phase 3 step 3: Standalone OTE backtest",
        "",
        f"**Date run:** 2026-06-06  ",
        f"**git_sha:** `{report['git_sha']}`  ",
        f"**Protocol:** {report['protocol_window'][0]} → {report['protocol_window'][1]}  ",
        f"**Mode:** Unconstrained RTH (no bias gate, multi-setup/session)  ",
        "",
        "## (a) Trade frequency",
        "",
        f"- Total setups (primary): **{freq['n_trades']:,}**",
        f"- Trades/year: **{freq['trades_per_year']:.1f}**",
        f"- Sessions with ≥1 trade: **{freq['sessions_with_trade']:,}** "
        f"({100 * freq['sessions_with_trade'] / freq['n_sessions_in_data']:.1f}% of sessions)",
        f"- Sessions with multiple trades: **{freq['sessions_with_multiple_trades']:,}** "
        f"({100 * freq['pct_sessions_multiple']:.1f}% of trading sessions)",
        f"- Max setups in one session: **{freq['max_trades_one_session']}**",
        "",
        "## (b) Headline economics (primary, qty=1 MNQ)",
        "",
        f"- Total P&L: **${econ['total_pnl_usd']:,.0f}**",
        f"- Annual P&L: **${econ['annual_pnl_usd']:,.0f}**",
        f"- Win rate: **{100 * econ['win_rate']:.1f}%**",
        f"- Avg win / avg loss: **${econ['avg_win_usd']:.0f}** / **${econ['avg_loss_usd']:.0f}**",
        f"- Reward:Risk (avg win / |avg loss|): **{econ.get('reward_risk_ratio', 0):.2f}**",
        f"- Avg R: **{econ.get('avg_r', 0):.2f}**",
        "",
        "### Year-by-year P&L (primary)",
        "",
    ]
    for y, p in sorted(econ.get("year_pnl_usd", {}).items()):
        lines.append(f"- {y}: ${p:,.0f}")
    lines.extend([
        "",
        "## (c) FVG/OTE conflict",
        "",
        f"- Conflict fraction (>4 ticks): **{100 * conflict['conflict_fraction']:.1f}%** "
        f"({conflict['n_conflict']:,} / {conflict['n_trades']:,})",
    ])
    if conflict.get("pnl_delta_fvg_minus_ote") is not None:
        lines.append(
            f"- Total P&L OTE entry: ${conflict['ote_total_pnl_usd']:,.0f}; "
            f"FVG-zone entry: ${conflict['fvg_zone_total_pnl_usd']:,.0f} "
            f"(delta ${conflict['pnl_delta_fvg_minus_ote']:,.0f})"
        )
    lines.extend([
        "",
        "## (d) Target fork preview",
        "",
        f"- Nearest (counterfactual on primary fills): WR "
        f"{100 * report['target_fork']['nearest_counterfactual_primary_entry']['win_rate']:.1f}%, "
        f"annual ${report['target_fork']['nearest_counterfactual_primary_entry']['annual_pnl_usd']:,.0f}",
        f"- Far (counterfactual on primary fills): WR "
        f"{100 * report['target_fork']['far_counterfactual_primary_entry']['win_rate']:.1f}%, "
        f"annual ${report['target_fork']['far_counterfactual_primary_entry']['annual_pnl_usd']:,.0f}",
        f"- Far (active variant log): WR "
        f"{100 * report['target_fork']['far_variant_active_log']['win_rate']:.1f}%, "
        f"annual ${report['target_fork']['far_variant_active_log']['annual_pnl_usd']:,.0f}",
        "",
        "## (e) Bias overlap preview (C1)",
        "",
        f"- Fraction setups on bias-agreeing sessions: "
        f"**{100 * report['bias_overlap']['fraction_bias_agrees_c1']:.1f}%**",
        f"- Agree subset annual P&L: "
        f"**${report['bias_overlap']['agree_c1_economics'].get('annual_pnl_usd', 0):,.0f}** "
        f"(WR {100 * report['bias_overlap']['agree_c1_economics'].get('win_rate', 0):.1f}%)",
        f"- Disagree/no-bias subset annual P&L: "
        f"**${report['bias_overlap']['disagree_or_no_bias_c1_economics'].get('annual_pnl_usd', 0):,.0f}** "
        f"(WR {100 * report['bias_overlap']['disagree_or_no_bias_c1_economics'].get('win_rate', 0):.1f}%)",
        "",
        "## Stop conditions",
        "",
    ])
    for k, v in report["stop_conditions"].items():
        lines.append(f"- **{k}:** {v}")
    lines.extend(["", "## Variant economics (all 5 logs)", ""])
    for name, e in report["variant_economics"].items():
        lines.append(
            f"- **{name}:** n={e['n_trades']:,}, annual=${e.get('annual_pnl_usd', 0):,.0f}, "
            f"WR={100 * e.get('win_rate', 0):.1f}%"
        )
    lines.append("")
    lines.append(f"Trade logs: `{TRADES_DIR}`")
    return "\n".join(lines)


def main() -> None:
    git_sha = _git_sha()
    print("Loading MNQ / MES / MYM ...", flush=True)
    frames: dict[str, pl.DataFrame] = {}
    for name, pattern in [
        ("MNQ", data_loader.MNQ_CONTRACT_GLOB),
        ("MES", data_loader.MES_CONTRACT_GLOB),
        ("MYM", data_loader.MYM_CONTRACT_GLOB),
    ]:
        frames[name] = load_continuous_rth_mnq_style(
            DATA_ROOT,
            pattern=pattern,
            protocol_start=PROTOCOL_START,
            protocol_end_inclusive=PROTOCOL_END,
        )
        print(f"  {name}: {frames[name].height:,} RTH bars", flush=True)

    mnq = pd_mod.add_pd_arrays(frames["MNQ"])
    correlated = {"MES": frames["MES"], "MYM": frames["MYM"]}

    print("Running bias module (C1/C2 tagging) ...", flush=True)
    bias_c1, bias_c2 = _bias_maps(mnq, correlated)
    sessions = _session_frames(mnq)
    n_sessions = len(sessions)

    scanned: dict[str, list[OteSetup]] = {}
    for variant, cfg in SCAN_CONFIGS.items():
        print(f"Scanning setups variant={variant} ...", flush=True)
        scanned[variant] = scan_setups(mnq, config=cfg)
        print(f"  -> {len(scanned[variant]):,} setups", flush=True)

    all_logs: dict[str, list[dict[str, Any]]] = {}
    all_logs["primary"] = _setups_to_trades(
        scanned["primary"], sessions, bias_c1, bias_c2,
        variant="primary",
        stop_arm=STOP_SWEPT_EXTREME, target_mode=TARGET_NEAREST,
        entry_mode=ENTRY_OTE_705, fvg_tiebreak="earliest",
    )
    for derived, (stop_arm, target_mode) in DERIVED_VARIANTS.items():
        all_logs[derived] = _setups_to_trades(
            scanned["primary"], sessions, bias_c1, bias_c2,
            variant=derived,
            stop_arm=stop_arm, target_mode=target_mode,
            entry_mode=ENTRY_OTE_705, fvg_tiebreak="earliest",
        )
    all_logs["entry_ote_62"] = _setups_to_trades(
        scanned["entry_ote_62"], sessions, bias_c1, bias_c2,
        variant="entry_ote_62",
        stop_arm=STOP_SWEPT_EXTREME, target_mode=TARGET_NEAREST,
        entry_mode=ENTRY_OTE_62, fvg_tiebreak="earliest",
    )
    all_logs["fvg_nearest_ote"] = _setups_to_trades(
        scanned["fvg_nearest_ote"], sessions, bias_c1, bias_c2,
        variant="fvg_nearest_ote",
        stop_arm=STOP_SWEPT_EXTREME, target_mode=TARGET_NEAREST,
        entry_mode=ENTRY_OTE_705, fvg_tiebreak=FVG_NEAREST_OTE,
    )

    primary = all_logs["primary"]
    freq = _frequency_stats(primary, n_sessions)
    econ_primary = _economics(primary)
    conflict = _conflict_diag(primary)
    target_fork = _target_fork_diag(primary, all_logs["target_far"])
    bias_prev = _bias_overlap_preview(primary)
    hour_prev = _hour_preview(primary)
    variant_econ = {k: _economics(v) for k, v in all_logs.items()}

    stop_conditions = {
        "low_frequency_STOP": freq["n_trades"] < MIN_SETUPS_STOP,
        "n_trades_primary": freq["n_trades"],
        "high_conflict_SURFACE": conflict.get("conflict_fraction", 0) > CONFLICT_SURFACE_FRAC,
        "conflict_fraction": round(conflict.get("conflict_fraction", 0), 4),
        "all_variants_negative_SURFACE": all(
            variant_econ[k].get("annual_pnl_usd", 0) < 0 for k in all_logs
        ),
        "strong_positive_EDGE_SURFACE": econ_primary.get("annual_pnl_usd", 0) > STRONG_EDGE_ANNUAL,
        "annual_pnl_primary": round(econ_primary.get("annual_pnl_usd", 0), 2),
    }

    report = {
        "wave": "Wave 1 Track 2 Phase 3 step 3 — standalone OTE backtest",
        "git_sha": git_sha,
        "protocol_window": [str(PROTOCOL_START), str(PROTOCOL_END)],
        "bar_counts": {k: v.height for k, v in frames.items()},
        "scan_counts": {k: len(v) for k, v in scanned.items()},
        "trade_log_counts": {k: len(v) for k, v in all_logs.items()},
        "frequency": freq,
        "economics_primary": econ_primary,
        "conflict": conflict,
        "target_fork": target_fork,
        "bias_overlap": bias_prev,
        "hour_distribution": hour_prev,
        "variant_economics": variant_econ,
        "stop_conditions": stop_conditions,
        "trade_log_dir": str(TRADES_DIR),
    }

    OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
    TRADES_DIR.mkdir(parents=True, exist_ok=True)
    OUT_STEM.with_suffix(".json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8",
    )
    OUT_STEM.with_suffix(".md").write_text(_render_md(report), encoding="utf-8")

    for variant, trades in all_logs.items():
        path = TRADES_DIR / f"{variant}.json"
        path.write_text(json.dumps(trades, indent=2, default=str), encoding="utf-8")
        print(f"Wrote {path} ({len(trades):,} trades)", flush=True)

    print(f"\nWrote {OUT_STEM.with_suffix('.json')}", flush=True)
    print(f"Wrote {OUT_STEM.with_suffix('.md')}", flush=True)
    print("\n=== STOP CONDITIONS ===", flush=True)
    print(json.dumps(stop_conditions, indent=2), flush=True)
    print("\n=== PRIMARY ECONOMICS ===", flush=True)
    print(json.dumps(econ_primary, indent=2), flush=True)


if __name__ == "__main__":
    main()
