"""Primitive 1 — PD-array / level marking (PDH, PDL, prior-day EQ).

Computes the daily reference levels the ICT daily-bias module and the Spec A
liquidity-sweep detector use:

- **PDH** — prior-day high.
- **PDL** — prior-day low.
- **Prior-day EQ** — the 50% level of the prior-day range, ``(PDH + PDL) / 2``.

"Day" here is the CME equity-index trading session keyed by
:func:`quant_research.data.session.assign_cme_session_date`
(``cme_session_date``). Using the PMC session key (17:00 prev → 16:00 close,
RTH subset) rather than a naive calendar date keeps these levels consistent
with the rest of the pipeline (lessons-log 2026-04-27 UTC→CT discovery: the
session key, not wall-clock calendar date, is the correct daily grouping).

Two-step API
------------
1. :func:`daily_pd_arrays` aggregates bars to one row **per session date** with
   day OHLC and the prior-day reference levels (``pdh``/``pdl``/``p_eq``). The
   first session in the data has null reference levels (no prior day) — this is
   the documented first-day-of-data edge case.
2. :func:`add_pd_arrays` left-joins those prior-day levels back onto the
   original (e.g. intraday) bars by session date, so every bar carries the
   reference levels for its own session.

The prior-day levels attached to session ``D`` are computed only from sessions
strictly before ``D``, so there is **no look-ahead**: at any bar inside session
``D`` the PDH/PDL/EQ were fully known at session ``D``'s open.
"""

from __future__ import annotations

from typing import Final

import polars as pl

from quant_research.data import session as session_mod

DEFAULT_SESSION_DATE_COL: Final[str] = "cme_session_date"
DEFAULT_TIMESTAMP_COL: Final[str] = "timestamp"

PDH_COL: Final[str] = "pdh"
PDL_COL: Final[str] = "pdl"
PRIOR_EQ_COL: Final[str] = "p_eq"


def daily_pd_arrays(
    df: pl.DataFrame,
    *,
    session_date_col: str = DEFAULT_SESSION_DATE_COL,
    timestamp: str = DEFAULT_TIMESTAMP_COL,
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
    calendar_name: str = session_mod.CME_EQUITY_CALENDAR,
) -> pl.DataFrame:
    """Aggregate bars to daily OHLC and attach prior-day PDH/PDL/EQ.

    Bars are grouped by ``session_date_col``. ``cme_session_date`` is added via
    :func:`quant_research.data.session.assign_cme_session_date` if absent. Within
    each session: ``day_open`` is the first bar's open by ``timestamp``,
    ``day_close`` the last bar's close, ``day_high`` the max high, ``day_low`` the
    min low. Rows with a null session date (maintenance break / weekend / holiday
    bars) are dropped before aggregation — they are not part of an open session.

    The prior-day reference levels for session ``D`` are the previous session's
    ``day_high`` (``pdh``), ``day_low`` (``pdl``), and ``(pdh + pdl) / 2``
    (``p_eq``). The earliest session has null ``pdh``/``pdl``/``p_eq``.

    Args:
        df: Bars with ``high``/``low``/``open``/``close`` columns and either a
            ``session_date_col`` or a tz-aware ``timestamp`` column (used to
            derive the session date and to order open/close).
        session_date_col: Per-session grouping key (``cme_session_date``).
        timestamp: Tz-aware timestamp column, used to order first/last for
            ``day_open``/``day_close`` and to assign session dates if needed.
        open_: Open price column name.
        high: High price column name.
        low: Low price column name.
        close: Close price column name.
        calendar_name: PMC calendar used if session dates must be assigned.

    Returns:
        One row per session date, sorted ascending by ``session_date_col``, with
        columns ``[session_date_col, day_open, day_high, day_low, day_close,
        pdh, pdl, p_eq]``.

    Raises:
        ValueError: If required price columns are missing, or if neither a
            session-date column nor a usable ``timestamp`` column is present.
    """
    missing = [c for c in (open_, high, low, close) if c not in df.columns]
    if missing:
        raise ValueError(f"missing required price columns: {missing}")

    out = df
    if session_date_col not in out.columns:
        if timestamp not in out.columns:
            raise ValueError(
                f"need either `{session_date_col}` or a tz-aware `{timestamp}` column"
            )
        out = session_mod.assign_cme_session_date(
            out, calendar_name=calendar_name, output=session_date_col
        )

    if timestamp not in out.columns:
        raise ValueError(f"`{timestamp}` column is required to order day open/close")

    daily = (
        out.filter(pl.col(session_date_col).is_not_null())
        .sort(timestamp)
        .group_by(session_date_col)
        .agg(
            pl.col(open_).first().alias("day_open"),
            pl.col(high).max().alias("day_high"),
            pl.col(low).min().alias("day_low"),
            pl.col(close).last().alias("day_close"),
        )
        .sort(session_date_col)
    )

    return daily.with_columns(
        pl.col("day_high").shift(1).alias(PDH_COL),
        pl.col("day_low").shift(1).alias(PDL_COL),
    ).with_columns(
        ((pl.col(PDH_COL) + pl.col(PDL_COL)) / 2.0).alias(PRIOR_EQ_COL),
    )


def add_pd_arrays(
    df: pl.DataFrame,
    *,
    session_date_col: str = DEFAULT_SESSION_DATE_COL,
    timestamp: str = DEFAULT_TIMESTAMP_COL,
    open_: str = "open",
    high: str = "high",
    low: str = "low",
    close: str = "close",
    calendar_name: str = session_mod.CME_EQUITY_CALENDAR,
) -> pl.DataFrame:
    """Attach prior-day PDH/PDL/EQ to every input bar by session date.

    Convenience wrapper that computes :func:`daily_pd_arrays` and left-joins the
    ``pdh``/``pdl``/``p_eq`` columns back onto the original bars on
    ``session_date_col``. Bars in the first session (or with a null session
    date) carry null reference levels. Original columns and row count are
    preserved; output is sorted by ``timestamp`` when present, else by
    ``session_date_col``.

    Args:
        df: Bars to annotate (typically intraday RTH bars from the pipeline).
        session_date_col: Per-session grouping key.
        timestamp: Tz-aware timestamp column (for ordering / session assignment).
        open_: Open price column name.
        high: High price column name.
        low: Low price column name.
        close: Close price column name.
        calendar_name: PMC calendar used if session dates must be assigned.

    Returns:
        ``df`` with ``pdh``/``pdl``/``p_eq`` appended.
    """
    out = df
    if session_date_col not in out.columns:
        if timestamp not in out.columns:
            raise ValueError(
                f"need either `{session_date_col}` or a tz-aware `{timestamp}` column"
            )
        out = session_mod.assign_cme_session_date(
            out, calendar_name=calendar_name, output=session_date_col
        )

    daily = daily_pd_arrays(
        out,
        session_date_col=session_date_col,
        timestamp=timestamp,
        open_=open_,
        high=high,
        low=low,
        close=close,
        calendar_name=calendar_name,
    ).select(session_date_col, PDH_COL, PDL_COL, PRIOR_EQ_COL)

    joined = out.join(daily, on=session_date_col, how="left")
    if timestamp in joined.columns:
        return joined.sort(timestamp)
    return joined.sort(session_date_col)
