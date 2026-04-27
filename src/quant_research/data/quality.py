"""Data-quality checks: missing-trading-day detection, OHLC spot-checks.

This module sits one layer above the loader and the session classifier
and answers two operator-facing questions:

1. *Are there trading days that PMC expects activity on but our local
   data has no bars for?* Cross-references PMC's ``CME_Equity``
   schedule with the calendar dates that contain bars. Gaps that the
   operator has previously acknowledged are listed as
   :data:`KNOWN_GAPS` and excluded from the "unexpected" list. New
   gaps surfacing from this function should either be investigated
   (re-export, vendor question) or appended to :data:`KNOWN_GAPS`
   with a note.

2. *Do the daily RTH OHLC values match an external reference such as
   TradingView?* :func:`compute_daily_rth_ohlc` produces a per-date
   OHLCV summary; :func:`spot_check_ohlc` is a thin convenience
   wrapper that picks a deterministic random subset for the operator
   to compare against TradingView.

The known-gap registry lives here as plain data rather than in the
session module because it is operator-curated knowledge about *this*
NT8 export, not a general property of the CME schedule. If we
re-export the data later, the registry should be re-derived from
empirical inspection rather than blindly trusted.

Empirical findings pinned by tests in ``tests/data/test_quality.py``
on the current dataset (2019-12-28 → 2026-04-17):

- 1,630 PMC trading days in range
- 61 PMC trading days have *no* bars on the calendar date itself
- All 61 fall inside the four pre-acknowledged regions in
  :data:`KNOWN_GAPS` — no unexpected gaps remain
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass
from typing import Final

import polars as pl

from quant_research.data import session


@dataclass(frozen=True)
class KnownGap:
    """A pre-acknowledged data gap.

    Represents an inclusive date range ``[start_date, end_date]``
    where PMC's ``CME_Equity`` calendar expects trading activity but
    the locally-available NT8 export contains no bars. Used by
    :func:`find_unexpected_missing_days` to subtract operator-known
    gaps from the surfaced missing-day list.
    """

    start_date: dt.date
    end_date: dt.date
    description: str

    def contains(self, date: dt.date) -> bool:
        """Return True iff ``date`` is in ``[start_date, end_date]`` inclusive."""
        return self.start_date <= date <= self.end_date


KNOWN_GAPS: Final[tuple[KnownGap, ...]] = (
    KnownGap(
        start_date=dt.date(2024, 3, 29),
        end_date=dt.date(2024, 3, 29),
        description=(
            "Good Friday 2024. PMC marks as a trading day (early close 08:15 "
            "CT, ~8h of bars expected on the calendar date). NT8 export "
            "contains no bars here; root cause not investigated."
        ),
    ),
    KnownGap(
        start_date=dt.date(2024, 6, 18),
        end_date=dt.date(2024, 7, 31),
        description=(
            "Jun-Jul 2024 export gap. 32 contiguous trading days with no "
            "bars in the NT8 export. Operator-acknowledged in the phase-1 "
            "plan; root cause not yet investigated."
        ),
    ),
    KnownGap(
        start_date=dt.date(2025, 4, 18),
        end_date=dt.date(2025, 4, 18),
        description=(
            "Good Friday 2025. Same shape as Good Friday 2024 — PMC marks "
            "as an 08:15 CT early-close trading day; NT8 export has no "
            "bars."
        ),
    ),
    KnownGap(
        start_date=dt.date(2026, 2, 3),
        end_date=dt.date(2026, 3, 11),
        description=(
            "Feb-Mar 2026 export gap. 27 contiguous trading days with no "
            "bars in the NT8 export. Operator-acknowledged in the phase-1 "
            "plan; root cause not yet investigated."
        ),
    ),
)
"""Operator-acknowledged data gaps in the local NT8 export.

Trading days inside any range here are excluded from
:func:`find_unexpected_missing_days`. Tests pin the count and span of
each region against the current dataset.
"""


def find_missing_trading_days(
    df: pl.DataFrame,
    *,
    calendar_name: str = session.CME_EQUITY_CALENDAR,
) -> list[dt.date]:
    """Return PMC trading days with no in-session bars on the calendar date.

    A "missing" trading day is a date that ``pandas_market_calendars``
    reports as a CME equity-index trading session, but for which no
    ``RTH`` or ``ETH`` bars exist on the calendar date in the input
    DataFrame. The check looks at the calendar date of each bar
    (after CT-tz normalization), not the trading-session-date — bars
    in Sunday's evening reopen still count under their Sunday
    calendar date, not Monday's session date.

    Args:
        df: Bars with at least a tz-aware ``timestamp`` column. The
            ``session`` column is added if missing (via
            :func:`session.classify_sessions`).
        calendar_name: PMC calendar identifier. Defaults to
            ``CME_Equity``.

    Returns:
        Sorted list of trading dates with no in-session bars.
    """
    if "session" not in df.columns:
        df = session.classify_sessions(df, calendar_name=calendar_name)

    if df.is_empty():
        return []

    min_date = df["timestamp"].min().date()  # type: ignore[union-attr]
    max_date = df["timestamp"].max().date()  # type: ignore[union-attr]

    schedule = session.get_cme_schedule(
        min_date,
        max_date,
        calendar_name=calendar_name,
    )
    pmc_dates = set(schedule["session_date"].to_list())

    bar_dates = set(
        df.filter(pl.col("session").is_in([session.SESSION_RTH, session.SESSION_ETH]))
        .select(pl.col("timestamp").dt.convert_time_zone(session.CT_TIMEZONE).dt.date().alias("d"))[
            "d"
        ]
        .unique()
        .to_list()
    )

    return sorted(pmc_dates - bar_dates)


def find_unexpected_missing_days(
    df: pl.DataFrame,
    *,
    known_gaps: tuple[KnownGap, ...] = KNOWN_GAPS,
    calendar_name: str = session.CME_EQUITY_CALENDAR,
) -> list[dt.date]:
    """Return missing trading days not covered by any :class:`KnownGap`.

    Wrapper around :func:`find_missing_trading_days` that subtracts
    pre-acknowledged operator-known gaps. A non-empty result means
    new gaps have surfaced and need either investigation or a new
    ``KNOWN_GAPS`` entry.

    Args:
        df: Bars with at least a tz-aware ``timestamp`` column.
        known_gaps: Iterable of :class:`KnownGap` ranges to subtract.
            Defaults to :data:`KNOWN_GAPS`.
        calendar_name: PMC calendar identifier.

    Returns:
        Sorted list of missing trading dates that fall outside every
        :class:`KnownGap` range.
    """
    missing = find_missing_trading_days(df, calendar_name=calendar_name)
    return [d for d in missing if not any(g.contains(d) for g in known_gaps)]


def compute_daily_rth_ohlc(df: pl.DataFrame) -> pl.DataFrame:
    """Aggregate per-date RTH OHLCV from minute bars.

    For each calendar date in CT, computes:

    - ``rth_open``: open of the first RTH bar of the day
    - ``rth_high``: max high across the day's RTH bars
    - ``rth_low``: min low across the day's RTH bars
    - ``rth_close``: close of the last RTH bar of the day
    - ``rth_volume``: sum of volume across the day's RTH bars
    - ``rth_bar_count``: count of RTH bars

    Bars outside the RTH window are ignored. The ``session`` column
    is added if missing.

    Args:
        df: Bars with tz-aware ``timestamp`` and OHLCV columns
            (``open``, ``high``, ``low``, ``close``, ``volume``).

    Returns:
        DataFrame indexed by ``date`` (one row per RTH-trading day),
        sorted ascending. Empty input -> empty output with the same
        schema.

    Raises:
        ValueError: If required OHLCV columns are missing.
    """
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing_cols = required - set(df.columns)
    if missing_cols:
        raise ValueError(f"missing required columns: {sorted(missing_cols)}")

    if "session" not in df.columns:
        df = session.classify_sessions(df)

    rth = (
        df.filter(pl.col("session") == session.SESSION_RTH)
        .with_columns(
            pl.col("timestamp").dt.convert_time_zone(session.CT_TIMEZONE).dt.date().alias("date")
        )
        .sort("timestamp")
    )

    if rth.is_empty():
        return pl.DataFrame(
            schema={
                "date": pl.Date,
                "rth_open": pl.Float64,
                "rth_high": pl.Float64,
                "rth_low": pl.Float64,
                "rth_close": pl.Float64,
                "rth_volume": pl.Int64,
                "rth_bar_count": pl.UInt32,
            }
        )

    return (
        rth.group_by("date")
        .agg(
            pl.col("open").first().alias("rth_open"),
            pl.col("high").max().alias("rth_high"),
            pl.col("low").min().alias("rth_low"),
            pl.col("close").last().alias("rth_close"),
            pl.col("volume").sum().alias("rth_volume"),
            pl.len().alias("rth_bar_count"),
        )
        .sort("date")
    )


def spot_check_ohlc(
    df: pl.DataFrame,
    *,
    n_dates: int = 5,
    seed: int | None = 42,
) -> pl.DataFrame:
    """Return per-date RTH OHLCV for a deterministic random sample of dates.

    Operator workflow: run this, eyeball the OHLC values against
    TradingView (or the broker's chart) for the same dates and
    instrument. Mismatches flag a contract-mapping or data-quality
    issue.

    Only RTH-classified bars are aggregated, and only dates with the
    standard 390 RTH bars are sampled, so each row should correspond
    to a "normal" full-RTH session that's easy to verify.

    Args:
        df: Bars with tz-aware ``timestamp`` and OHLCV columns.
        n_dates: Number of dates to sample.
        seed: Seed for ``random.Random`` so consecutive runs return
            the same sample. ``None`` for non-deterministic.

    Returns:
        DataFrame of ``n_dates`` rows (or fewer if the dataset has
        fewer normal-RTH days), sorted by ``date`` ascending.
    """
    daily = compute_daily_rth_ohlc(df)
    full_days = daily.filter(pl.col("rth_bar_count") == 390)
    if full_days.height == 0:
        return daily.head(0)

    rng = random.Random(seed)
    dates = full_days["date"].to_list()
    sample = rng.sample(dates, k=min(n_dates, len(dates)))
    return full_days.filter(pl.col("date").is_in(sample)).sort("date")
