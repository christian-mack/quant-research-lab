"""Opening range (OR) high / low for the first *N* minutes of RTH.

For each PMC ``cme_session_date`` (see :func:`quant_research.data.session.assign_cme_session_date`),
take all bars labeled ``RTH`` whose Chicago wall-clock time falls in
``[08:30, 08:30 + duration)``. The opening-range high is the max
``high`` and the low is the min ``low`` over those bars.

The resulting ``or_high`` / ``or_low`` are joined back to **every** row
sharing the same ``cme_session_date`` (including overnight ``ETH`` bars
that belong to the same session). That implies **lookahead** for bars
timestamped before the OR window ends — standard in end-of-day research,
but intraday strategies that must not see future OR should filter to
``timestamp >= or_end`` outside this module.

Requires ``session`` (from :func:`quant_research.data.session.classify_sessions`)
and ``cme_session_date``. Both are added automatically if absent.

API shape matches :mod:`quant_research.indicators.vwap` (wrapper-first;
grouped aggregates don't fit a pure per-row ``expr`` factory cleanly).
"""

from __future__ import annotations

from typing import Final

import polars as pl

from quant_research.data import session as session_mod

RTH_OPEN_HOUR: Final[int] = 8
RTH_OPEN_MINUTE: Final[int] = 30
DEFAULT_OR_MINUTES: Final[int] = 30


def add_opening_range(
    df: pl.DataFrame,
    *,
    duration_minutes: int = DEFAULT_OR_MINUTES,
    timestamp: str = "timestamp",
    high: str = "high",
    low: str = "low",
    calendar_name: str = session_mod.CME_EQUITY_CALENDAR,
    session_col: str = "session",
    session_date_col: str = "cme_session_date",
    or_high: str = "or_high",
    or_low: str = "or_low",
) -> pl.DataFrame:
    """Append opening-range high and low columns keyed by ``cme_session_date``."""
    if duration_minutes < 1:
        raise ValueError(f"`duration_minutes` must be >= 1; got {duration_minutes}")
    missing = [c for c in (timestamp, high, low) if c not in df.columns]
    if missing:
        raise ValueError(f"missing required columns: {missing}")

    out = df.sort(timestamp)
    if session_col not in out.columns:
        out = session_mod.classify_sessions(out, calendar_name=calendar_name)
    if session_date_col not in out.columns:
        out = session_mod.assign_cme_session_date(
            out, calendar_name=calendar_name, output=session_date_col
        )

    ct = pl.col(timestamp).dt.convert_time_zone(session_mod.CT_TIMEZONE)
    tsec = (
        ct.dt.hour().cast(pl.Int64) * 3600
        + ct.dt.minute().cast(pl.Int64) * 60
        + ct.dt.second().cast(pl.Int64)
    )
    rth_open_sec = RTH_OPEN_HOUR * 3600 + RTH_OPEN_MINUTE * 60
    win_end = rth_open_sec + duration_minutes * 60
    in_window = (
        (pl.col(session_col) == session_mod.SESSION_RTH)
        & pl.col(session_date_col).is_not_null()
        & (tsec >= rth_open_sec)
        & (tsec < win_end)
    )

    or_levels = (
        out.filter(in_window)
        .group_by(session_date_col)
        .agg(
            pl.col(high).max().alias(or_high),
            pl.col(low).min().alias(or_low),
        )
    )
    return out.join(or_levels, on=session_date_col, how="left")
