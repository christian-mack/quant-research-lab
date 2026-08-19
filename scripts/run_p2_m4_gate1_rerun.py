#!/usr/bin/env python3
"""P2-W2/W3 M4 engine Gate #1 re-run — IS partition, V1–V7 mandatory.

Usage::

    uv run python scripts/run_p2_m4_gate1_rerun.py

Writes ``notebooks/validation/2026-06-08_p2_m4_gate1_rerun.{md,json}``.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "src"))

from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.research_p2w2.data_verify import (
    PROTOCOL_END,
    PROTOCOL_START,
    load_verified_mnq_rth,
)
from quant_research.research_p2w2.hypothesis_sims import run_hypothesis_m4
from quant_research.research_p2w2.metrics import (
    gate1_is_screen_log,
    split_is_oos_log,
    trades_per_yr,
)

OUT_STEM = _REPO / "notebooks" / "validation" / "2026-06-08_p2_m4_gate1_rerun"
HYPOTHESES = ("H-1", "H-2", "H-3", "H-4", "H-6", "H-7")

# Bespoke-walker IS gate #1 anchors (pre-V7, untrusted path).
WALKER_IS_ANCHOR: dict[str, dict[str, float | int]] = {
    "H-1": {"is_trades": 7, "net_per_trade": -17.69, "win_rate": 0.0},
    "H-2": {"is_trades": 726, "net_per_trade": -5.34, "win_rate": 0.231},
    "H-3": {"is_trades": 738, "net_per_trade": -19.61, "win_rate": 0.046},
    "H-4": {"is_trades": 46, "net_per_trade": -3.34, "win_rate": 0.217},
    "H-6": {"is_trades": 282, "net_per_trade": -12.79, "win_rate": 0.043},
    "H-7": {"is_trades": 751, "net_per_trade": 20.85, "win_rate": 0.748},
}
H7_FORENSIC_CORRECTED = -2.41
H7_INFLATED_STOP_NET = 15.0


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
    import datetime as dt

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


def _check_stop_conditions(hid: str, g1: dict[str, object]) -> list[str]:
    stops: list[str] = []
    net = float(g1["net_expectancy_per_trade"])
    walker = WALKER_IS_ANCHOR[hid]
    walker_net = float(walker["net_per_trade"])
    if walker_net < 0 and net > 0:
        stops.append(f"{hid} flipped negative→positive (walker ${walker_net:.2f} → M4 ${net:.2f})")
    return stops


def _render_md(payload: dict[str, object]) -> str:
    lines = [
        "# P2-W2/W3 Gate #1 re-run on M4 engine (IS partition)",
        "",
        "**Date:** 2026-06-08  ",
        f"**git_sha:** `{payload['git']['git_sha']}`  ",
        "**Fill path:** M4 `BacktestEngine` (V7 provenance)  ",
        "**OOS:** sealed",
        "",
        "## Comparison — bespoke walker vs M4 engine (IS Gate #1)",
        "",
        "| ID | Walker net/tr | M4 net/tr | Δ net | Walker WR | M4 WR | V7 | Verdict |",
        "|----|---------------|-----------|-------|-----------|-------|-----|---------|",
    ]
    for hid, row in payload["hypotheses"].items():
        w = WALKER_IS_ANCHOR[hid]
        if row.get("stopped"):
            lines.append(
                f"| {hid} | ${w['net_per_trade']:.2f} | — | — | "
                f"{100 * w['win_rate']:.1f}% | — | **FAIL** | **STOPPED** |"
            )
            continue
        g = row["gate1"]
        v7 = "PASS" if row["harness_v7_pass"] else "**FAIL**"
        lines.append(
            f"| {hid} | ${w['net_per_trade']:.2f} | ${g['net_expectancy_per_trade']:.2f} | "
            f"${g['net_expectancy_per_trade'] - w['net_per_trade']:+.2f} | "
            f"{100 * w['win_rate']:.1f}% | {100 * g['win_rate']:.1f}% | {v7} | "
            f"**{g['verdict']}** |"
        )
    if payload.get("stop_reasons"):
        lines.extend(["", "## HARD STOP", ""])
        for s in payload["stop_reasons"]:
            lines.append(f"- {s}")
    lines.extend(["", "## Per-strategy summary", ""])
    for hid, row in payload["hypotheses"].items():
        if row.get("stopped"):
            lines.append(f"- **{hid}: STOPPED** — harness failed before gate #1")
            continue
        g = row["gate1"]
        lines.append(
            f"- **{hid}: {g['verdict']}** — M4 net ${g['net_expectancy_per_trade']:.2f}/tr "
            f"({g['is_trade_count']} IS, {row['trades_per_yr']:.1f}/yr) — V7 "
            f"{'PASS' if row['harness_v7_pass'] else 'FAIL'}"
        )
    h7 = payload["hypotheses"].get("H-7", {})
    if h7:
        g = h7["gate1"]
        lines.append(
            f"\n**H-7 forensic cross-check:** corrected walker estimate "
            f"**${H7_FORENSIC_CORRECTED:.2f}/tr** vs M4 **${g['net_expectancy_per_trade']:.2f}/tr**."
        )
    return "\n".join(lines)


def main() -> int:
    git = _git_meta()
    data_root = _REPO / "data" / "raw"
    print("=== MNQ dataset ===", flush=True)
    try:
        rth, ds = load_verified_mnq_rth(data_root)
    except RuntimeError as exc:
        print(f"HARD STOP: {exc}", file=sys.stderr)
        return 1
    print(f"  {ds.contract_file_count} files, {ds.rth_bar_count:,} bars")

    segments = split_dataframe_at_operator_export_gaps(rth)
    results: dict[str, object] = {}
    stop_reasons: list[str] = []

    for hid in HYPOTHESES:
        print(f"\n=== {hid} M4 run ===", flush=True)
        batch = run_hypothesis_m4(hid, segments)
        harness = batch.validation_report
        failed = (
            [{"id": c.check_id, "msg": c.message} for c in harness.failed_checks]
            if harness
            else [{"id": "?", "msg": "no report"}]
        )
        v7 = next((c for c in harness.checks if c.check_id == "V7"), None) if harness else None

        is_log, oos_log, part = split_is_oos_log(batch.trade_log)
        g1 = gate1_is_screen_log(is_log)
        tpy = trades_per_yr(batch.trade_log.height, PROTOCOL_START, PROTOCOL_END)
        stops = _check_stop_conditions(hid, g1)

        hard_stop = False
        if v7 is None or not v7.passed:
            msg = f"HARD STOP: {hid} V7 FAIL — {v7.message if v7 else 'missing'}"
            print(msg, file=sys.stderr)
            stop_reasons.append(msg)
            hard_stop = True
        if hid == "H-7" and float(g1["net_expectancy_per_trade"]) > H7_INFLATED_STOP_NET:
            msg = (
                f"HARD STOP: H-7 M4 net ${g1['net_expectancy_per_trade']:.2f}/tr "
                f"near bespoke inflated ${WALKER_IS_ANCHOR['H-7']['net_per_trade']:.2f}"
            )
            print(msg, file=sys.stderr)
            stop_reasons.append(msg)
            hard_stop = True
        if harness and not harness.passed:
            msg = f"Harness FAIL: {hid} — {failed}"
            print(msg, file=sys.stderr)
            if not (v7 and v7.passed):
                stop_reasons.append(msg)
        for s in stops:
            print(f"  REVIEW: {s}", file=sys.stderr)
            stop_reasons.append(s)

        print(
            f"  {hid}: {g1['verdict']} — net ${g1['net_expectancy_per_trade']:.2f}/tr "
            f"({g1['is_trade_count']} IS, V7 {'PASS' if v7 and v7.passed else 'FAIL'})"
        )

        results[hid] = {
            "stopped": hard_stop,
            "harness_passed": bool(harness and harness.passed),
            "harness_failed": failed if harness and not harness.passed else [],
            "total_trades": batch.trade_log.height,
            "setups_scanned": batch.setups_scanned,
            "geometry_rejects": batch.geometry_rejects,
            "partition": part,
            "oos_sealed_count": oos_log.height,
            "harness": harness.to_dict(),
            "harness_v7_pass": bool(v7 and v7.passed),
            "gate1": g1,
            "trades_per_yr": tpy,
            "walker_anchor": WALKER_IS_ANCHOR[hid],
            "delta_net_vs_walker": g1["net_expectancy_per_trade"]
            - WALKER_IS_ANCHOR[hid]["net_per_trade"],
        }

    payload: dict[str, object] = {
        "wave": "P2-W2/W3",
        "screen": "m4_engine_gate1_rerun_is_only",
        "date": "2026-06-08",
        "git": git,
        "mnq_dataset": {
            "contract_file_count": ds.contract_file_count,
            "rth_bar_count": ds.rth_bar_count,
            "session_date_count": ds.session_date_count,
            "first_session": ds.first_session.isoformat() if ds.first_session else None,
            "last_session": ds.last_session.isoformat() if ds.last_session else None,
        },
        "hypotheses": results,
        "stop_reasons": stop_reasons,
        "h7_forensic_anchor": H7_FORENSIC_CORRECTED,
    }

    OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
    OUT_STEM.with_suffix(".json").write_text(
        json.dumps(_json_sanitize(payload), indent=2),
        encoding="utf-8",
    )
    OUT_STEM.with_suffix(".md").write_text(_render_md(payload), encoding="utf-8")
    print(f"\nWrote {OUT_STEM.with_suffix('.md')}")

    hard = [s for s in stop_reasons if s.startswith("HARD STOP")]
    if hard:
        print("\nHARD STOP:", file=sys.stderr)
        for s in hard:
            print(f"  {s}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
