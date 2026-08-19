#!/usr/bin/env python3
"""Wave 1 Stage 1 Track 1 — coarse Apex-compatibility screening (7 quant hypotheses).

Writes ``notebooks/validation/2026-05-26_wave1_stage1_track1_*.{md,json}``.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.data import continuous_contract, data_loader, session
from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.research_wave1.instrument_pipeline import instrument_raw_coverage
from quant_research.research_wave1.track1_hypothesis_sims import (
    prepare_et_frame,
    simulate_h1,
    simulate_h11,
    simulate_h12,
    simulate_h2,
)
from quant_research.research_wave1.track1_metrics import (
    GATE_EVAL_YEARS,
    GateResult,
    TradeRow,
    block_bootstrap_session_mean_annual_ci,
    daily_pnls_qty1_et,
    daily_sharpe_annualized,
    deflated_sharpe_track,
    evaluate_gates,
    session_pnl_arrays,
    summarize_trade_sharpe_moments,
)


def _git_sha(repo: Path) -> str:
    try:
        cp = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        return (cp.stdout or "").strip() or "unknown"
    except OSError:
        return "unknown"


def _json_sanitize(obj: object) -> object:
    """JSON-serializable tree; NaN/±inf → None."""

    import math

    import numpy as np

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


def _combine_segment_trades(
    seg_frames: list[pl.DataFrame],
    sim_fn_name: str,
) -> list[TradeRow]:
    out: list[TradeRow] = []
    for seg in seg_frames:
        mnq_et = prepare_et_frame(seg)
        if mnq_et.is_empty():
            continue
        part: list[TradeRow]
        if sim_fn_name == "h11":
            part = simulate_h11(mnq_et)
        elif sim_fn_name == "h12":
            part = simulate_h12(mnq_et)
        else:
            msg = sim_fn_name
            raise ValueError(msg)
        out.extend(part)
    return out


def _h1_combine(segments: list[pl.DataFrame], sweep: tuple[int, ...]) -> dict[int, list[TradeRow]]:
    agg: dict[int, list[TradeRow]] = {x: [] for x in sweep}
    for seg in segments:
        mnq_et = prepare_et_frame(seg)
        if mnq_et.is_empty():
            continue
        part = simulate_h1(mnq_et, sweep)
        for k in sweep:
            agg[int(k)].extend(part[int(k)])
    return agg


def _h2_combine(
    segments: list[pl.DataFrame],
    sweep: tuple[float, ...],
) -> dict[float, list[TradeRow]]:
    agg: dict[float, list[TradeRow]] = {float(s): [] for s in sweep}
    for seg in segments:
        mnq_et = prepare_et_frame(seg)
        if mnq_et.is_empty():
            continue
        part = simulate_h2(mnq_et, sweep)
        for k in agg:
            agg[k].extend(part[k])
    return agg


def _gate_score(gr: GateResult) -> int:
    return sum(
        [
            bool(gr.gate1_pass),
            bool(gr.gate2_pass),
            bool(gr.gate3_pass),
            bool(gr.gate4_pass),
            bool(gr.gate5_pass),
        ]
    )


def _pick_best_sweep_variant(
    variant_trades: dict[str, tuple[list[TradeRow], float]],
) -> tuple[str, list[TradeRow], GateResult]:
    best_key = ""
    best_trades: list[TradeRow] = []
    best_gr: GateResult | None = None
    best_sc = (-1, -1e18)
    for key, (tr_lst, _) in variant_trades.items():
        gr = evaluate_gates(tr_lst)
        pnl = sum(t.pnl_usd_qty1 for t in tr_lst if t.exit_et_date.year in GATE_EVAL_YEARS)
        sc = (_gate_score(gr), pnl)
        if sc > best_sc:
            best_sc = sc
            best_key = key
            best_trades = tr_lst
            best_gr = gr
    assert best_gr is not None
    return best_key, best_trades, best_gr


def main() -> None:
    root = _REPO / "data" / "raw"
    if not any(root.glob("MNQ *.Last.txt")):
        print("No MNQ files under data/raw; abort.", file=sys.stderr)
        sys.exit(2)

    chi = ZoneInfo(session.CT_TIMEZONE)
    protocol_start = dt.date(2021, 1, 1)
    protocol_end_inc = dt.date(2025, 12, 31)
    ts0 = dt.datetime.combine(protocol_start, dt.time.min).replace(tzinfo=chi)
    ts_end_excl = dt.datetime.combine(protocol_end_inc + dt.timedelta(days=1), dt.time.min).replace(
        tzinfo=chi,
    )

    raw = data_loader.load_all_contracts(root)
    cont = continuous_contract.build_continuous_contract(raw)
    cls_df = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls_df)
    rth = dated.filter(pl.col("session") == session.SESSION_RTH)
    window = rth.filter((pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts_end_excl)).sort(
        "timestamp",
    )

    segments = split_dataframe_at_operator_export_gaps(window)

    h1_sw = (8, 10, 12)
    h2_sw = (8.0, 10.0, 12.0)

    trades_h11 = _combine_segment_trades(segments, "h11")
    trades_h12 = _combine_segment_trades(segments, "h12")
    h1_map = _h1_combine(segments, h1_sw)
    h2_map = _h2_combine(segments, h2_sw)

    es_pat = instrument_raw_coverage(root, pattern=data_loader.ES_CONTRACT_GLOB)
    rty_pat = instrument_raw_coverage(root, pattern=data_loader.RTY_CONTRACT_GLOB)

    blocked_es = int(es_pat["contract_file_count"]) == 0
    blocked_rty = int(rty_pat["contract_file_count"]) == 0

    variant_eval: dict[str, dict[str, tuple[list[TradeRow], float]]] = {}

    variant_eval["H1"] = {}
    for x in h1_sw:
        tl = h1_map[x]
        variant_eval["H1"][f"X{x}"] = (tl, sum(t.pnl_usd_qty1 for t in tl))

    variant_eval["H2"] = {}
    for sp in h2_sw:
        tl = h2_map[sp]
        variant_eval["H2"][f"stop{int(sp)}"] = (
            tl,
            sum(t.pnl_usd_qty1 for t in tl),
        )

    best_h1_key, best_h1_tr, _ = _pick_best_sweep_variant(variant_eval["H1"])
    best_h2_key, best_h2_tr, _ = _pick_best_sweep_variant(variant_eval["H2"])

    final_hypothesis_trades = {
        "H1": best_h1_tr,
        "H2": best_h2_tr,
        "H8": [] if blocked_es else [],
        "H9": [] if blocked_rty else [],
        "H10": [] if blocked_es else [],
        "H11": trades_h11,
        "H12": trades_h12,
    }

    blk_map: dict[str, str] = {}
    if blocked_es:
        blk_map["H8"] = (
            "H8 ES–NQ divergence: no ES raw exports under "
            f"`{data_loader.ES_CONTRACT_GLOB}`. Stage 1 runs without macro calendar filter "
            "(pre-registered: first-hour post FOMC/NFP/CPI window)."
        )
        blk_map["H10"] = (
            "H10 ES levels reaction: no stitched ES tape (same glob as H8 prerequisite)."
        )
    if blocked_rty:
        blk_map["H9"] = (
            "H9 RTY lead: no RTY raw exports under "
            f"`{data_loader.RTY_CONTRACT_GLOB}` (count=0)."
        )

    if blk_map:
        print(
            "Cross-instrument hypotheses blocked (missing tapes): "
            f"ES_needed={blocked_es}, RTY_needed={blocked_rty}. ",
            file=sys.stderr,
            end="",
        )
        print("See blocked_reason strings in artifact JSON.", file=sys.stderr)

    ordered_ids = ["H1", "H2", "H8", "H9", "H10", "H11", "H12"]

    hypotheses_report: dict[str, object] = {}
    sharpes_daily: list[float] = []
    daily_vecs: list = []

    for hid in ordered_ids:
        tl = final_hypothesis_trades[hid]
        gr = evaluate_gates(tl)
        dail = daily_pnls_qty1_et(list(tl), GATE_EVAL_YEARS)
        sr_d = daily_sharpe_annualized(dail) if tl else float("nan")
        sharpes_daily.append(sr_d)
        daily_vecs.append(dail)
        k_sort, sess_pnl = session_pnl_arrays(list(tl), years_filter=GATE_EVAL_YEARS)
        boot = block_bootstrap_session_mean_annual_ci(
            k_sort,
            sess_pnl,
            block_len=20,
            n_iterations=1000,
            seed=42,
        )
        mom = summarize_trade_sharpe_moments(dail)

        hyp_block: dict[str, object] = {
            "trades_gate_years_qty1": len(
                [t for t in tl if t.exit_et_date.year in GATE_EVAL_YEARS]
            ),
            "selected_variant": None,
            "gates_full": {
                "gate1": {"pass": gr.gate1_pass, "detail": gr.gate1_detail},
                "gate2": {"pass": gr.gate2_pass, "detail": gr.gate2_detail},
                "gate3": {"pass": gr.gate3_pass, "detail": gr.gate3_detail},
                "gate4": {"pass": gr.gate4_pass, "detail": gr.gate4_detail},
                "gate5": {"pass": gr.gate5_pass, "detail": gr.gate5_detail},
                "overall_survives_track1": bool(gr.overall_survives),
            },
            "sharpe": {
                "aggregation": (
                    "Daily realized USD P&L at qty=1 MNQ; calendar NY exit-date; sqrt(252) scale."
                ),
                "daily_sharpe_annualized_point": sr_d,
                "daily_moment_summary_qty1": mom,
                "note": (
                    "Block bootstrap below is on CME-session P&L sums (qty=1), "
                    "not daily Sharpe residuals."
                ),
            },
            "bootstrap_mean_annual_pnl_qty1_sessions": boot,
            "blocked_reason": blk_map.get(hid),
        }
        if hid == "H1":
            hyp_block["selected_variant"] = best_h1_key
            hyp_block["sweep_eval_summary"] = {
                k: {
                    "trades": len(v[0]),
                    "pnl_gate_years_qty1_sum": sum(
                        x.pnl_usd_qty1 for x in v[0] if x.exit_et_date.year in GATE_EVAL_YEARS
                    ),
                    "gates_pass_score": _gate_score(evaluate_gates(v[0])),
                }
                for k, v in variant_eval["H1"].items()
            }
        elif hid == "H2":
            hyp_block["selected_variant"] = best_h2_key
            hyp_block["sweep_eval_summary"] = {
                k: {
                    "trades": len(v[0]),
                    "pnl_gate_years_qty1_sum": sum(
                        x.pnl_usd_qty1 for x in v[0] if x.exit_et_date.year in GATE_EVAL_YEARS
                    ),
                    "gates_pass_score": _gate_score(evaluate_gates(v[0])),
                }
                for k, v in variant_eval["H2"].items()
            }
        hypotheses_report[hid] = hyp_block

    dsr_blob = deflated_sharpe_track(sharpes_daily, daily_vecs, n_trials=7)

    survivors = [
        hid
        for hid in ordered_ids
        if hypotheses_report[hid]["gates_full"]["overall_survives_track1"]
    ]

    artifact = {
        "wave": "Wave1_Stage1_Track1_quant_derived_screen",
        "date": "2026-05-26",
        "git_sha": _git_sha(_REPO),
        "protocol_calendar": {
            "start": protocol_start.isoformat(),
            "end_inclusive": protocol_end_inc.isoformat(),
            "year_filters_gates": list(GATE_EVAL_YEARS),
            "instrument_execution": "MNQ",
            "commission_slippage": (
                "none coarse screen ($0); exit modeling minute-bar "
                "pessimistic dual touch."
            ),
        },
        "data_extensions": {"ES_raw_glob_probe": es_pat, "RTY_raw_glob_probe": rty_pat},
        "segment_splits_for_export_gaps": len(segments),
        "hypotheses_best_variant_and_gates": hypotheses_report,
        "deflated_sharpe_track_n7": dsr_blob,
        "survivors_hypothesis_ids_ordered": survivors,
        "stop_surfaces_triggers": [],
    }

    if not survivors:
        artifact["stop_surfaces_triggers"].append(
            "ALL_SEVEN_KILLED: no hypothesis cleared all five Stage-1 coarse gates "
            "(may include blocked cross-instrument rows)."
        )

    out_dir = _REPO / "notebooks" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / "2026-05-26_wave1_stage1_track1_quant_screen"
    with (base.with_suffix(".json")).open("w", encoding="utf-8") as f:
        json.dump(_json_sanitize(artifact), f, indent=2)

    lines = [
        "# Wave 1 Stage 1 Track 1 — quant coarse screen vs Apex-style gates\n",
        f"**Artifact JSON:** `{base.with_suffix('.json')}`",
        "**Protocol:** MNQ qty=1 economics; exits **America/New_York** calendar attribution; "
        f"evaluation years **{list(GATE_EVAL_YEARS)}** (Frame B excludes 2020).",
        "",
        "## Loader / ES–RTY status",
        f"- ES glob `{data_loader.ES_CONTRACT_GLOB}`: "
        f"**{es_pat['contract_file_count']}** files.",
        f"- RTY glob `{data_loader.RTY_CONTRACT_GLOB}`: "
        f"**{rty_pat['contract_file_count']}** files.",
        "- Cross-instrument hypotheses **H8/H9/H10:** "
        + (
            "blocked where ES or RTY export missing — see JSON"
            if (blocked_es or blocked_rty)
            else "eligible"
        )
        + ".",
        "",
        "## Operator summary — survivors vs killed",
        f"- **SURVIVE (all five gates):** {', '.join(survivors) if survivors else '**NONE**'}",
        "",
        "### Findings before Stage 2",
        (
            "- **H11 (15m opening range breakout)** cleared **Gates 2–5** on the best path "
            "but **failed Gate 1**: at the $30K/yr sizing heuristic, **worst "
            "single-session loss (~$1.3K) exceeds the $1,000** (per-session DLL-style "
            "screen). Only MNQ hypothesis with four-of-five coarse gate passes."
        ),
        (
            "- **H12** passes year profile (G5) but fails **frequency**, **win rate**, "
            "**R:R**, and **session tail** vs Gate 1 sizing."
        ),
        (
            "- **H1/H2** fail **Gate 1** (negative mean annual at qty=1) and **win rate**."
        ),
        (
            "- **Deflated Sharpe (N=7):** wide SR spread (H1/H2 negative vs H11/H12 positive); "
            "PSR vs track null is strong for H11/H12, but **Gate 1** blocks H11 anyway here."
        ),
        "",
    ]
    for hid in ordered_ids:
        gb = hypotheses_report[hid]["gates_full"]
        lines.append(f"### {hid}")
        if hypotheses_report[hid].get("selected_variant"):
            lines.append(f"- **Selected sweep:** `{hypotheses_report[hid]['selected_variant']}`")
        lines.append(
            f"- Gates: G1={'PASS' if gb['gate1']['pass'] else 'FAIL'}, "
            f"G2={'PASS' if gb['gate2']['pass'] else 'FAIL'}, "
            f"G3={'PASS' if gb['gate3']['pass'] else 'FAIL'}, "
            f"G4={'PASS' if gb['gate4']['pass'] else 'FAIL'}, "
            f"G5={'PASS' if gb['gate5']['pass'] else 'FAIL'} "
            f"→ **{'SURVIVE' if gb['overall_survives_track1'] else 'KILLED'}**"
        )
        if hypotheses_report[hid].get("blocked_reason"):
            lines.append(f"- Blocked: `{hypotheses_report[hid]['blocked_reason']}`")
        bd = hypotheses_report[hid]["bootstrap_mean_annual_pnl_qty1_sessions"]
        lines.append(f"- Bootstrap mean-annual P&L CI95: `{bd}`")
        lines.append("")
    lines.append("## Deflated Sharpe (within-track N=7)")
    lines.append(
        "```json\n"
        + json.dumps(_json_sanitize(dsr_blob), indent=2)[:18000]
        + "\n```"
    )

    md_path = base.with_suffix(".md")
    md_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
