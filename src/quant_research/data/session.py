"""Session classification for CME equity-index futures bars.

Adds a ``session`` label to each bar, partitioning the 24/7 timeline into
five exhaustive, mutually-exclusive categories:

- ``RTH`` — *Regular Trading Hours.* Mon-Fri, ``08:30 <= time < 15:00`` CT,
  inside an open trading session. The classic "pit hours" window for
  equity-index futures.
- ``ETH`` — *Extended Trading Hours.* Inside an open trading session but
  outside the RTH window. Covers overnight (17:00 prev → 08:30) and the
  post-RTH stub (15:00 → 16:00) on weekdays, plus Sunday-evening
  reopens.
- ``BREAK`` — *Daily maintenance break.* ``16:00 <= time < 17:00`` CT on
  Mon-Thu between two adjacent normal-close trading sessions. CME
  Globex is fully halted in this window for /ES, /NQ and other
  equity-index futures. Friday 16:00 CT is the start of the weekly
  closure, not a maintenance break, so it classifies as ``WEEKEND``.
- ``WEEKEND`` — *Normal weekend closure.* Friday 16:00 CT through Sunday
  17:00 CT on weeks where the next session opens Sunday evening as
  usual. If a Monday holiday extends the closure, only the
  Friday-16:00 → Sunday-17:00 portion is ``WEEKEND``; the post-Sunday
  17:00 closure portion is ``HOLIDAY`` (since on a normal week the
  Monday session would already have started).
- ``HOLIDAY`` — *Any other out-of-session weekday closure.* Full holiday
  closes (Christmas Day, Thanksgiving Day, etc.), the post-early-close
  hours of shortened sessions (e.g., 12:01-15:59 CT on Black Friday),
  and the closed portion of holiday-extended weekends past Sunday
  17:00.

Holiday and early-close knowledge comes from
`pandas_market_calendars <https://pandas-market-calendars.readthedocs.io/>`_
via the ``CME_Equity`` calendar. We deliberately do **not** hard-code
the CME holiday schedule — the library is well-maintained, handles
shifted-observance dates and early closes, and means this module
doesn't carry an encoded calendar that has to be updated yearly.

Algorithm
---------
1. Pull the CME equity-index futures schedule for the data's date range
   (with a 2-day buffer on each side) from ``pandas_market_calendars``.
   Each row is one trading session, with ``market_open`` and
   ``market_close`` in tz-aware UTC; we convert both to CT for
   comparisons.
2. As-of join each bar to the most recent session whose
   ``market_open`` ≤ bar timestamp. This gives every bar a candidate
   "current session" (or ``null`` for bars before the schedule
   starts — should never happen given the buffer). A bar is treated
   as in-session iff ``market_open <= ts < market_close``
   (half-open). The bar timestamped exactly at the close belongs to
   the post-close window — on a normal day that means ``BREAK``, on
   an early-close day that means ``HOLIDAY``.
3. Decide ``RTH``/``ETH``/``BREAK``/``WEEKEND``/``HOLIDAY`` from the
   bar's wall-clock time, day-of-week, and the candidate session's
   open/close. Rules are vectorized polars expressions; see
   :func:`classify_sessions` for the full ``when/then/otherwise`` chain.

Edge cases handled and tested
-----------------------------
- Spring-forward and fall-back DST transitions (both happen on
  weekend Sundays, fully inside the WEEKEND window — no impact on
  classification).
- Early-close days (Black Friday, Christmas Eve, day before
  Independence Day if observed): bars after 12:00 CT on the
  early-close day are classified ``HOLIDAY`` (the session ended
  early; subsequent hours are not a routine break).
- Full holiday closes: Christmas Day, Thanksgiving Day, etc.
- Holiday-extended weekends: a Monday holiday means Sunday-17:00
  through Monday-17:00 is ``HOLIDAY``, not ``WEEKEND``.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

import pandas_market_calendars as mcal
import polars as pl

CME_EQUITY_CALENDAR: Final[str] = "CME_Equity"
"""``pandas_market_calendars`` calendar name for CME equity-index futures."""

CT_TIMEZONE: Final[str] = "America/Chicago"
"""Internal classification timezone. Bars are converted to CT for the
time-of-day comparisons (RTH window, maintenance-break window, etc.)
because all CME equity-index session boundaries are documented in CT.
"""

RTH_OPEN: Final[dt.time] = dt.time(8, 30)
"""Start of CME equity-index Regular Trading Hours, in CT."""

RTH_CLOSE: Final[dt.time] = dt.time(15, 0)
"""End of CME equity-index Regular Trading Hours, in CT."""

NORMAL_SESSION_CLOSE: Final[dt.time] = dt.time(16, 0)
"""Standard daily session close, in CT. Sessions closing earlier are
treated as early-close days and bars past the early close are labeled
``HOLIDAY``."""

NEXT_SESSION_OPEN: Final[dt.time] = dt.time(17, 0)
"""Standard next-session open, in CT. The 16:00-17:00 weekday window
between two normal-close sessions is the daily maintenance ``BREAK``."""

WEEKEND_START: Final[dt.time] = dt.time(16, 0)
"""On Friday, the start of normal weekend closure (in CT)."""

SESSION_RTH: Final[str] = "RTH"
SESSION_ETH: Final[str] = "ETH"
SESSION_BREAK: Final[str] = "BREAK"
SESSION_WEEKEND: Final[str] = "WEEKEND"
SESSION_HOLIDAY: Final[str] = "HOLIDAY"

ALL_SESSIONS: Final[tuple[str, ...]] = (
    SESSION_RTH,
    SESSION_ETH,
    SESSION_BREAK,
    SESSION_WEEKEND,
    SESSION_HOLIDAY,
)
"""Exhaustive set of ``session`` labels :func:`classify_sessions` may emit."""


def get_cme_schedule(
    start_date: dt.date,
    end_date: dt.date,
    *,
    calendar_name: str = CME_EQUITY_CALENDAR,
    timezone: str = CT_TIMEZONE,
) -> pl.DataFrame:
    """Return the CME equity-index trading-session schedule as a polars DataFrame.

    Thin wrapper around ``pandas_market_calendars`` with conversion to
    polars and to the requested timezone. The returned columns are:

    - ``session_date`` (``Date``) — calendar date the session is keyed
      on by the calendar (typically the date the session closes; for
      equity-index futures sessions span 17:00 prev → 16:00 ``session_date``).
    - ``market_open`` (tz-aware ``Datetime`` in ``timezone``) — the
      session's open. Standard value is 17:00 CT on ``session_date - 1``.
    - ``market_close`` (tz-aware ``Datetime`` in ``timezone``) — the
      session's close. Standard value is 16:00 CT on ``session_date``;
      early-close days will be earlier (typically 12:00 CT).

    Args:
        start_date: First date to include (inclusive).
        end_date: Last date to include (inclusive).
        calendar_name: ``pandas_market_calendars`` calendar identifier.
            Defaults to :data:`CME_EQUITY_CALENDAR`.
        timezone: IANA timezone for the output ``market_open`` /
            ``market_close`` columns. Defaults to :data:`CT_TIMEZONE`.

    Returns:
        DataFrame sorted by ``market_open`` ascending.
    """
    cal = mcal.get_calendar(calendar_name)
    sched_pd = cal.schedule(start_date=start_date, end_date=end_date)
    sched_pd = sched_pd.reset_index().rename(columns={"index": "session_date"})
    sched_pd["session_date"] = sched_pd["session_date"].dt.date
    return (
        pl.from_pandas(sched_pd[["session_date", "market_open", "market_close"]])
        .with_columns(
            pl.col("market_open").dt.convert_time_zone(timezone),
            pl.col("market_close").dt.convert_time_zone(timezone),
        )
        .sort("market_open")
    )


def classify_sessions(
    df: pl.DataFrame,
    *,
    calendar_name: str = CME_EQUITY_CALENDAR,
) -> pl.DataFrame:
    """Add a ``session`` column to ``df`` partitioning bars by session type.

    Input ``df`` must have a tz-aware ``timestamp`` column (any IANA
    timezone — internally converted to CT for classification). All
    other columns are passed through unchanged. The output is sorted
    by ``timestamp`` ascending.

    The classification scheme is documented in the module docstring.
    Briefly:

    - ``RTH`` / ``ETH`` for bars inside an open trading session
    - ``BREAK`` for the daily 16:00-17:00 CT maintenance halt between
      two normal-close weekday sessions
    - ``WEEKEND`` for the normal Friday 16:00 → Sunday 17:00 closure
    - ``HOLIDAY`` for everything else outside an open session
      (full-day holidays, post-early-close hours, holiday-extended
      weekend portions)

    Args:
        df: Bars with a tz-aware ``timestamp`` column.
        calendar_name: ``pandas_market_calendars`` calendar to use for
            session/holiday lookup. Defaults to :data:`CME_EQUITY_CALENDAR`.

    Returns:
        New DataFrame: original columns + ``session`` (``String``),
        sorted by ``timestamp`` ascending. Rows are not added or
        dropped.

    Raises:
        ValueError: If ``timestamp`` is missing, naive, or not a
            ``Datetime`` column.
    """
    if "timestamp" not in df.columns:
        raise ValueError("`df` must have a `timestamp` column")
    ts_dtype = df.schema["timestamp"]
    if not isinstance(ts_dtype, pl.Datetime):
        raise ValueError(f"`timestamp` must be a Datetime column; got {ts_dtype}")
    if ts_dtype.time_zone is None:
        raise ValueError(
            "`timestamp` must be tz-aware. The session classifier needs an "
            "absolute time reference; pass data through the loader (which "
            "tags with America/Chicago) or call `replace_time_zone(...)` "
            "before classifying."
        )

    if df.is_empty():
        return df.with_columns(pl.lit(None, dtype=pl.String).alias("session"))

    sorted_df = df.sort("timestamp")

    min_ts = sorted_df["timestamp"].min()
    max_ts = sorted_df["timestamp"].max()
    assert min_ts is not None and max_ts is not None
    schedule = get_cme_schedule(
        min_ts.date() - dt.timedelta(days=2),
        max_ts.date() + dt.timedelta(days=2),
        calendar_name=calendar_name,
        timezone=ts_dtype.time_zone,
    )

    joined = sorted_df.join_asof(
        schedule.select("market_open", "market_close"),
        left_on="timestamp",
        right_on="market_open",
        strategy="backward",
    ).with_columns(
        pl.col("timestamp").dt.convert_time_zone(CT_TIMEZONE).alias("_ts_ct"),
        pl.col("market_close").dt.convert_time_zone(CT_TIMEZONE).alias("_market_close_ct"),
    )

    in_session = (
        pl.col("market_open").is_not_null()
        & (pl.col("timestamp") >= pl.col("market_open"))
        & (pl.col("timestamp") < pl.col("market_close"))
    )

    weekday_ct = pl.col("_ts_ct").dt.weekday()
    time_ct = pl.col("_ts_ct").dt.time()

    is_rth = in_session & (weekday_ct <= 5) & (time_ct >= RTH_OPEN) & (time_ct < RTH_CLOSE)

    is_break = (
        ~in_session
        & (weekday_ct <= 4)
        & (time_ct >= NORMAL_SESSION_CLOSE)
        & (time_ct < NEXT_SESSION_OPEN)
        & (pl.col("_market_close_ct").dt.time() == NORMAL_SESSION_CLOSE)
        & (pl.col("_market_close_ct").dt.date() == pl.col("_ts_ct").dt.date())
    )

    is_weekend = (
        ~in_session
        & ~is_break
        & (
            ((weekday_ct == 5) & (time_ct >= WEEKEND_START))
            | (weekday_ct == 6)
            | ((weekday_ct == 7) & (time_ct < NEXT_SESSION_OPEN))
        )
    )

    return joined.with_columns(
        pl.when(is_rth)
        .then(pl.lit(SESSION_RTH))
        .when(in_session)
        .then(pl.lit(SESSION_ETH))
        .when(is_break)
        .then(pl.lit(SESSION_BREAK))
        .when(is_weekend)
        .then(pl.lit(SESSION_WEEKEND))
        .otherwise(pl.lit(SESSION_HOLIDAY))
        .alias("session")
    ).select(*df.columns, "session")


def count_trading_days(
    start_date: dt.date,
    end_date: dt.date,
    *,
    calendar_name: str = CME_EQUITY_CALENDAR,
) -> int:
    """Return the number of CME equity-index trading days in ``[start_date, end_date]``.

    Counts every session in the calendar's schedule, including
    early-close days (which are still trading days). Holidays and
    weekends are not counted. Backed by ``pandas_market_calendars``.

    Args:
        start_date: First date to include (inclusive).
        end_date: Last date to include (inclusive).
        calendar_name: Calendar identifier. Defaults to
            :data:`CME_EQUITY_CALENDAR`.

    Returns:
        Integer count of trading sessions in the range.
    """
    cal = mcal.get_calendar(calendar_name)
    sched = cal.schedule(start_date=start_date, end_date=end_date)
    return int(len(sched))
