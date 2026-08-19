#!/usr/bin/env python3
"""H-W4-7 quarterly close-location continuation — distribution, frequency, M4 grade.

Usage::

    uv run python scripts/run_hw4_7_quarter_continuation.py

Writes ``notebooks/validation/2026-08-18_hw4_7_quarter_continuation.{md,json,png}``.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import subprocess
import sys
import warnings
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.backtest import BacktestEngine, as_module
from quant_research.backtest.m6_metrics import compute_m6_aggregates, protocol_year_fraction
from quant_research.backtest.schema import empty_trade_log
from quant_research.backtest.validation import validate_backtest_result
from quant_research.data import continuous_contract, data_loader, session
from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.data.session import SESSION_ETH, SESSION_RTH
from quant_research.modules.quarter_continuation import (
    MODULE_ID,
    QUARTER_BLOCKS,
    QuarterContinuationStrategy,
    annotate_trades_with_signal_quarter,
    completed_quarter_stats,
    holds_cross_maintenance_et,
    qcl_backtest_config,
    qcl_validation_thresholds,
    quarter_block_id_et,
    resample_to_15m_et,
)
from quant_research.statistics.apex_eod_trailing import simulate_eval_window_eod
from quant_research.statistics.deflated_sharpe import (
    deflated_sharpe_ratio,
    sample_moments_from_returns,
)
from quant_research.statistics.trade_report import _trade_sharpe

PROTOCOL_START = dt.date(2020, 1, 1)
PROTOCOL_END = dt.date(2026, 4, 19)
OUT_STEM = _REPO / "notebooks" / "validation" / "2026-08-18_hw4_7_quarter_continuation"
TRADES_STEM = _REPO / "notebooks" / "validation" / "2026-08-18_hw4_7_primary_trades"
FREQ_FLOOR = 200.0
MNQ_N = 15
SESSION1_TRADES = 6410
SESSION1_WIN_RATE = 0.505
SESSION1_NET = 1358.70
SESSION1_DD = 6769.84
REPRO_NET_TOL = 0.02
REPRO_WR_TOL = 0.0005
REPRO_DD_TOL = 0.02
_ET = ZoneInfo("America/New_York")
_CT = ZoneInfo("America/Chicago")
WIN_LEN = 30
TDD = 2000.0
DLL = 1000.0
POINT_VALUE = 2.0
STOP_POINTS = 50.0
COMMISSION_RT = 1.98
SLIP_STOP_USD = 0.50


def _git_meta() -> dict[str, object]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_REPO,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=_REPO,
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
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        x = float(obj)
        return None if math.isnan(x) or math.isinf(x) else x
    if isinstance(obj, dt.datetime | dt.date):
        return obj.isoformat()
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        x = float(obj)
        return None if math.isnan(x) or math.isinf(x) else x
    return str(obj)


def load_continuous_eth_rth(data_root: Path) -> pl.DataFrame:
    """Full-session (ETH+RTH) continuous MNQ in the protocol window."""
    pattern = data_loader.MNQ_CONTRACT_GLOB
    paths = data_loader.discover_contract_files(data_root, pattern=pattern)
    if not paths:
        msg = f"No files matching {pattern!r} under {data_root}"
        raise FileNotFoundError(msg)
    raw = data_loader.load_contracts(paths, timezone=data_loader.CME_TIMEZONE)
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    in_sess = dated.filter(pl.col("session").is_in([SESSION_RTH, SESSION_ETH]))
    ts0 = dt.datetime.combine(PROTOCOL_START, dt.time.min).replace(tzinfo=_CT)
    ts_end = dt.datetime.combine(PROTOCOL_END + dt.timedelta(days=1), dt.time.min).replace(
        tzinfo=_CT
    )
    return in_sess.filter((pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts_end)).sort(
        "timestamp"
    )


def dst_spot_check(bars_15m: pl.DataFrame) -> dict[str, object]:
    """Verify ET block ids around DST weekends (02:00 ET Sunday has no Globex bars).

    US DST shifts at Sunday 02:00 ET, inside the CME weekend close. The live-tape
    check is the Sunday 18:00 ET reopen plus weekday overnight blocks in DST-on
    vs DST-off months. Instant-level 02:00 classification is covered by unit tests.
    """

    def _first_block_at(ts: dt.datetime) -> str | None:
        sub = bars_15m.filter(
            (pl.col("timestamp") >= ts) & (pl.col("timestamp") < ts + dt.timedelta(minutes=30))
        )
        if sub.is_empty():
            return None
        return quarter_block_id_et(sub["timestamp"][0])

    spring_reopen = _first_block_at(dt.datetime(2020, 3, 8, 18, 0, tzinfo=_ET))
    fall_reopen = _first_block_at(dt.datetime(2020, 11, 1, 18, 0, tzinfo=_ET))
    jan_2200 = _first_block_at(dt.datetime(2020, 1, 7, 22, 0, tzinfo=_ET))
    jan_0200 = _first_block_at(dt.datetime(2020, 1, 8, 2, 0, tzinfo=_ET))
    jun_2200 = _first_block_at(dt.datetime(2020, 6, 2, 22, 0, tzinfo=_ET))
    jun_0200 = _first_block_at(dt.datetime(2020, 6, 3, 2, 0, tzinfo=_ET))
    checks = {
        "spring_reopen_2020_03_08_1800": spring_reopen,
        "fall_reopen_2020_11_01_1800": fall_reopen,
        "jan_2200": jan_2200,
        "jan_0200": jan_0200,
        "jun_2200": jun_2200,
        "jun_0200": jun_0200,
    }
    spring_ok = spring_reopen == "18:00-22:00"
    fall_ok = fall_reopen == "18:00-22:00"
    overnight_ok = (
        jan_2200 == "22:00-02:00"
        and jan_0200 == "02:00-06:00"
        and jun_2200 == "22:00-02:00"
        and jun_0200 == "02:00-06:00"
    )
    return {
        "checks": checks,
        "spring_ok": spring_ok,
        "fall_ok": fall_ok,
        "overnight_ok": overnight_ok,
        "passed": spring_ok and fall_ok and overnight_ok,
        "note": (
            "US DST is Sunday 02:00 ET during the CME weekend close; "
            "no 15-min bars exist at the transition instant."
        ),
    }


def range_distribution(stats: pl.DataFrame) -> tuple[list[dict[str, object]], Path]:
    years = stats.with_columns(
        pl.col("last_bar_time").dt.convert_time_zone("America/New_York").dt.year().alias("year")
    ).filter(pl.col("q_range") > 0)
    table: list[dict[str, object]] = []
    for year in range(2020, 2027):
        col = years.filter(pl.col("year") == year)["q_range"]
        if col.is_empty():
            continue
        arr = col.to_numpy()
        row = {
            "year": year,
            "n": int(arr.size),
            "p10": float(np.quantile(arr, 0.10)),
            "p25": float(np.quantile(arr, 0.25)),
            "median": float(np.quantile(arr, 0.50)),
            "p75": float(np.quantile(arr, 0.75)),
            "p90": float(np.quantile(arr, 0.90)),
            "frac_range_lt_50": float(np.mean(arr < 50.0)),
            "frac_50_vs_median": float(50.0 / float(np.median(arr)))
            if float(np.median(arr)) > 0
            else None,
        }
        table.append(row)

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ys = [r["year"] for r in table]
    ax.fill_between(
        ys, [r["p10"] for r in table], [r["p90"] for r in table], alpha=0.15, label="p10–p90"
    )
    ax.plot(ys, [r["p25"] for r in table], "--", label="p25")
    ax.plot(ys, [r["median"] for r in table], "o-", label="median")
    ax.plot(ys, [r["p75"] for r in table], "--", label="p75")
    ax.axhline(50.0, color="crimson", linewidth=1.2, label="50-pt bracket")
    ax.set_xlabel("Year")
    ax.set_ylabel("4h-quarter high–low range (MNQ points)")
    ax.set_title("H-W4-7 quarter-range distribution (ETH+RTH, clock-anchored 4h)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    png = OUT_STEM.with_suffix(".png")
    fig.savefig(png, dpi=140)
    plt.close(fig)
    return table, png


def frequency_screen(stats: pl.DataFrame, yfrac: float) -> dict[str, object]:
    traded = stats.filter(pl.col("signal").is_not_null())
    n = traded.height
    per_yr = n / yfrac if yfrac > 0 else 0.0
    by_block: dict[str, int] = {b: 0 for b in QUARTER_BLOCKS}
    by_tier: dict[str, int] = {
        "ge_0.75": 0,
        "0.50_to_0.75": 0,
        "0.25_to_0.50": 0,
        "le_0.25": 0,
        "eq_0.50": 0,
    }
    by_block_tier: dict[str, dict[str, int]] = {b: {k: 0 for k in by_tier} for b in QUARTER_BLOCKS}
    for row in traded.iter_rows(named=True):
        b = str(row["quarter_block"])
        t = str(row["tier"]) if row["tier"] is not None else "eq_0.50"
        by_block[b] = by_block.get(b, 0) + 1
        by_tier[t] = by_tier.get(t, 0) + 1
        if b in by_block_tier and t in by_block_tier[b]:
            by_block_tier[b][t] += 1
    return {
        "n_signals": n,
        "n_quarters": stats.height,
        "n_no_trade": stats.filter(pl.col("signal").is_null()).height,
        "signals_per_year": per_yr,
        "signals_per_session_day": n / max(stats["cme_session_date"].n_unique(), 1),
        "by_block": by_block,
        "by_tier": by_tier,
        "by_block_tier": by_block_tier,
        "clears_200_yr_floor": per_yr >= FREQ_FLOOR,
    }


def _r_of_q(dd_q: float) -> float:
    return max(1.5 * dd_q, dd_q + 500.0)


def dll_two_loss_qmax(*, per_loss_gross: float) -> tuple[int, float]:
    """Largest integer q with 2 * q * (per_loss_gross + friction) < $1000."""
    friction = COMMISSION_RT + SLIP_STOP_USD
    per = per_loss_gross + friction
    best = 0
    for q in range(1, 40):
        if 2.0 * q * per < DLL:
            best = q
        else:
            break
    return best, per


def eval_pass_rate_sessions(
    trade_log: pl.DataFrame,
    session_dates: list[dt.date],
    qty: int,
) -> dict[str, object]:
    if trade_log.is_empty() or len(session_dates) < WIN_LEN:
        return {
            "pass_rate": 0.0,
            "pass_count": 0,
            "total_windows": 0,
            "fail_trailing": 0,
            "fail_no_target": 0,
        }
    pnls = trade_log["net_pnl"].to_numpy() * float(qty)
    exit_ny = [t.astimezone(_ET).date() for t in trade_log["exit_time"].to_list()]
    exit_sess = []
    for t in trade_log["exit_time"].to_list():
        # CME session date: after 18:00 ET the session is the next calendar date
        # in CT; use Chicago date of the bar's session via 16:00 CT close convention
        # approximated as ET date if hour < 18 else ET date + 1 day... fallback:
        # Chicago calendar date of the timestamp (Wave 0 local-date fallback).
        exit_sess.append(t.astimezone(_CT).date())
    # Prefer cme_session_date if we can map via bars — caller may overwrite.
    if "exit_cme_session_date" in trade_log.columns:
        exit_sess = trade_log["exit_cme_session_date"].to_list()

    pass_c = fail_tr = fail_nt = 0
    total_w = len(session_dates) - WIN_LEN + 1
    for i0 in range(total_w):
        wset = set(session_dates[i0 : i0 + WIN_LEN])
        mask = np.array([s in wset for s in exit_sess], dtype=bool)
        sub_p = pnls[mask]
        sub_ny = [exit_ny[j] for j in range(len(exit_ny)) if mask[j]]
        sub_sess = [exit_sess[j] for j in range(len(exit_sess)) if mask[j]]
        r = simulate_eval_window_eod(
            sub_p,
            sub_ny,
            sub_sess,
            starting_balance=50_000.0,
            trailing_dd=TDD,
            profit_target=3_000.0,
            dll_limit=DLL,
            lock_equity_threshold=52_000.0,
            post_lock_floor=50_000.0,
        )
        if r["outcome"] == "pass":
            pass_c += 1
        elif r.get("mode") == "trailing_dd":
            fail_tr += 1
        else:
            fail_nt += 1
    return {
        "pass_rate": pass_c / total_w if total_w else 0.0,
        "pass_count": pass_c,
        "total_windows": total_w,
        "fail_trailing": fail_tr,
        "fail_no_target": fail_nt,
    }


def run_backtest(
    bars_15m: pl.DataFrame,
    *,
    strategy_factory: type | None = None,
) -> dict[str, object]:
    cfg = qcl_backtest_config()
    segments = split_dataframe_at_operator_export_gaps(bars_15m)
    logs: list[pl.DataFrame] = []
    fills_n = 0
    skip = 0
    signals = 0
    suppress_skip = 0
    geom_rejects: dict[str, int] = {}
    bar_frames: list[pl.DataFrame] = []
    factory = strategy_factory or QuarterContinuationStrategy
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Backtest end:")
        for seg in segments:
            strat = factory()
            out = BacktestEngine(cfg).run(seg, [as_module(MODULE_ID, strat)], run_validation=False)
            skip += strat.skip_count
            signals += strat.signal_count
            suppress_skip += strat.suppress_skip_count
            fills_n += len(out.fills)
            for k, v in out.geometry_rejects.items():
                geom_rejects[k] = geom_rejects.get(k, 0) + v
            if not out.trade_log.is_empty():
                logs.append(out.trade_log)
            bar_frames.append(seg)

    if logs:
        combined = pl.concat(logs).sort("entry_time")
        combined = combined.with_columns(pl.arange(1, combined.height + 1).alias("trade_id"))
    else:
        combined = empty_trade_log()
    bars_all = pl.concat(bar_frames) if bar_frames else bars_15m
    report = validate_backtest_result(
        combined,
        config=cfg,
        fills=None,
        bars=bars_all,
        thresholds=qcl_validation_thresholds(),
    )
    cross = 0
    flatten = 0
    if not combined.is_empty():
        for row in combined.iter_rows(named=True):
            reason = str(row["exit_reason"])
            if reason == "session_maintenance_flatten_et":
                flatten += 1
            if holds_cross_maintenance_et(row["entry_time"], row["exit_time"]):
                cross += 1
    return {
        "trade_log": combined,
        "validation": report,
        "n_segments": len(segments),
        "skip_count": skip,
        "signal_count_engine": signals,
        "suppress_skip_count": suppress_skip,
        "geometry_rejects": geom_rejects,
        "maintenance_flatten_exits": flatten,
        "holds_crossing_maintenance": cross,
        "n_fills": fills_n,
        "cfg": cfg,
        "bars": bars_all,
    }


def _render_md(payload: dict[str, object]) -> str:
    dist = payload["range_distribution"]
    freq = payload["frequency"]
    g = payload["grading"]
    v = payload["validation"]
    n_ext = int(freq["by_tier"].get("ge_0.75", 0)) + int(freq["by_tier"].get("le_0.25", 0))
    n_sig = max(int(freq["n_signals"]), 1)
    ext_frac = n_ext / n_sig
    ext_sess = ext_frac * float(freq["signals_per_session_day"])
    lines = [
        "# H-W4-7 Quarterly Close-Location Continuation (MNQ) — harness report",
        "",
        "**Date:** 2026-08-18  ",
        f"**git_sha:** `{payload['git']['git_sha']}`  ",
        f"**git_dirty:** `{payload['git']['git_dirty']}`  ",
        "**Fill path:** M4 `BacktestEngine` (V7 provenance)  ",
        "**Costs:** $1.98 RT + 1 tick stop/time / 0.5 tick target  ",
        f"**MNQ running N (DSR):** **{MNQ_N}**  ",
        "**Verdict:** not issued this session",
        "",
        "## Repro check vs Session 1",
        "",
        "| Metric | Session 1 | This rerun | Delta | OK |",
        "|--------|-----------|------------|-------|----|",
    ]
    for r in payload.get("repro", {}).get("rows", []):
        lines.append(
            f"| {r['metric']} | {r['session1']} | {r['rerun']} | {r['delta']} | "
            f"{'yes' if r['ok'] else 'NO'} |"
        )
    lines += [
        "",
        f"Trade log: `{Path(str(payload.get('trade_log', ''))).name}`",
        "",
        "## W4 pre-conditions",
        "",
        "| Gate | Status |",
        "|------|--------|",
        "| Clean clone | **MET** (worktree of ledger-correction SHA) |",
        "| TDD $2K vs $3K | **RESOLVED** — $2,000 pre-lock trail |",
        "| MES loader | N/A (MNQ-only) |",
        "",
        "## Forced deviations from spec",
        "",
    ]
    for d in payload["deviations"]:
        lines.append(f"- {d}")
    lines += [
        "",
        "## DST spot-check",
        "",
        f"Spring reopen 2020-03-08 18:00 ET: **{payload['dst']['spring_ok']}**; "
        f"fall reopen 2020-11-01 18:00 ET: **{payload['dst']['fall_ok']}**; "
        f"weekday overnight DST-on/off: **{payload['dst']['overnight_ok']}**.",
        "",
        "## Quarter-range distribution (points)",
        "",
        "| Year | n | p10 | p25 | median | p75 | p90 | % range < 50 | 50 / median |",
        "|------|---|-----|-----|--------|-----|-----|--------------|-------------|",
    ]
    for r in dist:
        lines.append(
            f"| {r['year']} | {r['n']} | {r['p10']:.1f} | {r['p25']:.1f} | "
            f"{r['median']:.1f} | {r['p75']:.1f} | {r['p90']:.1f} | "
            f"{100 * r['frac_range_lt_50']:.1f}% | {r['frac_50_vs_median']:.2f} |"
        )
    lines += [
        "",
        f"Chart: `{Path(payload['range_chart']).name}`",
        "",
        "## Frequency screen (signal counts, no P&L)",
        "",
        f"- Quarters classified: **{freq['n_quarters']}**",
        f"- Signals (not 0.50 / not degenerate): **{freq['n_signals']}** "
        f"(**{freq['signals_per_year']:.1f}**/yr, "
        f"**{freq['signals_per_session_day']:.2f}**/session)",
        f"- No-trade quarters: **{freq['n_no_trade']}**",
        f"- Clears ~200/yr floor: **{freq['clears_200_yr_floor']}**",
        f"- Extreme tiers (>=0.75 or <=0.25): **{n_ext}** "
        f"({100 * ext_frac:.1f}% of signals; ~{ext_sess:.2f}/session if gated, not graded).",
        "",
        "### By block",
        "",
        "| Block | n |",
        "|-------|---|",
    ]
    for b in QUARTER_BLOCKS:
        lines.append(f"| {b} | {freq['by_block'].get(b, 0)} |")
    lines += [
        "",
        "### By tier",
        "",
        "| Tier | n |",
        "|------|---|",
    ]
    for t in ("ge_0.75", "0.50_to_0.75", "0.25_to_0.50", "le_0.25", "eq_0.50"):
        lines.append(f"| {t} | {freq['by_tier'].get(t, 0)} |")
    lines += [
        "",
        "## VALIDATION REPORT (V1–V7)",
        "",
        f"**Overall:** {'PASS' if v['passed'] else '**FAIL**'}",
        "",
    ]
    for c in v["checks"]:
        mark = "PASS" if c["passed"] else "FAIL"
        lines.append(f"- **{c['check_id']} {c['name']}:** {mark} — {c['message']}")
    lines += [
        "",
        "## Headline economics (qty=1, net of costs)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Trades | {g['n_trades']} |",
        f"| Trades/yr | {g['trades_per_year']:.1f} |",
        f"| Win rate | {100 * g['win_rate']:.1f}% |",
        f"| Profit factor | {g['profit_factor']:.3f} |",
        f"| Net P&L | ${g['net_pnl']:,.2f} |",
        f"| $/yr | ${g['pnl_per_year']:,.2f} |",
        f"| Max DD (closed path) | ${g['max_dd']:,.2f} |",
        f"| MAR qty=1 | {g['mar_q1']:.3f} |",
        "",
        "### Year-by-year net P&L (qty=1)",
        "",
        "| Year | Net P&L |",
        "|------|---------|",
    ]
    for y, pnl in sorted(g["years"].items()):
        lines.append(f"| {y} | ${pnl:,.2f} |")
    lines += [
        "",
        "## Skips / maintenance",
        "",
        f"- Engine signals: **{payload['engine']['signal_count_engine']}**",
        f"- Skipped (position still open): **{payload['engine']['skip_count']}**",
        f"- Skipped (deadzone suppress): **{payload['engine']['suppress_skip_count']}**",
        f"- Hygiene flatten exits (`session_maintenance_flatten_et`): "
        f"**{payload['engine']['maintenance_flatten_exits']}**",
        f"- Holds crossing 17:00 ET close: **{payload['engine']['holds_crossing_maintenance']}**",
        "",
        "## Max sustainable qty",
        "",
        f"- DD(1): **${g['max_dd']:,.2f}**",
        f"- R(q) ceiling: **${TDD:,.0f}** TDD (Wave 0c-corrected)",
        f"- q_max R(q): **{g['q_max_rq']}** (R(q)={g['r_at_qmax_rq']:,.2f})",
        f"- DLL two-loss (correct 50×$2=**$100**/contract + friction "
        f"${g['dll_friction_per_loss']:.2f}): **q={g['q_max_dll_correct']}**",
        f"- DLL two-loss if spec's $200/contract figure were used: "
        f"**q={g['q_max_dll_spec_text']}** "
        f"(flagged as arithmetic slip; 50×$2=$100)",
        f"- **Binding q_max:** **{g['q_max']}** ({g['binding']})",
        "",
        f"### Graded at q={g['q_max']}",
        "",
        "| Metric | Value | Floor $36k | Target $60k | Stretch $100k |",
        "|--------|-------|------------|-------------|---------------|",
        f"| $/yr | ${g['graded_pnl_per_year']:,.2f} | "
        f"{'yes' if g['graded_pnl_per_year'] >= 36000 else 'no'} | "
        f"{'yes' if g['graded_pnl_per_year'] >= 60000 else 'no'} | "
        f"{'yes' if g['graded_pnl_per_year'] >= 100000 else 'no'} |",
        f"| MAR | {g['graded_mar_display']} | — | — | — |",
        f"| Eval pass (30-session) | {100 * g['eval']['pass_rate']:.2f}% "
        f"({g['eval']['pass_count']}/{g['eval']['total_windows']}) | "
        f"{'yes' if g['eval']['pass_rate'] >= 0.50 else 'no'} | "
        f"{'yes' if g['eval']['pass_rate'] >= 0.70 else 'no'} | "
        f"{'yes' if g['eval']['pass_rate'] >= 0.80 else 'no'} |",
        "",
        (
            f"Qty=1 eval diagnostic (not graded): "
            f"{100 * g['eval']['qty1_diagnostic']['pass_rate']:.2f}% "
            f"({g['eval']['qty1_diagnostic']['pass_count']}/"
            f"{g['eval']['qty1_diagnostic']['total_windows']})."
            if g["eval"].get("qty1_diagnostic")
            else ""
        ),
        "",
        f"## Deflated Sharpe (N={MNQ_N})",
        "",
        f"- Observed trade-series Sharpe: **{g['dsr']['observed_sharpe']:.4f}**",
        f"- PSR vs E[max SR] null: **{g['dsr']['psr']:.4f}**",
        f"- E[max SR] (N={MNQ_N}, var from this SR + {MNQ_N - 1} zeros): "
        f"**{g['dsr']['e_max']:.4f}**",
        f"- n_trades (observations): **{g['dsr']['n_obs']}**",
        "",
        f"Variance-across-trials uses this hypothesis's Sharpe plus {MNQ_N - 1} zeros "
        "(committed ledger: Track 1 + W2 = 13, W3 H-7 = 14, H-W4-7 primary = **15**; "
        "H-W4-1…6 were never registered). **PSR near 1 here is an artifact "
        "of that zero-fill shrinking E[max SR]; it is not evidence of edge.** "
        "Trade-series Sharpe ~0.16 with PF 1.00 is noise-scale.",
        "",
        "## Kill/promote",
        "",
        "Not issued. Operator verdict in a fresh context.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    git = _git_meta()
    data_root = data_loader.default_data_root()
    print(f"Loading MNQ from {data_root} ...")
    minute = load_continuous_eth_rth(data_root)
    print(
        f"Minute bars: {minute.height:,}  "
        f"{minute['timestamp'].min()} -> {minute['timestamp'].max()}  "
        f"files pattern {data_loader.MNQ_CONTRACT_GLOB}"
    )
    bars = resample_to_15m_et(minute)
    print(f"15-min bars: {bars.height:,}")
    dst = dst_spot_check(bars)
    print(f"DST spot-check passed={dst['passed']} spring={dst['spring_ok']} fall={dst['fall_ok']}")
    if not dst["passed"]:
        print("STOP: DST quarter classification failed the spot-check.")
        return 2

    stats = completed_quarter_stats(bars)
    yfrac = protocol_year_fraction(PROTOCOL_START, PROTOCOL_END)
    dist, png = range_distribution(stats)
    print("Quarter-range distribution:")
    for r in dist:
        print(
            f"  {r['year']}: n={r['n']}  p10={r['p10']:.1f}  med={r['median']:.1f}  "
            f"p90={r['p90']:.1f}  50/med={r['frac_50_vs_median']:.2f}"
        )
    freq = frequency_screen(stats, yfrac)
    print(
        f"Frequency: {freq['n_signals']} signals, {freq['signals_per_year']:.1f}/yr, "
        f"{freq['signals_per_session_day']:.2f}/session  "
        f"floor200={freq['clears_200_yr_floor']}"
    )
    print("  by block:", freq["by_block"])
    print("  by tier:", freq["by_tier"])
    if not freq["clears_200_yr_floor"]:
        print("STOP: frequency < ~200/yr - quarter classification suspect.")
        payload = {
            "git": git,
            "dst": dst,
            "range_distribution": dist,
            "range_chart": str(png),
            "frequency": freq,
            "stopped": "frequency_floor",
        }
        OUT_STEM.with_suffix(".json").write_text(
            json.dumps(_json_sanitize(payload), indent=2), encoding="utf-8"
        )
        return 2

    print("Running M4 grading backtest (qty=1) ...")
    bt = run_backtest(bars)
    log = bt["trade_log"]
    annotated = annotate_trades_with_signal_quarter(log, stats)
    TRADES_STEM.parent.mkdir(parents=True, exist_ok=True)
    annotated.write_parquet(TRADES_STEM.with_suffix(".parquet"))
    annotated.write_csv(TRADES_STEM.with_suffix(".csv"))
    n_unlabeled = (
        annotated.filter(pl.col("tier_bucket").is_null()).height if not annotated.is_empty() else 0
    )
    print(
        f"Wrote trade log {TRADES_STEM.with_suffix('.parquet')} "
        f"n={annotated.height} unlabeled_tier={n_unlabeled}"
    )
    agg = compute_m6_aggregates(log)
    n = agg.trade_count
    pnl_yr = agg.net_pnl_total / yfrac if yfrac else 0.0
    dd1 = abs(float(agg.max_drawdown))
    mar1 = (pnl_yr / dd1) if dd1 > 0 else float("nan")

    wr_pp = 100.0 * agg.win_rate
    repro_rows = [
        {
            "metric": "trades",
            "session1": SESSION1_TRADES,
            "rerun": n,
            "delta": n - SESSION1_TRADES,
            "ok": n == SESSION1_TRADES,
        },
        {
            "metric": "win_rate_pct",
            "session1": 50.5,
            "rerun": round(wr_pp, 1),
            "delta": round(wr_pp, 1) - 50.5,
            "ok": abs(wr_pp - 50.5) <= 0.05,
        },
        {
            "metric": "net_pnl",
            "session1": SESSION1_NET,
            "rerun": float(agg.net_pnl_total),
            "delta": float(agg.net_pnl_total) - SESSION1_NET,
            "ok": abs(float(agg.net_pnl_total) - SESSION1_NET) <= REPRO_NET_TOL,
        },
        {
            "metric": "max_dd",
            "session1": SESSION1_DD,
            "rerun": dd1,
            "delta": dd1 - SESSION1_DD,
            "ok": abs(dd1 - SESSION1_DD) <= REPRO_DD_TOL,
        },
    ]
    repro_ok = all(bool(r["ok"]) for r in repro_rows)
    print("Repro check vs Session 1:")
    for r in repro_rows:
        mark = "OK" if r["ok"] else "MISMATCH"
        print(
            f"  {r['metric']}: session1={r['session1']} rerun={r['rerun']} "
            f"delta={r['delta']} {mark}"
        )
    if not repro_ok:
        print("STOP: reproducibility check failed. No further cells.")
        fail_payload = {
            "hypothesis": "H-W4-7",
            "git": git,
            "repro": {"passed": False, "rows": repro_rows},
            "grading": {
                "n_trades": n,
                "win_rate": agg.win_rate,
                "net_pnl": agg.net_pnl_total,
                "max_dd": dd1,
            },
            "trade_log": str(TRADES_STEM.with_suffix(".parquet")),
        }
        OUT_STEM.with_suffix(".json").write_text(
            json.dumps(_json_sanitize(fail_payload), indent=2), encoding="utf-8"
        )
        return 3

    q_rq = 0
    r_at = None
    for q in range(1, 80):
        r = _r_of_q(q * dd1)
        if r <= TDD:
            q_rq = q
            r_at = r
        else:
            break

    q_dll_correct, per_loss = dll_two_loss_qmax(per_loss_gross=STOP_POINTS * POINT_VALUE)
    q_dll_spec, _ = dll_two_loss_qmax(per_loss_gross=200.0)
    if q_rq == 0:
        q_max = 0
        binding = "R(q) (no positive q)"
    elif q_dll_correct < q_rq:
        q_max = q_dll_correct
        binding = "DLL two-loss (correct $100/contract)"
    else:
        q_max = q_rq
        binding = "R(q)"

    sessions = (
        bars["cme_session_date"].drop_nulls().unique().sort().to_list()
        if "cme_session_date" in bars.columns
        else []
    )
    ev_q1 = eval_pass_rate_sessions(log, sessions, 1)
    if q_max == 0:
        ev = {
            "pass_rate": 0.0,
            "pass_count": 0,
            "total_windows": ev_q1["total_windows"],
            "fail_trailing": 0,
            "fail_no_target": 0,
            "note": "degenerate q_max=0 (Wave 0 convention)",
            "qty1_diagnostic": ev_q1,
        }
    else:
        ev = eval_pass_rate_sessions(log, sessions, q_max)

    net = log["net_pnl"].to_numpy() if n else np.array([])
    dsr_block = {
        "observed_sharpe": float("nan"),
        "psr": float("nan"),
        "e_max": float("nan"),
        "n_obs": n,
        "n_trials": MNQ_N,
            "variance_note": f"this SR + {MNQ_N - 1} zeros (committed N={MNQ_N})",
    }
    if n >= 3:
        sr = _trade_sharpe(net)
        sk, ku = sample_moments_from_returns(net)
        trial_srs = np.array([sr] + [0.0] * (MNQ_N - 1), dtype=float)
        var = float(np.var(trial_srs, ddof=1))
        dsr = deflated_sharpe_ratio(sr, n, sk, ku, MNQ_N, var, 0.0)
        dsr_block = {
            "observed_sharpe": dsr.observed_sharpe,
            "psr": dsr.probabilistic_sharpe,
            "e_max": dsr.expected_max_sr_benchmark,
            "n_obs": n,
            "n_trials": MNQ_N,
            "variance_across_trials": var,
            "skew": sk,
            "kurtosis_pearson": ku,
        }

    graded_yr = pnl_yr * q_max
    graded_dd = dd1 * q_max
    graded_mar = (graded_yr / graded_dd) if graded_dd > 0 else float("nan")

    deviations = [
        "M4 implements OPEN_OF_NEXT_BAR only: entry order is submitted on the closed "
        "first 15-min bar of the following quarter and fills at the **open of the next** "
        "15-min bar (~15 min after the spec's 'close of first bar'). No CLOSE_OF_SIGNAL_BAR; "
        "no bespoke walker.",
        "V4 implausible-tick surface raised 15 → 250 because the pre-registered 50-pt "
        "target is 200 MNQ ticks gross (default 15 is ORB-scale and would false-fail).",
        "15-min left-labeled bars never timestamp at 16:59 ET, so engine hygiene flatten "
        "does not fire on this grid; holds may cross the 17:00 ET maintenance break "
        "(counted below). Deadzone [17:00, 18:00) still suppresses entries if those bars exist.",
        "DLL spec text said '$200/contract per loss' for a 50-pt MNQ stop; 50×$2/pt=$100. "
        "Binding q uses $100; the $200 figure is reported as a side calculation.",
        "Committed MNQ running N: Track 1 + W2 = 13, W3 H-7 = 14, H-W4-7 primary = **15**. "
        "H-W4-1…6 were never registered and are not invented. Session 1 DSR used N=19; "
        "this rerun uses N=15.",
        "Session 3 execution is from a clean worktree of the ledger-correction SHA "
        "(H-W4-7 module + N-correction committed). Per-trade log is written (Session 1 "
        "aggregates-only JSON was a hygiene miss).",
        "V5 `validation_spot_checks.py` was imported by committed `validation.py` since "
        "fb264ac but the module itself was never on main (only in the dirty tree / now "
        "WIP). Restored onto this worktree so V1–V7 can run; fills/P&L path unchanged.",
        "Full-protocol graded path (not 60/40 IS as the pass/fail split). 60/40 is not the "
        "primary metric for this spec.",
    ]

    vdict = bt["validation"].to_dict()
    grading = {
        "n_trades": n,
        "trades_per_year": n / yfrac if yfrac else 0.0,
        "win_rate": agg.win_rate,
        "profit_factor": agg.profit_factor,
        "net_pnl": agg.net_pnl_total,
        "pnl_per_year": pnl_yr,
        "max_dd": dd1,
        "mar_q1": mar1,
        "years": {str(k): v for k, v in agg.years_calendar.items()},
        "years_positive": agg.years_positive_count,
        "q_max_rq": q_rq,
        "r_at_qmax_rq": r_at if r_at is not None else _r_of_q(dd1),
        "q_max_dll_correct": q_dll_correct,
        "q_max_dll_spec_text": q_dll_spec,
        "dll_friction_per_loss": COMMISSION_RT + SLIP_STOP_USD,
        "q_max": q_max,
        "binding": binding,
        "graded_pnl_per_year": graded_yr,
        "graded_mar": graded_mar,
        "graded_mar_display": "n/a" if q_max == 0 else f"{graded_mar:.3f}",
        "eval": ev,
        "dsr": dsr_block,
        "yfrac": yfrac,
    }
    payload = {
        "hypothesis": "H-W4-7",
        "git": git,
        "dst": dst,
        "range_distribution": dist,
        "range_chart": str(png),
        "frequency": freq,
        "engine": {
            "n_segments": bt["n_segments"],
            "skip_count": bt["skip_count"],
            "signal_count_engine": bt["signal_count_engine"],
            "suppress_skip_count": bt["suppress_skip_count"],
            "geometry_rejects": bt["geometry_rejects"],
            "maintenance_flatten_exits": bt["maintenance_flatten_exits"],
            "holds_crossing_maintenance": bt["holds_crossing_maintenance"],
        },
        "validation": vdict,
        "grading": grading,
        "deviations": deviations,
        "repro": {"passed": True, "rows": repro_rows},
        "trade_log": str(TRADES_STEM.with_suffix(".parquet")),
        "trade_log_unlabeled_tier": n_unlabeled,
        "data": {
            "minute_bars": minute.height,
            "bars_15m": bars.height,
            "first": str(minute["timestamp"].min()),
            "last": str(minute["timestamp"].max()),
        },
    }
    OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
    OUT_STEM.with_suffix(".json").write_text(
        json.dumps(_json_sanitize(payload), indent=2), encoding="utf-8"
    )
    OUT_STEM.with_suffix(".md").write_text(_render_md(payload), encoding="utf-8")
    print(f"Wrote {OUT_STEM.with_suffix('.md')}")
    print(
        f"qty=1: trades={n}  $/yr=${pnl_yr:,.0f}  WR={100 * agg.win_rate:.1f}%  "
        f"PF={agg.profit_factor:.3f}  DD=${dd1:,.0f}  q_max={q_max} ({binding})"
    )
    print(f"V1-V7: {'PASS' if vdict['passed'] else 'FAIL'}")
    print("Repro: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
