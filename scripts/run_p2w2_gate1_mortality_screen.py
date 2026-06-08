#!/usr/bin/env python3
"""P2-W2 Gate #1 mortality screen — net-of-cost per-trade expectancy on IS only.

Usage (repo root, MNQ under ``data/raw/mnq``)::

    uv run python scripts/run_p2w2_gate1_mortality_screen.py

Writes ``notebooks/validation/2026-06-08_p2w2_gate1_mortality_screen.{md,json}``.
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

from quant_research.data.quality import split_dataframe_at_operator_export_gaps
from quant_research.research_p2w2.data_verify import PROTOCOL_END, PROTOCOL_START, load_verified_mnq_rth
from quant_research.research_p2w2.hypothesis_sims import run_hypothesis
from quant_research.research_p2w2.metrics import gate1_is_screen, run_harness, split_is_oos

OUT_STEM = _REPO / "notebooks" / "validation" / "2026-06-08_p2w2_gate1_mortality_screen"
HYPOTHESES = ("H-1", "H-2", "H-3", "H-4", "H-6")


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


def _render_md(payload: dict[str, object]) -> str:
    lines = [
        "# P2-W2 Gate #1 mortality screen (IS partition)",
        "",
        f"**Date:** 2026-06-08  ",
        f"**Wave:** P2-W2  ",
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
            f"- **sessions:** {ds['first_session']} → {ds['last_session']}",
            f"- **verification:** {'PASS' if ds['passed'] else '**FAIL**'}",
            "",
            "## Protocol",
            "",
            f"- Window: **{payload['protocol']['start']}** – **{payload['protocol']['end_inclusive']}**",
            "- Partition: **60/40** by trade count (chronological); **this run = IS only**",
            "- Costs: **$1.98** RT + slip **1 tick** stop/time, **0.5 tick** target",
            "- Gate #1: net-of-cost per-trade expectancy **> 0** on IS",
            "",
            "## Per-hypothesis results",
            "",
        ]
    )
    for hid in HYPOTHESES:
        h = payload["hypotheses"][hid]
        if h.get("stopped"):
            lines.append(f"### {hid} — **STOPPED** ({h.get('stop_reason')})")
            lines.append("")
            continue
        part = h["partition"]
        g1 = h["gate1"]
        harness = h["harness"]
        lines.extend(
            [
                f"### {hid} — **{g1['verdict']}** (net ${g1['net_expectancy_per_trade']:.2f}/trade)",
                "",
                f"- **Total trades:** {h['total_trades']:,} | **IS:** {part['is_trade_count']:,} | "
                f"**OOS sealed:** {part['oos_trade_count']:,}",
                f"- **IS/OOS boundary (last IS exit):** {part['is_oos_boundary_last_is_exit']}",
                f"- **Harness V1–V6:** {'PASS' if harness['passed'] else '**FAIL**'}",
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
            ]
        )
        if not harness["passed"]:
            for chk in harness.get("failed_checks", []):
                lines.append(f"- Harness **{chk['check_id']}:** {chk['message']}")
            lines.append("")

    lines.extend(["## Summary", ""])
    for hid in HYPOTHESES:
        h = payload["hypotheses"][hid]
        if h.get("stopped"):
            lines.append(f"- **{hid}:** STOPPED — {h.get('stop_reason')}")
        else:
            g1 = h["gate1"]
            lines.append(
                f"- **{hid}:** {g1['verdict']} — net ${g1['net_expectancy_per_trade']:.2f}/trade "
                f"({g1['is_trade_count']:,} IS trades)"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    git = _git_meta(_REPO)
    data_root = _REPO / "data" / "raw"

    print("=== MNQ dataset verification (hard stop if fail) ===", flush=True)
    try:
        rth, ds_report = load_verified_mnq_rth(data_root)
    except RuntimeError as exc:
        print(f"HARD STOP: {exc}", file=sys.stderr)
        payload = {
            "wave": "P2-W2",
            "date": "2026-06-08",
            "git": git,
            "stopped": True,
            "stop_reason": str(exc),
            "mnq_dataset": {
                "data_root": str(data_root),
                "pattern": "mnq/MNQ *.Last.txt",
                "passed": False,
            },
        }
        OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
        OUT_STEM.with_suffix(".json").write_text(
            json.dumps(_json_sanitize(payload), indent=2),
            encoding="utf-8",
        )
        OUT_STEM.with_suffix(".md").write_text(
            f"# P2-W2 Gate #1 — HARD STOP\n\n{exc}\n",
            encoding="utf-8",
        )
        return 1

    print(f"  data_root: {data_root}")
    print(f"  pattern: {ds_report.pattern}")
    print(f"  contract_files: {ds_report.contract_file_count}")
    print(f"  sample_paths: {ds_report.contract_files[:3]} ...")
    print(f"  RTH bars: {ds_report.rth_bar_count:,}")
    print(f"  session_dates: {ds_report.session_date_count:,}")
    print(f"  range CT: {ds_report.first_bar_ct} -> {ds_report.last_bar_ct}")
    print(f"  sessions: {ds_report.first_session} -> {ds_report.last_session}")

    segments = split_dataframe_at_operator_export_gaps(rth)
    print(f"  gap-split segments: {len(segments)}", flush=True)

    payload: dict[str, object] = {
        "wave": "P2-W2",
        "screen": "gate1_mortality_is_only",
        "date": "2026-06-08",
        "git": git,
        "protocol": {
            "start": PROTOCOL_START.isoformat(),
            "end_inclusive": PROTOCOL_END.isoformat(),
            "is_fraction": 0.60,
            "oos_sealed": True,
        },
        "mnq_dataset": {
            "data_root": str(ds_report.data_root),
            "pattern": ds_report.pattern,
            "contract_file_count": ds_report.contract_file_count,
            "contract_file_sample": list(ds_report.contract_files[:5]),
            "rth_bar_count": ds_report.rth_bar_count,
            "session_date_count": ds_report.session_date_count,
            "first_bar_ct": ds_report.first_bar_ct.isoformat() if ds_report.first_bar_ct else None,
            "last_bar_ct": ds_report.last_bar_ct.isoformat() if ds_report.last_bar_ct else None,
            "first_session": ds_report.first_session.isoformat() if ds_report.first_session else None,
            "last_session": ds_report.last_session.isoformat() if ds_report.last_session else None,
            "passed": ds_report.passed,
        },
        "hypotheses": {},
        "summary": {},
    }

    any_stopped = False
    for hid in HYPOTHESES:
        print(f"\n=== {hid} ===", flush=True)
        trades = run_hypothesis(hid, segments)
        print(f"  total trades: {len(trades)}", flush=True)

        harness_report = run_harness(trades, git_sha=str(git["git_sha"]))
        harness_dict = harness_report.to_dict()
        if not harness_report.passed:
            failed = [
                {"check_id": c.check_id, "message": c.message}
                for c in harness_report.failed_checks
            ]
            harness_dict["failed_checks"] = failed
            print(f"  HARD STOP: harness FAIL — {failed}", file=sys.stderr)
            payload["hypotheses"][hid] = {
                "stopped": True,
                "stop_reason": "harness_fail",
                "total_trades": len(trades),
                "harness": harness_dict,
            }
            any_stopped = True
            continue

        is_trades, oos_trades, part_meta = split_is_oos(trades)
        g1 = gate1_is_screen(is_trades)
        print(
            f"  IS trades: {part_meta['is_trade_count']} | "
            f"boundary: {part_meta['is_oos_boundary_last_is_exit']} | "
            f"verdict: {g1['verdict']} (${g1['net_expectancy_per_trade']:.2f}/trade)",
            flush=True,
        )
        payload["hypotheses"][hid] = {
            "stopped": False,
            "total_trades": len(trades),
            "partition": part_meta,
            "oos_sealed_count": len(oos_trades),
            "harness": harness_dict,
            "gate1": g1,
            "operational_spec_ref": "docs/research-log.md P2-W2 pre-registration",
        }
        payload["summary"][hid] = {
            "verdict": g1["verdict"],
            "net_expectancy_per_trade": g1["net_expectancy_per_trade"],
            "is_trade_count": g1["is_trade_count"],
        }

    OUT_STEM.parent.mkdir(parents=True, exist_ok=True)
    json_path = OUT_STEM.with_suffix(".json")
    md_path = OUT_STEM.with_suffix(".md")
    json_path.write_text(json.dumps(_json_sanitize(payload), indent=2), encoding="utf-8")
    md_path.write_text(_render_md(payload), encoding="utf-8")
    print(f"\nWrote {json_path}")
    print(f"Wrote {md_path}")

    survivors = [
        hid
        for hid in HYPOTHESES
        if not payload["hypotheses"].get(hid, {}).get("stopped")
        and payload["hypotheses"][hid]["gate1"]["verdict"] == "SURVIVOR"
    ]
    print(f"\nSurvivors (Gate #1): {survivors or 'NONE'}")
    return 1 if any_stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
