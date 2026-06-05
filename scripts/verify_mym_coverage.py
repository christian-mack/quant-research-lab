"""Wave 1 Track 2 data-prep: process MYM through the MNQ-style pipeline and verify coverage.

Runs MYM (Micro Dow) through the same continuous-contract + RTH session pipeline as
MNQ/MES, then reports coverage and cross-instrument overlap so SMT (Primitive 4) can
decide MNQ-vs-MES-vs-MYM vs an MES-only fallback.

Outputs (per ai-project-instructions Section 4 / research-log convention):
  - earliest/latest RTH timestamp, total RTH bar count per instrument
  - unique CME session-date count per instrument
  - whether MYM covers the operator-known MNQ export gaps and any MYM-specific gaps
  - overlapping session count across MNQ/MES/MYM (inner join) and MNQ/MES only

Run: ``uv run python scripts/verify_mym_coverage.py``
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

from quant_research.data import data_loader
from quant_research.research_wave1.instrument_pipeline import load_continuous_rth_mnq_style

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data" / "raw"

PROTOCOL_START = dt.date(2020, 1, 1)
PROTOCOL_END = dt.date(2026, 6, 30)

# Operator-known MNQ export gaps (ai-project-instructions Section 7 / lessons-log 2026-04-26).
KNOWN_MNQ_GAPS = [
    (dt.date(2024, 6, 18), dt.date(2024, 7, 31)),
    (dt.date(2026, 2, 3), dt.date(2026, 3, 11)),
]


def session_dates(df: pl.DataFrame) -> set[dt.date]:
    return set(df["cme_session_date"].unique().to_list())


def coverage_summary(name: str, df: pl.DataFrame) -> dict:
    sd = sorted(session_dates(df))
    return {
        "instrument": name,
        "rth_bar_count": df.height,
        "ct_first_bar": str(df["timestamp"].min()),
        "ct_last_bar": str(df["timestamp"].max()),
        "n_session_dates": len(sd),
        "first_session_date": str(sd[0]) if sd else None,
        "last_session_date": str(sd[-1]) if sd else None,
    }


def session_gaps(df: pl.DataFrame, max_report: int = 25) -> list[dict]:
    """Find calendar gaps > 4 days between consecutive RTH session dates."""
    sd = sorted(session_dates(df))
    gaps = []
    for prev, cur in zip(sd, sd[1:], strict=False):
        delta = (cur - prev).days
        if delta > 4:
            gaps.append({"from": str(prev), "to": str(cur), "calendar_days": delta})
    return sorted(gaps, key=lambda g: -g["calendar_days"])[:max_report]


def main() -> None:
    frames: dict[str, pl.DataFrame] = {}
    for name, pattern in [
        ("MNQ", data_loader.MNQ_CONTRACT_GLOB),
        ("MES", data_loader.MES_CONTRACT_GLOB),
        ("MYM", data_loader.MYM_CONTRACT_GLOB),
    ]:
        print(f"Loading {name} ({pattern}) ...", flush=True)
        frames[name] = load_continuous_rth_mnq_style(
            DATA_ROOT,
            pattern=pattern,
            protocol_start=PROTOCOL_START,
            protocol_end_inclusive=PROTOCOL_END,
        )

    summaries = {name: coverage_summary(name, df) for name, df in frames.items()}

    sd_mnq = session_dates(frames["MNQ"])
    sd_mes = session_dates(frames["MES"])
    sd_mym = session_dates(frames["MYM"])

    overlap_all = sd_mnq & sd_mes & sd_mym
    overlap_mnq_mes = sd_mnq & sd_mes
    overlap_mnq_mym = sd_mnq & sd_mym

    # Does MYM cover the operator-known MNQ export gaps?
    mym_covers_known_gaps = []
    for g0, g1 in KNOWN_MNQ_GAPS:
        in_gap = sorted(d for d in sd_mym if g0 <= d <= g1)
        mym_covers_known_gaps.append(
            {
                "mnq_gap": [str(g0), str(g1)],
                "mym_session_dates_in_window": len(in_gap),
                "mym_covers": len(in_gap) > 0,
            }
        )

    # MYM session dates missing relative to MNQ within the shared span (MYM-specific holes).
    shared_lo = max(min(sd_mnq), min(sd_mym))
    shared_hi = min(max(sd_mnq), max(sd_mym))
    mnq_in_span = {d for d in sd_mnq if shared_lo <= d <= shared_hi}
    mym_in_span = {d for d in sd_mym if shared_lo <= d <= shared_hi}
    mym_missing_vs_mnq = sorted(mnq_in_span - mym_in_span)
    mnq_missing_vs_mym = sorted(mym_in_span - mnq_in_span)

    report = {
        "protocol_window": [str(PROTOCOL_START), str(PROTOCOL_END)],
        "summaries": summaries,
        "gaps": {name: session_gaps(df) for name, df in frames.items()},
        "overlap": {
            "mnq_mes_mym_inner": len(overlap_all),
            "mnq_mes_inner": len(overlap_mnq_mes),
            "mnq_mym_inner": len(overlap_mnq_mym),
        },
        "mym_covers_known_mnq_gaps": mym_covers_known_gaps,
        "shared_span_mnq_mym": [str(shared_lo), str(shared_hi)],
        "mym_missing_vs_mnq_count": len(mym_missing_vs_mnq),
        "mym_missing_vs_mnq_sample": [str(d) for d in mym_missing_vs_mnq[:30]],
        "mnq_missing_vs_mym_count": len(mnq_missing_vs_mym),
        "mnq_missing_vs_mym_sample": [str(d) for d in mnq_missing_vs_mym[:30]],
    }

    print(json.dumps(report, indent=2))
    out = REPO_ROOT / "scripts" / "_mym_coverage_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
