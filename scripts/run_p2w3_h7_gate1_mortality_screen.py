#!/usr/bin/env python3
"""P2-W3 / H-7 Gate #1 mortality screen — IS partition only.

Usage::

    uv run python scripts/run_p2w3_h7_gate1_mortality_screen.py

Writes ``notebooks/validation/2026-06-08_p2w3_h7_gate1_mortality_screen.{md,json}``.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.backtest.m6_metrics import protocol_year_fraction
from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.research_p2w2.data_verify import PROTOCOL_END, PROTOCOL_START, load_verified_mnq_rth
from quant_research.research_p2w2.hypothesis_sims import (
    count_h3_h7_reclaim_triggers,
    prepare_et_frame,
    run_hypothesis,
)
from quant_research.research_p2w2.metrics import gate1_is_screen, run_harness, split_is_oos

OUT_STEM = _REPO / "notebooks" / "validation" / "2026-06-08_p2w3_h7_gate1_mortality_screen"
FORENSIC_JSON = _REPO / "notebooks" / "validation" / "2026-06-08_p2w2_forensic_verdict_check.json"
H3_TOTAL_ANCHOR = 1230
H3_IS_ANCHOR = 738
H3_FLIP_IS_NET = 15.65
FORENSIC_SAMPLE_DATES = (
    "2020-01-02",
    "2020-05-25",
    "2020-10-02",
    "2021-02-26",
    "2021-07-26",
)


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


def _trade_key(session: dt.date, entry_price: float) -> tuple[str, float]:
    return (str(session), round(entry_price, 2))


def _dir_label(d: int) -> str:
    return "long" if d == 1 else "short"


def _inversion_proof(h3_trades: list, h7_trades: list) -> list[dict[str, object]]:
    h3_by = {_trade_key(t.cme_session_date, t.entry_price): t for t in h3_trades}
    h7_by = {_trade_key(t.cme_session_date, t.entry_price): t for t in h7_trades}
    rows: list[dict[str, object]] = []
    for sdate in FORENSIC_SAMPLE_DATES:
        h3_match = None
        h7_match = None
        for k, t in h3_by.items():
            if k[0] == sdate:
                h3_match = t
                break
        for k, t in h7_by.items():
            if k[0] == sdate:
                h7_match = t
                break
        if h3_match is None or h7_match is None:
            rows.append(
                {
                    "session_date": sdate,
                    "status": "MISSING",
                    "h3_direction": _dir_label(h3_match.direction) if h3_match else None,
                    "h7_direction": _dir_label(h7_match.direction) if h7_match else None,
                    "entry_price_h3": h3_match.entry_price if h3_match else None,
                    "entry_price_h7": h7_match.entry_price if h7_match else None,
                    "inverted": None,
                }
            )
            continue
        inverted = h3_match.direction == -h7_match.direction
        rows.append(
            {
                "session_date": sdate,
                "status": "OK",
                "h3_direction": _dir_label(h3_match.direction),
                "h7_direction": _dir_label(h7_match.direction),
                "entry_price_h3": round(h3_match.entry_price, 2),
                "entry_price_h7": round(h7_match.entry_price, 2),
                "same_entry_bar": abs(h3_match.entry_price - h7_match.entry_price) < 0.01,
                "inverted": inverted,
            }
        )
    return rows


def _render_md(payload: dict[str, object]) -> str:
    g1 = payload["gate1"]
    lines = [
        "# P2-W3 / H-7 Gate #1 mortality screen (IS partition)",
        "",
        f"**Date:** 2026-06-08  ",
        f"**Wave:** P2-W3 / **H-7**  ",
        f"**git_sha:** `{payload['git']['git_sha']}`  ",
        f"**Status:** RESULT-LOGGED (Gate #1 only; OOS sealed)",
        "",
        "## Data precondition",
        "",
    ]
    ds = payload["mnq_dataset"]
    lines.extend(
        [
            f"- **data_root:** `{ds['data_root']}`",
            f"- **pattern:** `{ds['pattern']}`",
            f"- **contract_files:** {ds['contract_file_count']}",
            f"- **RTH bars:** {ds['rth_bar_count']:,}",
            f"- **session_dates:** {ds['session_date_count']:,}",
            f"- **range (CT):** {ds['first_bar_ct']} → {ds['last_bar_ct']}",
            f"- **verification:** {'PASS' if ds['passed'] else '**FAIL**'}",
            "",
            "## H-3 trigger parity",
            "",
            f"- **Shared reclaim triggers:** {payload['h3_crosscheck']['trigger_count']:,}",
            f"- **H-3 trades (re-run):** {payload['h3_crosscheck']['h3_total']:,} "
            f"(anchor {payload['h3_crosscheck']['h3_anchor']:,})",
            f"- **H-7 trades:** {payload['h3_crosscheck']['h7_total']:,}",
            f"- **H-3 geometry rejects:** {payload['h3_crosscheck']['h3_geometry_rejects']:,} "
            "(structural stop/target; H-7 fixed 10/20 accepts all triggers)",
            f"- **Trigger parity:** {payload['h3_crosscheck']['verdict']}",
            "",
            "## Inversion proof (5 forensic sample dates)",
            "",
            "| Session | H-3 dir | H-7 dir | Entry (H-3) | Entry (H-7) | Inverted? |",
            "|---------|---------|---------|-------------|-------------|-----------|",
        ]
    )
    for row in payload["inversion_proof"]:
        lines.append(
            f"| {row['session_date']} | {row.get('h3_direction', '—')} | "
            f"{row.get('h7_direction', '—')} | {row.get('entry_price_h3', '—')} | "
            f"{row.get('entry_price_h7', '—')} | {row.get('inverted', '—')} |"
        )
    lines.extend(
        [
            "",
            f"**Time stop:** {payload['spec']['time_stop']}",
            f"**Stop / target:** {payload['spec']['stop_pts']}pt / {payload['spec']['target_pts']}pt fixed",
            "",
            "## Harness V1–V6",
            "",
            f"**Overall:** {'PASS' if payload['harness']['passed'] else '**FAIL**'}",
            "",
            "## Gate #1 (IS only)",
            "",
            f"- **Total trades:** {payload['partition']['total_trades']:,} | "
            f"**IS:** {payload['partition']['is_trade_count']:,} | "
            f"**OOS sealed:** {payload['partition']['oos_trade_count']:,}",
            f"- **IS/OOS boundary (last IS exit):** {payload['partition']['is_oos_boundary_last_is_exit']}",
            f"- **Trades/yr (total, protocol):** {payload['trades_per_yr']:.1f}",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Gross expectancy/trade | ${g1['gross_expectancy_per_trade']:.2f} |",
            f"| Cost/trade | ${g1['cost_per_trade']:.2f} |",
            f"| **Net expectancy/trade** | **${g1['net_expectancy_per_trade']:.2f}** |",
            f"| Win rate (net) | {100 * g1['win_rate']:.1f}% |",
            f"| Avg win (net) | ${g1['avg_win_net']:.2f} |",
            f"| Avg loss (net) | ${g1['avg_loss_net']:.2f} |",
            f"| Max single-trade loss (net) | ${g1['max_single_trade_loss_net']:.2f} |",
            f"| P95 single-trade loss (net) | ${g1['p95_single_trade_loss_net']:.2f} |",
            "",
            "## Flip motivation cross-check",
            "",
            payload["flip_crosscheck"]["narrative"],
            "",
            "## Summary",
            "",
            f"**H-7: {g1['verdict']}** — net ${g1['net_expectancy_per_trade']:.2f}/trade "
            f"({g1['is_trade_count']:,} IS trades)",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    git = _git_meta(_REPO)
    data_root = _REPO / "data" / "raw"

    print("=== MNQ dataset verification ===", flush=True)
    try:
        rth, ds_report = load_verified_mnq_rth(data_root)
    except RuntimeError as exc:
        print(f"HARD STOP: {exc}", file=sys.stderr)
        return 1

    print(f"  data_root: {data_root}")
    print(f"  contract_files: {ds_report.contract_file_count}")
    print(f"  RTH bars: {ds_report.rth_bar_count:,}")
    print(f"  sessions: {ds_report.session_date_count:,}")
    print(f"  range: {ds_report.first_session} -> {ds_report.last_session}")

    segments = split_dataframe_at_operator_export_gaps(rth)
    trigger_count = 0
    for seg in segments:
        if seg.is_empty():
            continue
        mnq_et = prepare_et_frame(seg)
        if not mnq_et.is_empty():
            trigger_count += count_h3_h7_reclaim_triggers(mnq_et)

    h3_trades = run_hypothesis("H-3", segments)
    h7_trades = run_hypothesis("H-7", segments)
    h3_geom_rejects = trigger_count - len(h3_trades)

    print(f"\n=== H-3 / H-7 trigger parity ===", flush=True)
    print(f"  Shared reclaim triggers: {trigger_count}")
    print(f"  H-3 trades: {len(h3_trades)} (anchor {H3_TOTAL_ANCHOR})")
    print(f"  H-7 trades: {len(h7_trades)}")
    print(f"  H-3 geometry rejects: {h3_geom_rejects}")

    if len(h7_trades) != trigger_count:
        msg = (
            f"HARD STOP: H-7 trades {len(h7_trades)} != shared triggers {trigger_count} "
            "— trigger / trade mapping diverged"
        )
        print(msg, file=sys.stderr)
        payload = {
            "stopped": True,
            "stop_reason": msg,
            "git": git,
            "trigger_count": trigger_count,
            "h3_total": len(h3_trades),
            "h7_total": len(h7_trades),
        }
        OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
        OUT_STEM.with_suffix(".json").write_text(
            json.dumps(_json_sanitize(payload), indent=2),
            encoding="utf-8",
        )
        OUT_STEM.with_suffix(".md").write_text(f"# H-7 Gate #1 — HARD STOP\n\n{msg}\n", encoding="utf-8")
        return 1

    if len(h3_trades) != H3_TOTAL_ANCHOR:
        msg = (
            f"HARD STOP: H-3 re-run {len(h3_trades)} != anchor {H3_TOTAL_ANCHOR} "
            "— baseline drift; cannot trust cross-check"
        )
        print(msg, file=sys.stderr)
        return 1

    parity_verdict = (
        f"PASS — {trigger_count:,} shared triggers; H-7 maps all; "
        f"H-3 drops {h3_geom_rejects} on structural geometry"
    )
    print(f"  {parity_verdict}")

    harness = run_harness(h7_trades, git_sha=str(git["git_sha"]))
    if not harness.passed:
        failed = [{"check_id": c.check_id, "message": c.message} for c in harness.failed_checks]
        print(f"HARD STOP: harness FAIL — {failed}", file=sys.stderr)
        return 1

    is_trades, oos_trades, part_meta = split_is_oos(h7_trades)
    g1 = gate1_is_screen(is_trades)
    inversion = _inversion_proof(h3_trades, h7_trades)
    if not all(r.get("inverted") is True for r in inversion if r.get("status") == "OK"):
        print("WARNING: inversion proof incomplete on sample dates", file=sys.stderr)

    yfrac = protocol_year_fraction(PROTOCOL_START, PROTOCOL_END)
    trades_per_yr = len(h7_trades) / yfrac if yfrac > 0 else 0.0
    gap_vs_flip = g1["net_expectancy_per_trade"] - H3_FLIP_IS_NET

    flip_narrative = (
        f"H-3 arithmetic flip (upper-biased): **+${H3_FLIP_IS_NET:.2f}/trade** on IS. "
        f"H-7 walked continuation exits (10pt stop / 20pt target): "
        f"**${g1['net_expectancy_per_trade']:.2f}/trade** on IS. "
        f"Gap vs flip: **${gap_vs_flip:+.2f}/trade**. "
        "Large shortfall vs +$15.65 is expected (flip does not re-walk bars); "
        "a result near or above the flip would warrant skeptical exit-walk review."
    )

    payload: dict[str, object] = {
        "wave": "P2-W3",
        "hypothesis": "H-7",
        "screen": "gate1_mortality_is_only",
        "date": "2026-06-08",
        "git": git,
        "mnq_dataset": {
            "data_root": str(ds_report.data_root),
            "pattern": ds_report.pattern,
            "contract_file_count": ds_report.contract_file_count,
            "rth_bar_count": ds_report.rth_bar_count,
            "session_date_count": ds_report.session_date_count,
            "first_bar_ct": ds_report.first_bar_ct.isoformat() if ds_report.first_bar_ct else None,
            "last_bar_ct": ds_report.last_bar_ct.isoformat() if ds_report.last_bar_ct else None,
            "first_session": ds_report.first_session.isoformat() if ds_report.first_session else None,
            "last_session": ds_report.last_session.isoformat() if ds_report.last_session else None,
            "passed": ds_report.passed,
        },
        "spec": {
            "stop_pts": 10.0,
            "target_pts": 20.0,
            "time_stop": "12:00 ET (T_ET_1200) — same as H-3",
            "max_trades_per_session": 1,
        },
        "h3_crosscheck": {
            "trigger_count": trigger_count,
            "h3_total": len(h3_trades),
            "h7_total": len(h7_trades),
            "h3_anchor": H3_TOTAL_ANCHOR,
            "h3_geometry_rejects": h3_geom_rejects,
            "verdict": parity_verdict,
        },
        "inversion_proof": inversion,
        "harness": harness.to_dict(),
        "partition": part_meta,
        "oos_sealed_count": len(oos_trades),
        "gate1": g1,
        "trades_per_yr": trades_per_yr,
        "protocol_yfrac": yfrac,
        "flip_crosscheck": {
            "h3_flip_is_net_upper_biased": H3_FLIP_IS_NET,
            "h7_is_net_walked": g1["net_expectancy_per_trade"],
            "gap_vs_flip": gap_vs_flip,
            "narrative": flip_narrative,
        },
        "summary": {
            "verdict": g1["verdict"],
            "net_expectancy_per_trade": g1["net_expectancy_per_trade"],
            "is_trade_count": g1["is_trade_count"],
        },
    }

    OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
    OUT_STEM.with_suffix(".json").write_text(
        json.dumps(_json_sanitize(payload), indent=2),
        encoding="utf-8",
    )
    OUT_STEM.with_suffix(".md").write_text(_render_md(payload), encoding="utf-8")

    print(f"\nWrote {OUT_STEM.with_suffix('.md')}")
    print(
        f"\nH-7: {g1['verdict']} — net ${g1['net_expectancy_per_trade']:.2f}/trade "
        f"({g1['is_trade_count']} IS, {trades_per_yr:.1f}/yr)"
    )
    print(flip_narrative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
