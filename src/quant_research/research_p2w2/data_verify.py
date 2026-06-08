"""Hard-stop MNQ dataset verification for P2-W2 (no silent fallback)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from quant_research.data import data_loader
from quant_research.research_wave1.instrument_pipeline import load_continuous_rth_mnq_style

PROTOCOL_START = dt.date(2020, 1, 1)
PROTOCOL_END = dt.date(2026, 4, 19)
MIN_CONTRACT_FILES = 20
MIN_RTH_BARS = 500_000
MIN_SESSION_DATES = 1_400


@dataclass(frozen=True, slots=True)
class MnqDatasetReport:
    """Resolved MNQ load metadata."""

    data_root: Path
    pattern: str
    contract_files: tuple[str, ...]
    contract_file_count: int
    rth_bar_count: int
    session_date_count: int
    first_bar_ct: dt.datetime | None
    last_bar_ct: dt.datetime | None
    first_session: dt.date | None
    last_session: dt.date | None
    passed: bool
    failure_reason: str | None


def verify_mnq_dataset(data_root: Path) -> MnqDatasetReport:
    """Load MNQ from raw exports only; fail if missing or undersized."""
    pattern = data_loader.MNQ_CONTRACT_GLOB
    paths = data_loader.discover_contract_files(data_root, pattern=pattern)
    rel_paths = tuple(str(p.relative_to(data_root)).replace("\\", "/") for p in paths)

    if not paths:
        return MnqDatasetReport(
            data_root=data_root,
            pattern=pattern,
            contract_files=(),
            contract_file_count=0,
            rth_bar_count=0,
            session_date_count=0,
            first_bar_ct=None,
            last_bar_ct=None,
            first_session=None,
            last_session=None,
            passed=False,
            failure_reason=(
                f"No files matching {pattern!r} under {data_root}. "
                "Refusing silent Wave-0-artifact fallback."
            ),
        )

    rth = load_continuous_rth_mnq_style(
        data_root,
        pattern=pattern,
        protocol_start=PROTOCOL_START,
        protocol_end_inclusive=PROTOCOL_END,
    )
    bar_count = rth.height
    sessions = (
        rth["cme_session_date"].drop_nulls().unique().sort().to_list()
        if bar_count
        else []
    )
    first_bar = rth["timestamp"].min() if bar_count else None
    last_bar = rth["timestamp"].max() if bar_count else None
    first_sess = sessions[0] if sessions else None
    last_sess = sessions[-1] if sessions else None

    failures: list[str] = []
    if len(paths) < MIN_CONTRACT_FILES:
        failures.append(f"contract_files={len(paths)} < {MIN_CONTRACT_FILES}")
    if bar_count < MIN_RTH_BARS:
        failures.append(f"rth_bars={bar_count} < {MIN_RTH_BARS}")
    if len(sessions) < MIN_SESSION_DATES:
        failures.append(f"session_dates={len(sessions)} < {MIN_SESSION_DATES}")
    if first_sess is None or first_sess > dt.date(2020, 1, 15):
        failures.append(f"first_session={first_sess} too late (expected ~2020-01)")
    if last_sess is None or last_sess < dt.date(2026, 3, 1):
        failures.append(f"last_session={last_sess} too early (expected ~2026-04)")

    return MnqDatasetReport(
        data_root=data_root,
        pattern=pattern,
        contract_files=rel_paths,
        contract_file_count=len(paths),
        rth_bar_count=bar_count,
        session_date_count=len(sessions),
        first_bar_ct=first_bar,
        last_bar_ct=last_bar,
        first_session=first_sess,
        last_session=last_sess,
        passed=len(failures) == 0,
        failure_reason="; ".join(failures) if failures else None,
    )


def load_verified_mnq_rth(data_root: Path) -> tuple[pl.DataFrame, MnqDatasetReport]:
    """Verify dataset then return RTH bars; raises on failure."""
    report = verify_mnq_dataset(data_root)
    if not report.passed:
        msg = report.failure_reason or "MNQ dataset verification failed"
        raise RuntimeError(msg)
    rth = load_continuous_rth_mnq_style(
        data_root,
        pattern=data_loader.MNQ_CONTRACT_GLOB,
        protocol_start=PROTOCOL_START,
        protocol_end_inclusive=PROTOCOL_END,
    )
    return rth, report
