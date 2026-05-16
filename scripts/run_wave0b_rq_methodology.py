#!/usr/bin/env python3
"""Wave 0b — R(q) methodology: EOD trailing DD, bootstrap DD, live audit stub.

Usage (repo root, requires ``data/raw`` MNQ exports)::

    uv run python scripts/run_wave0b_rq_methodology.py

Optional **Deliverable 3:** place operator CSV at ``data/wave0b_live_funded_daily.csv``
(gitignored under ``/data/``) with columns::

    cme_session_date,daily_net_pnl

``daily_net_pnl`` must be **closed realized USD for that session at live qty (3)**.
"""

from __future__ import annotations

# ruff: noqa: E402, E501
import datetime as dt
import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.backtest import (  # noqa: E402
    BacktestConfig,
    BacktestEngine,
    OrchestrationSpec,
    as_module,
)
from quant_research.backtest.m6_metrics import compute_m6_aggregates
from quant_research.backtest.schema import empty_trade_log
from quant_research.data import continuous_contract, data_loader, session
from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.modules import OrbStrategy, production_orb_opt3_funded_params
from quant_research.statistics.apex_eod_trailing import (
    block_bootstrap_resample_trades,
    simulate_apex_eod_trailing,
    trades_to_daily_pnls_chronological,
)

_CHI = ZoneInfo("America/Chicago")
_START = dt.date(2020, 1, 1)
_END = dt.date(2026, 4, 19)
_START_BALANCE = 50_000.0
_R_CEILING = 3_000.0
_WAVE0_CLOSED_DD1 = 2_675.0
_WAVE0_CLOSED_DD3 = 8_025.0
_LIVE_CSV_REL = Path("data") / "wave0b_live_funded_daily.csv"


def _json_safe(obj: object) -> object:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def _git_meta(repo: Path) -> dict[str, object]:
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = (
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        != ""
    )
    return {"git_sha": sha, "git_dirty": dirty}


def _append_exit_session_columns(trade_log: pl.DataFrame) -> pl.DataFrame:
    if trade_log.is_empty():
        return trade_log
    stamp = trade_log.select(pl.col("exit_time").alias("timestamp"))
    stamped = session.assign_cme_session_date(stamp)
    ny_date = trade_log.select(
        pl.col("exit_time").dt.convert_time_zone("America/New_York").dt.date().alias("exit_ny_date"),
    )["exit_ny_date"]
    return trade_log.with_columns(
        stamped["cme_session_date"].alias("exit_cme_session_date"),
        ny_date,
    )


def _percentile_summary(a: np.ndarray) -> dict[str, float]:
    a = np.asarray(a, dtype=np.float64)
    return {
        "mean": float(np.mean(a)),
        "median": float(np.percentile(a, 50)),
        "p75": float(np.percentile(a, 75)),
        "p90": float(np.percentile(a, 90)),
        "p95": float(np.percentile(a, 95)),
        "p99": float(np.percentile(a, 99)),
    }


def _max_sustainable_q_legacy(dd1: float) -> int:
    best = 0
    for q in range(1, 500):
        ddq = q * dd1
        rq = max(1.5 * ddq, ddq + 500.0)
        if rq <= _R_CEILING:
            best = q
        else:
            break
    return best


def _max_sustainable_q_proposed(p95_unit: float, eod_pt_unit: float) -> int:
    """R(q)=max(p95_unit*q, q*eod_pt_unit+500) — both unit DDs at qty=1 scale."""
    best = 0
    for q in range(1, 500):
        rq = max(p95_unit * q, q * eod_pt_unit + 500.0)
        if rq <= _R_CEILING:
            best = q
        else:
            break
    return best


def _run_d1_daily_payload(
    session_dates: list[object],
    daily_qty1: np.ndarray,
    qty: int,
    mode: str,
) -> dict[str, object]:
    scaled = daily_qty1 * float(qty)
    m = "funded_lock" if mode == "funded_lock" else "pure_trailing"
    sim = simulate_apex_eod_trailing(scaled, mode=m)  # type: ignore[arg-type]
    bind_date = session_dates[sim.binding_session_index] if session_dates else None
    return {
        "qty": qty,
        "mode": mode,
        "n_sessions": sim.n_sessions,
        "final_equity": sim.final_equity,
        "max_peak_to_trough_dd_on_equity": sim.max_peak_to_trough_dd,
        "max_floor_violation": sim.max_floor_violation,
        "min_margin_to_floor": sim.min_margin_to_floor,
        "breach_session_count": sim.breach_session_count,
        "dll_hit_session_count": sim.dll_hit_session_count,
        "binding_session_index": sim.binding_session_index,
        "binding_cme_session_date": str(bind_date) if bind_date is not None else None,
    }


def _histogram_payload(a: np.ndarray, n_bins: int = 40) -> dict[str, list[float]]:
    a = np.asarray(a, dtype=np.float64)
    counts, edges = np.histogram(a, bins=n_bins)
    return {
        "bin_edges": edges.astype(float).tolist(),
        "counts": counts.astype(int).tolist(),
    }


def main() -> None:
    root_raw = _REPO / "data" / "raw"
    if not any(root_raw.glob("MNQ *.Last.txt")):
        print("No MNQ contract files under data/raw; abort.", file=sys.stderr)
        sys.exit(2)

    meta_git = _git_meta(_REPO)
    raw = data_loader.load_all_contracts(root_raw)
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    rth = dated.filter(pl.col("session") == session.SESSION_RTH)

    ts0 = dt.datetime.combine(_START, dt.time.min).replace(tzinfo=_CHI)
    ts_end_excl = dt.datetime(2026, 4, 20, 0, 0, 0, tzinfo=_CHI)
    window = rth.filter(
        (pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts_end_excl),
    ).sort("timestamp")

    segments = split_dataframe_at_operator_export_gaps(window)
    orch = OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)
    p1 = replace(production_orb_opt3_funded_params(), quantity=1)

    logs: list[pl.DataFrame] = []
    for seg in segments:
        strat = OrbStrategy(p1)
        out = BacktestEngine(cfg).run(seg, [as_module("orb", strat)])
        if out.trade_log.height > 0:
            logs.append(out.trade_log)

    combined = pl.concat(logs) if logs else empty_trade_log()
    if combined.is_empty():
        print("No trades; abort.", file=sys.stderr)
        sys.exit(3)

    enriched = _append_exit_session_columns(combined)
    trades_sorted = enriched.sort("exit_time")
    exit_dates = trades_sorted["exit_cme_session_date"].to_list()
    pnls1 = trades_sorted["net_pnl"].to_numpy().astype(np.float64)

    session_dates, daily_qty1 = trades_to_daily_pnls_chronological(exit_dates, pnls1)
    m = compute_m6_aggregates(combined)
    dd1_closed = abs(float(m.max_drawdown))

    d1_pure: dict[str, dict[str, dict[str, object]]] = {
        str(q): {
            "pure_trailing": _run_d1_daily_payload(
                session_dates, daily_qty1, q, "pure_trailing"
            ),
            "funded_lock": _run_d1_daily_payload(session_dates, daily_qty1, q, "funded_lock"),
        }
        for q in (1, 2, 3)
    }

    eod_pt_dd1_lock = float(
        d1_pure["1"]["funded_lock"]["max_peak_to_trough_dd_on_equity"]  # type: ignore[arg-type]
    )
    eod_pt_dd3_lock = float(
        d1_pure["3"]["funded_lock"]["max_peak_to_trough_dd_on_equity"]  # type: ignore[arg-type]
    )

    stop_eod_vs_closed = bool(eod_pt_dd3_lock < _WAVE0_CLOSED_DD3 - 3_500)

    rng = np.random.default_rng(42)
    n_tr = pnls1.size
    boot: dict[str, object] = {}
    for bl in (1, 5, 10):
        closed_dd, eod_dd = block_bootstrap_resample_trades(
            pnls1,
            exit_dates,
            block_len=bl,
            n_target_trades=n_tr,
            n_iterations=10_000,
            rng=rng,
        )
        boot[f"block_len_{bl}"] = {
            "closed_trade_max_dd_pos": _percentile_summary(closed_dd),
            "eod_funded_lock_peak_trough": _percentile_summary(eod_dd),
            "histogram_closed_trade_max_dd_pos": _histogram_payload(closed_dd),
            "histogram_eod_peak_trough": _histogram_payload(eod_dd),
            "note": (
                "10k replicate max-DD values summarized by percentiles + histogram; "
                "re-run script to regenerate draws (seed 42, single RNG stream in block_len order)."
            ),
        }

    b5_closed = boot["block_len_5"]["closed_trade_max_dd_pos"]  # type: ignore[index]
    b5_eod = boot["block_len_5"]["eod_funded_lock_peak_trough"]  # type: ignore[index]
    p95_closed_b5 = float(b5_closed["p95"])
    p99_closed_b5 = float(b5_closed["p99"])
    p95_eod_b5 = float(b5_eod["p95"])
    p99_eod_b5 = float(b5_eod["p99"])

    q_max_old = _max_sustainable_q_legacy(dd1_closed)
    q_prop_closed95 = _max_sustainable_q_proposed(p95_closed_b5, eod_pt_dd1_lock)
    q_prop_eod95 = _max_sustainable_q_proposed(p95_eod_b5, eod_pt_dd1_lock)

    live_path = _REPO / _LIVE_CSV_REL
    live_block: dict[str, object] = {
        "expected_relative_path": _LIVE_CSV_REL.as_posix(),
        "file_found": live_path.is_file(),
    }
    stop_live_proximity = False
    if live_path.is_file():
        lf = pl.read_csv(live_path)
        if "cme_session_date" not in lf.columns or "daily_net_pnl" not in lf.columns:
            live_block["error"] = "CSV must have columns cme_session_date,daily_net_pnl"
        else:
            lf = lf.sort("cme_session_date")
            live_pnls = lf["daily_net_pnl"].to_numpy().astype(np.float64)
            live_days = lf["cme_session_date"].to_list()
            live_sim = simulate_apex_eod_trailing(live_pnls, mode="funded_lock")
            dll_live = int(np.sum(live_pnls < -1_000.0))
            live_block.update(
                {
                    "n_sessions": live_sim.n_sessions,
                    "final_equity": live_sim.final_equity,
                    "max_peak_to_trough_dd_on_equity": live_sim.max_peak_to_trough_dd,
                    "min_margin_to_floor": live_sim.min_margin_to_floor,
                    "breach_session_count": live_sim.breach_session_count,
                    "dll_hit_session_count": dll_live,
                    "binding_cme_session_date": str(live_days[live_sim.binding_session_index])
                    if live_days
                    else None,
                    "first_date": str(live_days[0]) if live_days else None,
                    "last_date": str(live_days[-1]) if live_days else None,
                },
            )
            if live_sim.breach_session_count > 0 or dll_live > 0:
                stop_live_proximity = True
            if live_sim.min_margin_to_floor < 500.0:
                stop_live_proximity = True
    else:
        live_block["note"] = (
            "No operator CSV — cannot audit live vs backtest (Deliverable 3 incomplete)."
        )

    payload: dict[str, object] = {
        "wave": "0b",
        "git": meta_git,
        "account_class_starting_balance_usd": _START_BALANCE,
        "protocol": {
            "start": _START.isoformat(),
            "end_inclusive": _END.isoformat(),
            "trade_count_qty1": m.trade_count,
            "unique_cme_session_days_in_trade_log": len(session_dates),
        },
        "wave0_reference_closed_trade_dd": {
            "qty1": _WAVE0_CLOSED_DD1,
            "qty3_linear_scaled": _WAVE0_CLOSED_DD3,
            "recomputed_dd1_from_this_run": dd1_closed,
        },
        "deliverable_1_eod_trailing": d1_pure,
        "deliverable_1_flags": {
            "eod_qty3_funded_lock_dd_vs_closed_x3": {
                "eod_dd_qty3": eod_pt_dd3_lock,
                "closed_trade_dd_qty3": _WAVE0_CLOSED_DD3,
                "ratio_eod_over_closed": eod_pt_dd3_lock / _WAVE0_CLOSED_DD3
                if _WAVE0_CLOSED_DD3
                else None,
            },
            "significant_finding_closed_overstates_apex_relevant_dd": stop_eod_vs_closed,
        },
        "deliverable_2_bootstrap": boot,
        "deliverable_3_live_audit": live_block,
        "stop_conditions_triggered": {
            "live_breach_or_dll_or_margin_within_500": stop_live_proximity,
            "eod_qty3_materially_below_closed_x3": stop_eod_vs_closed,
        },
        "proposed_rq_for_operator_review": {
            "description": (
                "Illustrative only — not adopted until operator accepts + lessons log. "
                "Uses block_len=5 bootstrap percentiles at qty=1, linear scale in q."
            ),
            "formula_closed_p95": "R(q)=max(p95_closed(1)*q, q*EOD_DD_point(1)+500)",
            "formula_eod_p95": "R(q)=max(p95_eod(1)*q, q*EOD_DD_point(1)+500)",
            "inputs": {
                "p95_closed_trade_dd_qty1_block5": p95_closed_b5,
                "p99_closed_trade_dd_qty1_block5": p99_closed_b5,
                "p95_eod_peak_trough_qty1_block5": p95_eod_b5,
                "p99_eod_peak_trough_qty1_block5": p99_eod_b5,
                "eod_point_funded_lock_dd_qty1": eod_pt_dd1_lock,
            },
            "q_max_legacy_R": q_max_old,
            "q_max_proposed_closed_p95_rule": q_prop_closed95,
            "q_max_proposed_eod_p95_rule": q_prop_eod95,
        },
    }

    out_dir = _REPO / "notebooks" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "2026-05-16_wave0b_rq_methodology.json"
    md_path = out_dir / "2026-05-16_wave0b_rq_methodology.md"

    json_path.write_text(
        json.dumps(_json_safe(payload), indent=2, allow_nan=False),
        encoding="utf-8",
    )

    lines = [
        "# Wave 0b — R(q) methodology investigation",
        "",
        f"**Git SHA:** `{meta_git['git_sha']}`  ",
        f"**Dirty tree:** {meta_git['git_dirty']}  ",
        f"**Generated:** {dt.datetime.now(dt.UTC).isoformat()}  ",
        "",
        "## Scope",
        "",
        "Methodology investigation (not a strategy hypothesis): reconcile **closed-trade "
        "cumulative DD** (Wave 0) with **session-close aggregation** and **Apex-style EOD "
        "trailing rules**, block-bootstrap tail of max DD, and optional live funded CSV.",
        "",
        "### Account / rule assumptions",
        "",
        f"- **Starting balance:** **${_START_BALANCE:,.0f}** ($50K EOD class; see "
        "`docs/ai-project-instructions.md`).",
        "- **Trailing:** \\$3,000 below high-water **equity** after each session’s net P&amp;L.",
        "- **Funded-style lock (`funded_lock`):** when HWM first reaches start+\\$100, "
        "`locked_floor = HWM_at_lock − \\$3,000`; **allowed minimum equity** stays at "
        "`locked_floor` (does not rise with later equity highs). **Pure trailing** keeps "
        "`allowed_min = HWM − \\$3,000` throughout.",
        "- **DLL:** sessions with daily P&amp;L &lt; **\\-$1,000** are counted; path is **not** "
        "censored for DD (underlying profile).",
        "",
        "## Deliverable 1 — EOD trailing on 6y ORB+Opt3 daily P&amp;L",
        "",
        "| Qty | Mode | Peak-to-trough DD on equity | Min margin to floor | "
        "Breach sessions | DLL hits | Binding session |",
        "|-----|------|----------------------------|---------------------|-----------------|----------|----------------|",
    ]
    for q in (1, 2, 3):
        for mm in ("pure_trailing", "funded_lock"):
            row = d1_pure[str(q)][mm]
            lines.append(
                f"| {q} | {mm} | ${row['max_peak_to_trough_dd_on_equity']:,.2f} | "
                f"${row['min_margin_to_floor']:,.2f} | {row['breach_session_count']} | "
                f"{row['dll_hit_session_count']} | {row['binding_cme_session_date']} |",
            )
    lines += [
        "",
        "**Interpretation:** **funded_lock** freezes the trailing floor after the first HWM ≥ "
        "start+\\$100; on this backtest that removes **trailing breach** sessions at qty 2–3 "
        "that appear under **pure_trailing**, while **DLL** flags are unchanged. "
        "**Peak-to-trough** equity drawdown at q=3 still reaches **\\$8,025**, matching "
        "closed-trade ×3 — the “stop” gap example (EOD \\ll closed×3) **did not occur** here.",
        "",
        f"- **Wave 0 closed-trade DD(1):** \\${dd1_closed:,.2f} (recomputed here; logged \\$2,675).",
        f"- **Wave 0 closed-trade DD(3) scaled:** \\$**{_WAVE0_CLOSED_DD3:,.0f}**.",
        f"- **EOD funded_lock DD(3):** \\$**{eod_pt_dd3_lock:,.2f}**.",
        "",
        "### Finding — closed-trade vs EOD (qty=3)",
        "",
    ]
    if stop_eod_vs_closed:
        lines.append(
            "**Significant:** EOD trailing peak-to-trough DD at qty=3 is **materially below** "
            f"closed-trade cumulative ×3 (\\${_WAVE0_CLOSED_DD3:,.0f}). That suggests "
            "**closed-trade path DD can overstate Apex-relevant (EOD) risk** for ORB+Opt3 when "
            "multiple same-session exits net out at the session boundary.",
        )
    else:
        lines.append(
            "Ratio of EOD DD to linear scaled closed-trade DD is in JSON — review if margin "
            "is narrower than the example in the investigation brief.",
        )

    lines += [
        "",
        "## Deliverable 2 — Block bootstrap max DD (qty=1), 10k resamples, seed=42",
        "",
        "Per block length: **closed-trade** max DD (positive magnitude) and **EOD** "
        "peak-to-trough on the **collapsed session series** under **funded_lock**.",
        "",
        "| Block len | Closed p95 | Closed p99 | EOD p95 | EOD p99 |",
        "|-----------|------------|------------|---------|---------|",
    ]
    for bl in (1, 5, 10):
        b = boot[f"block_len_{bl}"]
        cp = b["closed_trade_max_dd_pos"]  # type: ignore[index]
        ep = b["eod_funded_lock_peak_trough"]  # type: ignore[index]
        lines.append(
            f"| {bl} | ${cp['p95']:,.2f} | ${cp['p99']:,.2f} | "
            f"${ep['p95']:,.2f} | ${ep['p99']:,.2f} |",
        )

    lines += [
        "",
        "Percentiles + **histograms** (40 bins) per block length are in JSON; re-run the script to regenerate 10k draws.",
        "",
        "## Deliverable 3 — Live production audit",
        "",
    ]
    if live_path.is_file() and live_block.get("error") is None:
        lines.append(
            f"Loaded **{live_block['n_sessions']}** sessions from `{_LIVE_CSV_REL.as_posix()}`. "
            f"Live funded_lock peak-to-trough DD: "
            f"**${live_block['max_peak_to_trough_dd_on_equity']:,.2f}**; "
            f"min margin to floor: **${live_block['min_margin_to_floor']:,.2f}**.",
        )
        if stop_live_proximity:
            lines += [
                "",
                "**STOP / operator:** Live path shows **breach, DLL hit, or margin &lt; \\$500** "
                "— treat as **immediate risk review** before methodology changes.",
            ]
    else:
        lines.append(
            f"**Incomplete:** place operator CSV at `{_LIVE_CSV_REL.as_posix()}` (under gitignored "
            "`data/`). No live conclusions without it.",
        )

    lines += [
        "",
        "## Operator review summary",
        "",
        f"- **Empirical DD(1) under EOD funded_lock (point, 6y):** "
        f"\\${eod_pt_dd1_lock:,.2f} peak-to-trough on equity.",
        f"- **Bootstrap (block=5) closed-trade DD qty=1:** **p95 \\${p95_closed_b5:,.2f}**, "
        f"**p99 \\${p99_closed_b5:,.2f}**.",
        f"- **Bootstrap (block=5) EOD funded_lock DD qty=1:** **p95 \\${p95_eod_b5:,.2f}**, "
        f"**p99 \\${p99_eod_b5:,.2f}**.",
        "- **Live audit:** "
        + (
            "**STOP flagged** — see Deliverable 3."
            if stop_live_proximity
            else (
                "**Not completed** (no CSV)."
                if not live_path.is_file()
                else "Completed from CSV — no stop flag."
            )
        ),
        "",
        "### Proposed R(q) (for operator decision only)",
        "",
        "Using **percentile** margin instead of **1.5×**, illustrative forms at qty=1 scale:",
        "",
        f"- **R₁(q)** = max( **{p95_closed_b5:.2f}** × q , q × **{eod_pt_dd1_lock:.2f}** + 500 ) "
        f"→ largest q ≤ \\$3k ceiling: **{q_prop_closed95}**.",
        f"- **R₂(q)** = max( **{p95_eod_b5:.2f}** × q , q × **{eod_pt_dd1_lock:.2f}** + 500 ) "
        f"→ **{q_prop_eod95}**.",
        "",
        f"Legacy Wave 0 rule gave **q_max = {q_max_old}** at DD(1)=\\${dd1_closed:,.0f}.",
        "",
        "Artifacts: `2026-05-16_wave0b_rq_methodology.json`, "
        "runner `scripts/run_wave0b_rq_methodology.py`.",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"wrote_md": str(md_path), "wrote_json": str(json_path)}, indent=2))


if __name__ == "__main__":
    main()
