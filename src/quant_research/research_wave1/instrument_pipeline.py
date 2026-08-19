"""Continuous-contract + RTH session pipeline for MNQ-style NT8 equity-index exports."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from quant_research.data import continuous_contract, data_loader, session
from quant_research.data.session import SESSION_RTH


def instrument_raw_coverage(
    data_root: str | Path,
    *,
    pattern: str,
    timezone: str = data_loader.CME_TIMEZONE,
) -> dict[str, Any]:
    """Summarize locally available raw contract files for one instrument glob.

    Returns filename count, inferred contract quarters, wall-clock spans (CT),
    and whether any paths were found — used to document Phase 2 cross-feature
    data gaps without requiring successful loads.
    """
    root = Path(data_root)
    paths = data_loader.discover_contract_files(root, pattern=pattern)
    if not paths:
        return {
            "pattern": pattern,
            "contract_file_count": 0,
            "contract_symbols": [],
            "ct_first_bar": None,
            "ct_last_bar": None,
            "note": "no matching files under data_root",
        }
    dfs = [data_loader.load_contract_file(p, timezone=timezone)[["timestamp"]] for p in paths]

    concat = (
        pl.concat(dfs, how="vertical").sort("timestamp")
        if len(dfs) > 1
        else dfs[0].sort("timestamp")
    )
    return {
        "pattern": pattern,
        "contract_file_count": len(paths),
        "contract_symbols": continuous_contract.sort_contracts_chronologically(
            [_contract_symbol_from_filename(p) for p in paths]
        ),
        "ct_first_bar": concat["timestamp"].min(),
        "ct_last_bar": concat["timestamp"].max(),
    }


def _contract_symbol_from_filename(path: Path) -> str:
    return path.name.removesuffix(".Last.txt")


def load_continuous_rth_mnq_style(
    data_root: str | Path,
    *,
    pattern: str,
    protocol_start: dt.date,
    protocol_end_inclusive: dt.date,
    timezone: str = data_loader.CME_TIMEZONE,
) -> pl.DataFrame:
    """Load contracts, build continuous series, keep RTH bars in the protocol window.

    Mirrors the MNQ path in ``scripts/run_m6_orb_baseline.py`` (continuous +
    session classification + ``cme_session_date`` + RTH filter + date slice).

    Args:
        data_root: Directory containing ``*.Last.txt`` exports (usually
            ``<repo>/data/raw``).
        pattern: Glob relative to ``data_root`` (e.g. :data:`data_loader.ES_CONTRACT_GLOB`).
        protocol_start: First calendar date (Chicago) to include.
        protocol_end_inclusive: Last calendar date (Chicago) to include.
        timezone: Wall-clock timezone for bars (default CME / Chicago).

    Returns:
        Sorted RTH ``DataFrame`` with canonical OHLCV columns, ``session``,
        ``cme_session_date``, ``timestamp`` tz-aware. Empty schema-equivalent
        frame when no files match ``pattern``.
    """
    root = Path(data_root)
    paths = data_loader.discover_contract_files(root, pattern=pattern)
    if not paths:
        return pl.DataFrame(
            schema={
                "timestamp": pl.Datetime("us", timezone),
                "open": pl.Float64,
                "high": pl.Float64,
                "low": pl.Float64,
                "close": pl.Float64,
                "volume": pl.Int64,
                "contract_symbol": pl.String,
                "session": pl.String,
                "cme_session_date": pl.Date,
            }
        )

    raw = data_loader.load_contracts(paths, timezone=timezone)
    cont = continuous_contract.build_continuous_contract(raw)
    cls = session.classify_sessions(cont)
    dated = session.assign_cme_session_date(cls)
    rth = dated.filter(pl.col("session") == SESSION_RTH)

    ts0 = dt.datetime.combine(protocol_start, dt.time.min).replace(tzinfo=ZoneInfo(timezone))
    ts_end_excl = dt.datetime.combine(
        protocol_end_inclusive + dt.timedelta(days=1),
        dt.time.min,
    ).replace(tzinfo=ZoneInfo(timezone))

    return rth.filter((pl.col("timestamp") >= ts0) & (pl.col("timestamp") < ts_end_excl)).sort(
        "timestamp"
    )
