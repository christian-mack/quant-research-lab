#!/usr/bin/env python3
"""H-W4-7 Session 3: diagnostic from primary trade log + sensitivity cells A-C.

Does not issue a kill/promote verdict. Pulse criterion is pre-specified:
qty=1 net PF >= 1.10 AND positive in >= 4 of 7 calendar years.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))
if str(_REPO / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO / "scripts"))

from quant_research.backtest.m6_metrics import compute_m6_aggregates, protocol_year_fraction
from quant_research.data import data_loader
from quant_research.modules.quarter_continuation import (
    QUARTER_BLOCKS,
    QuarterContinuationStrategy,
    annotate_trades_with_signal_quarter,
    completed_quarter_stats,
    resample_to_15m_et,
)
from quant_research.statistics.deflated_sharpe import (
    deflated_sharpe_ratio,
    sample_moments_from_returns,
)
from quant_research.statistics.trade_report import _trade_sharpe

from run_hw4_7_quarter_continuation import (
    MNQ_N,
    POINT_VALUE,
    PROTOCOL_END,
    PROTOCOL_START,
    STOP_POINTS,
    TDD,
    _git_meta,
    _json_sanitize,
    _r_of_q,
    dll_two_loss_qmax,
    dst_spot_check,
    eval_pass_rate_sessions,
    load_continuous_eth_rth,
    run_backtest,
)

OUT = _REPO / "notebooks" / "validation" / "2026-08-18_hw4_7_session3"
PRIMARY_TRADES = _REPO / "notebooks" / "validation" / "2026-08-18_hw4_7_primary_trades.parquet"
TIERS = ("ge_0.75", "0.50_to_0.75", "0.25_to_0.50", "le_0.25")
PULSE_PF = 1.10
PULSE_YEARS = 4


def _metrics(df: pl.DataFrame) -> dict[str, object]:
    n = df.height
    if n == 0:
        return {"n": 0, "win_rate": None, "profit_factor": None, "net_pnl": 0.0}
    pnls = df["net_pnl"].to_list()
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gp = float(sum(wins))
    gl = float(sum(losses))
    if gl == 0.0:
        pf: float | None = math.inf if gp > 0 else 0.0
    else:
        pf = gp / abs(gl)
    return {
        "n": n,
        "win_rate": len(wins) / n,
        "profit_factor": pf,
        "net_pnl": float(sum(pnls)),
    }


def diagnostic_from_primary(log: pl.DataFrame) -> dict[str, object]:
    by_tier = {}
    for t in TIERS:
        by_tier[t] = _metrics(log.filter(pl.col("tier_bucket") == t))
    by_block = {}
    for b in QUARTER_BLOCKS:
        by_block[b] = _metrics(log.filter(pl.col("quarter_block") == b))
    cross: dict[str, dict[str, dict[str, object]]] = {}
    for t in TIERS:
        cross[t] = {}
        for b in QUARTER_BLOCKS:
            cross[t][b] = _metrics(
                log.filter((pl.col("tier_bucket") == t) & (pl.col("quarter_block") == b))
            )
    return {"by_tier": by_tier, "by_block": by_block, "cross": cross}


def _fmt_pf(x: object) -> str:
    if x is None:
        return "—"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return f"{float(x):.3f}"


def _fmt_wr(x: object) -> str:
    if x is None:
        return "—"
    return f"{100 * float(x):.1f}%"


def _dual_touch_pct(vdict: dict[str, object]) -> float | None:
    for c in vdict.get("checks", []):
        if c.get("check_id") == "V6":
            details = c.get("details") or {}
            rate = details.get("dual_touch_rate")
            return None if rate is None else float(rate)
    return None


def _grade_cell(
    *,
    name: str,
    bars: pl.DataFrame,
    stats: pl.DataFrame,
    factory,
    yfrac: float,
    stem: Path,
) -> dict[str, object]:
    bt = run_backtest(bars, strategy_factory=factory)
    log = bt["trade_log"]
    annotated = annotate_trades_with_signal_quarter(log, stats)
    stem.parent.mkdir(parents=True, exist_ok=True)
    annotated.write_parquet(stem.with_suffix(".parquet"))
    annotated.write_csv(stem.with_suffix(".csv"))
    agg = compute_m6_aggregates(log)
    n = agg.trade_count
    pnl_yr = agg.net_pnl_total / yfrac if yfrac else 0.0
    dd1 = abs(float(agg.max_drawdown))
    vdict = bt["validation"].to_dict()
    years = {str(k): v for k, v in agg.years_calendar.items()}
    n_pos = sum(1 for v in years.values() if v > 0)
    pulse = (agg.profit_factor >= PULSE_PF) and (n_pos >= PULSE_YEARS)
    out = {
        "cell": name,
        "n_trades": n,
        "trades_per_year": n / yfrac if yfrac else 0.0,
        "win_rate": agg.win_rate,
        "profit_factor": agg.profit_factor,
        "net_pnl": agg.net_pnl_total,
        "pnl_per_year": pnl_yr,
        "max_dd": dd1,
        "years": years,
        "years_positive": n_pos,
        "skip_count": bt["skip_count"],
        "signal_count_engine": bt["signal_count_engine"],
        "holds_crossing_maintenance": bt["holds_crossing_maintenance"],
        "maintenance_flatten_exits": bt["maintenance_flatten_exits"],
        "dual_touch_rate": _dual_touch_pct(vdict),
        "validation_passed": vdict["passed"],
        "validation": vdict,
        "pulse_pass": pulse,
        "trade_log": str(stem.with_suffix(".parquet")),
    }
    print(
        f"{name}: trades={n} ({n / yfrac:.1f}/yr) WR={100 * agg.win_rate:.1f}% "
        f"PF={agg.profit_factor:.3f} $/yr=${pnl_yr:,.0f} DD=${dd1:,.0f} "
        f"years+={n_pos}/7 skips={bt['skip_count']} "
        f"17:00-cross={bt['holds_crossing_maintenance']} "
        f"dual-touch={out['dual_touch_rate']} pulse={pulse}"
    )
    return out


def _full_harness(
    cell: dict[str, object], log: pl.DataFrame, bars: pl.DataFrame
) -> dict[str, object]:
    """V1-V7 already on cell; add year-by-year, DD(1), q_max, eval, DSR at N=15."""
    yfrac = protocol_year_fraction(PROTOCOL_START, PROTOCOL_END)
    dd1 = float(cell["max_dd"])
    q_rq = 0
    r_at = None
    for q in range(1, 80):
        r = _r_of_q(q * dd1)
        if r <= TDD:
            q_rq = q
            r_at = r
        else:
            break
    q_dll, per_loss = dll_two_loss_qmax(per_loss_gross=STOP_POINTS * POINT_VALUE)
    if q_rq == 0:
        q_max = 0
        binding = "R(q) (no positive q)"
    elif q_dll < q_rq:
        q_max = q_dll
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
            "note": "degenerate q_max=0",
            "qty1_diagnostic": ev_q1,
        }
    else:
        ev = eval_pass_rate_sessions(log, sessions, q_max)
    n = int(cell["n_trades"])
    net = log["net_pnl"].to_numpy() if n else np.array([])
    dsr_block: dict[str, object] = {"n_obs": n, "n_trials": MNQ_N}
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
        }
    return {
        "q_max": q_max,
        "binding": binding,
        "q_max_rq": q_rq,
        "r_at_qmax_rq": r_at if r_at is not None else _r_of_q(dd1),
        "q_max_dll": q_dll,
        "dll_per_loss": per_loss,
        "eval": ev,
        "dsr": dsr_block,
        "yfrac": yfrac,
    }


def _render(payload: dict[str, object]) -> str:
    d = payload["diagnostic"]
    lines = [
        "# H-W4-7 Session 3 — remediation, repro, diagnostic, cells A–C",
        "",
        f"**git_sha:** `{payload['git']['git_sha']}`  ",
        f"**git_dirty:** `{payload['git']['git_dirty']}`  ",
        f"**Clone base:** `{payload['clone_base_sha']}`  ",
        f"**WIP backlog:** `{payload['wip_branch']}`  ",
        "**Verdict:** not issued this session",
        "",
        "## 1. Remediation",
        "",
        f"- `main` H-W4-7 provenance: `{payload['hw47_sha']}`",
        f"- N-ledger correction: `{payload['clone_base_sha']}` (H-W4-7 primary **N=15**)",
        f"- Wave 0e–1 / ICT parked on `{payload['wip_branch']}`",
        f"- Execution worktree: `{payload['worktree']}`",
        "",
        "## 2. Repro check (primary spec, unchanged)",
        "",
        "| Metric | Session 1 | Rerun | Delta | OK |",
        "|--------|-----------|-------|-------|----|",
    ]
    for r in payload["repro"]["rows"]:
        lines.append(
            f"| {r['metric']} | {r['session1']} | {r['rerun']} | {r['delta']} | "
            f"{'yes' if r['ok'] else 'NO'} |"
        )
    lines += [
        "",
        f"V1–V7: **{'PASS' if payload['primary_v17'] else 'FAIL'}**. "
        f"Primary DSR at N=15 in the primary harness JSON.",
        "",
        "## 3b. Diagnostic (descriptive only — no new cells)",
        "",
        "### By tier",
        "",
        "| Tier | n | WR | PF | Net P&L |",
        "|------|---|----|----|---------|",
    ]
    for t in TIERS:
        m = d["by_tier"][t]
        lines.append(
            f"| {t} | {m['n']} | {_fmt_wr(m['win_rate'])} | {_fmt_pf(m['profit_factor'])} | "
            f"${m['net_pnl']:,.2f} |"
        )
    lines += [
        "",
        "### By quarter block",
        "",
        "| Block | n | WR | PF | Net P&L |",
        "|-------|---|----|----|---------|",
    ]
    for b in QUARTER_BLOCKS:
        m = d["by_block"][b]
        lines.append(
            f"| {b} | {m['n']} | {_fmt_wr(m['win_rate'])} | {_fmt_pf(m['profit_factor'])} | "
            f"${m['net_pnl']:,.2f} |"
        )
    lines += [
        "",
        "### Tier × block (n / net P&L)",
        "",
        "| Tier \\ Block | " + " | ".join(QUARTER_BLOCKS) + " |",
        "|" + "------|" * (len(QUARTER_BLOCKS) + 1),
    ]
    for t in TIERS:
        cells = []
        for b in QUARTER_BLOCKS:
            m = d["cross"][t][b]
            cells.append(f"{m['n']} / ${m['net_pnl']:,.0f}")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## 3c. Sensitivity cells A–C",
        "",
        "Pulse: qty=1 net PF ≥ 1.10 AND +PnL in ≥ 4 of 7 years. Cells do not increment N.",
        "",
        "| Cell | n | /yr | WR | PF | $/yr | Max DD | Y+ | Skips | Dual | 17:00 | Pulse |",
        "|------|---|-----|----|----|------|--------|----|-------|------|-------|-------|",
    ]
    for key in ("A", "B", "C"):
        c = payload["cells"][key]
        dtouch = c["dual_touch_rate"]
        dt_s = "—" if dtouch is None else f"{100 * dtouch:.2f}%"
        lines.append(
            f"| {key} | {c['n_trades']} | {c['trades_per_year']:.1f} | "
            f"{100 * c['win_rate']:.1f}% | {c['profit_factor']:.3f} | "
            f"${c['pnl_per_year']:,.2f} | ${c['max_dd']:,.2f} | "
            f"{c['years_positive']}/7 | {c['skip_count']} | {dt_s} | "
            f"{c['holds_crossing_maintenance']} | "
            f"{'PASS' if c['pulse_pass'] else 'no'} |"
        )
    any_pulse = payload["pulse_any"]
    pulse_line = (
        "at least one cell passed"
        if any_pulse
        else "no cell passed — family dead at fixed-bracket (stop; no R:R / ATR / block subsets)."
    )
    lines += [
        "",
        f"**Pulse criterion:** {pulse_line}",
        "",
        "### Year-by-year net P&L (qty=1)",
        "",
        "| Year | A | B | C |",
        "|------|---|---|---|",
    ]
    years = sorted({y for c in payload["cells"].values() for y in c["years"]})
    for y in years:
        row = [y]
        for key in ("A", "B", "C"):
            pnl = payload["cells"][key]["years"].get(y, 0.0)
            row.append(f"${pnl:,.2f}")
        lines.append("| " + " | ".join(row) + " |")
    if any_pulse:
        lines += ["", "## Pulse-pass harness (no verdict)", ""]
        for key in ("A", "B", "C"):
            if not payload["cells"][key]["pulse_pass"]:
                continue
            h = payload["cells"][key]["harness"]
            lines += [
                f"### Cell {key}",
                "",
                f"- V1–V7: **{'PASS' if payload['cells'][key]['validation_passed'] else 'FAIL'}**",
                f"- DD(1): **${payload['cells'][key]['max_dd']:,.2f}**",
                f"- q_max: **{h['q_max']}** ({h['binding']}); R(q) q={h['q_max_rq']}; "
                f"DLL q={h['q_max_dll']}",
                f"- Eval: {100 * h['eval']['pass_rate']:.2f}%",
                f"- DSR N={MNQ_N}: SR={h['dsr'].get('observed_sharpe')}, PSR={h['dsr'].get('psr')}",
                "",
            ]
    lines += [
        "",
        "## Forced deviations",
        "",
    ]
    for dline in payload["deviations"]:
        lines.append(f"- {dline}")
    lines += [
        "",
        "## Kill/promote",
        "",
        "Not issued.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    git = _git_meta()
    if not PRIMARY_TRADES.exists():
        print(f"STOP: missing primary trade log {PRIMARY_TRADES}")
        return 2
    primary = pl.read_parquet(PRIMARY_TRADES)
    diag = diagnostic_from_primary(primary)
    print("Diagnostic by tier:", diag["by_tier"])

    data_root = data_loader.default_data_root()
    print(f"Loading MNQ from {data_root} ...")
    minute = load_continuous_eth_rth(data_root)
    bars = resample_to_15m_et(minute)
    dst = dst_spot_check(bars)
    if not dst["passed"]:
        print("STOP: DST spot-check failed")
        return 2
    stats = completed_quarter_stats(bars)
    yfrac = protocol_year_fraction(PROTOCOL_START, PROTOCOL_END)

    cells: dict[str, dict[str, object]] = {}
    cells["A"] = _grade_cell(
        name="A",
        bars=bars,
        stats=stats,
        factory=lambda: QuarterContinuationStrategy(
            extreme_tiers_only=True,
            submit_on_completing_quarter_last_bar=True,
        ),
        yfrac=yfrac,
        stem=_REPO / "notebooks" / "validation" / "2026-08-18_hw4_7_cell_a_trades",
    )
    cells["B"] = _grade_cell(
        name="B",
        bars=bars,
        stats=stats,
        factory=lambda: QuarterContinuationStrategy(
            extreme_tiers_only=True,
            submit_on_completing_quarter_last_bar=False,
        ),
        yfrac=yfrac,
        stem=_REPO / "notebooks" / "validation" / "2026-08-18_hw4_7_cell_b_trades",
    )
    cells["C"] = _grade_cell(
        name="C",
        bars=bars,
        stats=stats,
        factory=lambda: QuarterContinuationStrategy(
            extreme_tiers_only=False,
            submit_on_completing_quarter_last_bar=True,
        ),
        yfrac=yfrac,
        stem=_REPO / "notebooks" / "validation" / "2026-08-18_hw4_7_cell_c_trades",
    )
    pulse_any = any(bool(cells[k]["pulse_pass"]) for k in cells)
    if pulse_any:
        for key in cells:
            if cells[key]["pulse_pass"]:
                log = pl.read_parquet(cells[key]["trade_log"])
                cells[key]["harness"] = _full_harness(cells[key], log, bars)

    repro_path = _REPO / "notebooks" / "validation" / "2026-08-18_hw4_7_quarter_continuation.json"
    repro = json.loads(repro_path.read_text(encoding="utf-8")).get("repro", {})
    v17 = json.loads(repro_path.read_text(encoding="utf-8")).get("validation", {}).get("passed")

    payload = {
        "hypothesis": "H-W4-7",
        "session": 3,
        "git": git,
        "clone_base_sha": "efc119e11495666a6e73d4161e2dcab649f7e337",
        "hw47_sha": "1ae71e8ca46fb307e64c160e9f44ae6d22ca4329",
        "wip_branch": "wip/wave0e-ict-backlog",
        "worktree": str(_REPO),
        "repro": repro,
        "primary_v17": v17,
        "diagnostic": diag,
        "cells": cells,
        "pulse_any": pulse_any,
        "dst": dst,
        "deviations": [
            "M4 OPEN_OF_NEXT_BAR only; Cell A/C submit on last bar of completing quarter "
            "(16:45 ET last of 14:00-17:00 fills at next in-session bar, typically 18:00 ET "
            "because 17:00-18:00 is BREAK).",
            "V4 surface 250 ticks (50-pt / 200-tick target).",
            "V5 module `validation_spot_checks.py` restored from WIP — committed validation.py "
            "imported it since fb264ac but the file was never on main.",
            "DSR uses committed N=15. Cells A-C do not increment N.",
            "15-min grid: 16:59 flatten never fires; 17:00-cross holds counted.",
            "Annotation of tier/block is a post-hoc asof join; fills unchanged.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.with_suffix(".json").write_text(
        json.dumps(_json_sanitize(payload), indent=2), encoding="utf-8"
    )
    OUT.with_suffix(".md").write_text(_render(payload), encoding="utf-8")
    print(f"Wrote {OUT.with_suffix('.md')}")
    print(f"pulse_any={pulse_any}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
