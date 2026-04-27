"""Tests for :mod:`quant_research.data.session`.

Synthetic tests build small CT-aware DataFrames covering specific
session-boundary cases and assert the classifier emits the expected
``session`` label for each row.

Real-data tests load the full MNQ dataset, build the continuous
contract, classify, and assert population-level invariants
(distribution shape, holiday-day behavior, no naive-tz crashes).
They are skipped automatically when the raw data is absent.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.data import continuous_contract, data_loader, session


def _make_ct_df(rows: list[tuple[dt.datetime, str | None]]) -> pl.DataFrame:
    """Build a tiny CT-aware DataFrame from a list of (naive_ct, label) pairs.

    The label is a comment for the test reader; only the timestamp
    is used by the classifier. The synthetic frame includes an
    ``expected`` column holding the label so a single assertion can
    compare against ``session`` after classification.
    """
    return pl.DataFrame(
        {
            "timestamp": [ts.replace(tzinfo=ZoneInfo("America/Chicago")) for ts, _ in rows],
            "expected": [label for _, label in rows],
        }
    )


def test_classify_normal_weekday_boundaries() -> None:
    """RTH window is [08:30, 15:00); BREAK is [16:00, 17:00); rest in-session is ETH."""
    rows = [
        (dt.datetime(2024, 3, 4, 0, 0), session.SESSION_ETH),
        (dt.datetime(2024, 3, 4, 8, 29), session.SESSION_ETH),
        (dt.datetime(2024, 3, 4, 8, 30), session.SESSION_RTH),
        (dt.datetime(2024, 3, 4, 12, 0), session.SESSION_RTH),
        (dt.datetime(2024, 3, 4, 14, 59), session.SESSION_RTH),
        (dt.datetime(2024, 3, 4, 15, 0), session.SESSION_ETH),
        (dt.datetime(2024, 3, 4, 15, 30), session.SESSION_ETH),
        (dt.datetime(2024, 3, 4, 16, 0), session.SESSION_BREAK),
        (dt.datetime(2024, 3, 4, 16, 30), session.SESSION_BREAK),
        (dt.datetime(2024, 3, 4, 16, 59), session.SESSION_BREAK),
        (dt.datetime(2024, 3, 4, 17, 0), session.SESSION_ETH),
        (dt.datetime(2024, 3, 4, 23, 59), session.SESSION_ETH),
    ]
    df = _make_ct_df(rows)
    out = session.classify_sessions(df.drop("expected"))
    actual = out.join(df, on="timestamp", how="left")
    assert actual["session"].to_list() == actual["expected"].to_list()


def test_classify_normal_weekend_boundaries() -> None:
    """Friday 16:00 -> Sunday 17:00 is WEEKEND; Sunday 17:00+ is ETH."""
    rows = [
        (dt.datetime(2024, 3, 1, 15, 0), session.SESSION_ETH),
        (dt.datetime(2024, 3, 1, 15, 30), session.SESSION_ETH),
        (dt.datetime(2024, 3, 1, 15, 59), session.SESSION_ETH),
        (dt.datetime(2024, 3, 1, 16, 0), session.SESSION_WEEKEND),
        (dt.datetime(2024, 3, 1, 23, 59), session.SESSION_WEEKEND),
        (dt.datetime(2024, 3, 2, 12, 0), session.SESSION_WEEKEND),
        (dt.datetime(2024, 3, 3, 16, 59), session.SESSION_WEEKEND),
        (dt.datetime(2024, 3, 3, 17, 0), session.SESSION_ETH),
        (dt.datetime(2024, 3, 3, 18, 0), session.SESSION_ETH),
    ]
    df = _make_ct_df(rows)
    out = session.classify_sessions(df.drop("expected"))
    actual = out.join(df, on="timestamp", how="left")
    assert actual["session"].to_list() == actual["expected"].to_list()


def test_classify_full_holiday_christmas_day() -> None:
    """2024-12-25 is closed all weekday hours; 17:00+ belongs to Thursday's session.

    On a normal week this would be a routine session. With Christmas
    Day on Wednesday: prev session closes Tue 12:00 (early close),
    next session opens Wed 17:00 for Thursday's trading. Therefore:
    Wed 00:00-16:59 -> HOLIDAY; Wed 17:00+ -> ETH.
    """
    rows = [
        (dt.datetime(2024, 12, 25, 0, 0), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 12, 25, 9, 0), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 12, 25, 14, 0), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 12, 25, 15, 30), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 12, 25, 16, 0), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 12, 25, 16, 59), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 12, 25, 17, 0), session.SESSION_ETH),
        (dt.datetime(2024, 12, 25, 22, 0), session.SESSION_ETH),
    ]
    df = _make_ct_df(rows)
    out = session.classify_sessions(df.drop("expected"))
    actual = out.join(df, on="timestamp", how="left")
    assert actual["session"].to_list() == actual["expected"].to_list()


def test_classify_early_close_black_friday() -> None:
    """2024-11-29 closes at 12:00 CT; 12:00+ is HOLIDAY (post-early-close).

    In-session is half-open: ``[market_open, market_close)``. So the
    bar at 12:00:00 sharp on an early-close day is already
    out-of-session and classifies as HOLIDAY. Bars at 16:00+ on
    Friday belong to the normal weekend window -> WEEKEND.
    """
    rows = [
        (dt.datetime(2024, 11, 29, 11, 0), session.SESSION_RTH),
        (dt.datetime(2024, 11, 29, 11, 59), session.SESSION_RTH),
        (dt.datetime(2024, 11, 29, 12, 0), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 11, 29, 12, 1), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 11, 29, 12, 30), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 11, 29, 14, 0), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 11, 29, 15, 30), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 11, 29, 15, 59), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 11, 29, 16, 0), session.SESSION_WEEKEND),
        (dt.datetime(2024, 11, 29, 18, 0), session.SESSION_WEEKEND),
        (dt.datetime(2024, 11, 30, 9, 0), session.SESSION_WEEKEND),
        (dt.datetime(2024, 12, 1, 16, 59), session.SESSION_WEEKEND),
        (dt.datetime(2024, 12, 1, 17, 0), session.SESSION_ETH),
    ]
    df = _make_ct_df(rows)
    out = session.classify_sessions(df.drop("expected"))
    actual = out.join(df, on="timestamp", how="left")
    assert actual["session"].to_list() == actual["expected"].to_list()


def test_classify_holiday_extended_weekend_monday_holiday() -> None:
    """2024-01-01 (NYD on Monday, full close): Sun 17:00 -> Mon 17:00 is HOLIDAY.

    Per PMC's CME_Equity calendar, NYD 2024 is the only Monday full-close
    holiday in 2024-2025 (Good Friday is an early-close day, not a full
    close). On a normal week Sunday 17:00 begins Monday's session (ETH);
    with Monday closed the session is skipped and the next session opens
    Mon 17:00 CT for Tuesday's trading. So Sun 17:00 -> Mon 17:00 is
    HOLIDAY, distinct from the WEEKEND (Fri 16:00 -> Sun 17:00).

    The bar at Mon 16:00 specifically is HOLIDAY (not BREAK): although
    the wall-clock window matches the maintenance break, the previous
    session's close was the prior Friday at 16:00, not Monday at 16:00,
    so the BREAK rule's same-date guard prevents a false positive.
    """
    rows = [
        (dt.datetime(2023, 12, 29, 15, 0), session.SESSION_ETH),
        (dt.datetime(2023, 12, 29, 16, 0), session.SESSION_WEEKEND),
        (dt.datetime(2023, 12, 30, 12, 0), session.SESSION_WEEKEND),
        (dt.datetime(2023, 12, 31, 16, 59), session.SESSION_WEEKEND),
        (dt.datetime(2023, 12, 31, 17, 0), session.SESSION_HOLIDAY),
        (dt.datetime(2023, 12, 31, 23, 0), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 1, 1, 8, 0), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 1, 1, 12, 0), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 1, 1, 15, 59), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 1, 1, 16, 0), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 1, 1, 16, 59), session.SESSION_HOLIDAY),
        (dt.datetime(2024, 1, 1, 17, 0), session.SESSION_ETH),
        (dt.datetime(2024, 1, 1, 23, 0), session.SESSION_ETH),
    ]
    df = _make_ct_df(rows)
    out = session.classify_sessions(df.drop("expected"))
    actual = out.join(df, on="timestamp", how="left")
    assert actual["session"].to_list() == actual["expected"].to_list()


def test_classify_dst_spring_forward_inside_weekend() -> None:
    """2024-03-10 spring forward (02:00 CST -> 03:00 CDT) sits inside WEEKEND.

    The classifier sees CT wall-clock; bars on Sat/Sun before 17:00
    classify as WEEKEND regardless of underlying UTC offset, and
    polars' tz handling means no special case is needed.
    """
    sat_after_dst_hour = dt.datetime(2024, 3, 10, 1, 30, tzinfo=ZoneInfo("America/Chicago"))
    sun_after_open = dt.datetime(2024, 3, 10, 17, 30, tzinfo=ZoneInfo("America/Chicago"))
    df = pl.DataFrame({"timestamp": [sat_after_dst_hour, sun_after_open]})
    out = session.classify_sessions(df)
    assert out["session"].to_list() == [session.SESSION_WEEKEND, session.SESSION_ETH]


def test_classify_empty_dataframe_returns_empty_with_session_column() -> None:
    df = pl.DataFrame(
        schema={
            "timestamp": pl.Datetime("us", "America/Chicago"),
            "open": pl.Float64,
        }
    )
    out = session.classify_sessions(df)
    assert out.height == 0
    assert "session" in out.columns
    assert out.schema["session"] == pl.String


def test_classify_naive_timestamp_raises() -> None:
    df = pl.DataFrame({"timestamp": [dt.datetime(2024, 3, 4, 9, 0)]})
    with pytest.raises(ValueError, match="tz-aware"):
        session.classify_sessions(df)


def test_classify_missing_timestamp_column_raises() -> None:
    df = pl.DataFrame({"open": [100.0]})
    with pytest.raises(ValueError, match="timestamp"):
        session.classify_sessions(df)


def test_classify_preserves_original_columns_and_row_count() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [
                dt.datetime(2024, 3, 4, 9, 0, tzinfo=ZoneInfo("America/Chicago")),
                dt.datetime(2024, 3, 4, 14, 0, tzinfo=ZoneInfo("America/Chicago")),
            ],
            "open": [100.0, 101.0],
            "volume": [10, 20],
        }
    )
    out = session.classify_sessions(df)
    assert out.height == df.height
    assert set(out.columns) == {"timestamp", "open", "volume", "session"}


def test_classify_alternate_input_timezone_converts_correctly() -> None:
    """A UTC-tz input is correctly classified by its CT wall-clock equivalent.

    2024-03-04 is before DST start (2024-03-10), so CT = UTC-6:
    - 15:00 UTC = 09:00 CT -> RTH
    - 22:00 UTC = 16:00 CT -> BREAK
    """
    df = pl.DataFrame(
        {
            "timestamp": [
                dt.datetime(2024, 3, 4, 15, 0, tzinfo=dt.UTC),
                dt.datetime(2024, 3, 4, 22, 0, tzinfo=dt.UTC),
            ]
        }
    )
    out = session.classify_sessions(df)
    assert out["session"].to_list() == [session.SESSION_RTH, session.SESSION_BREAK]


def test_count_trading_days_matches_pmc_for_calendar_year_2020() -> None:
    """2020 had 252 standard trading days; PMC may report a few more for futures."""
    n = session.count_trading_days(dt.date(2020, 1, 1), dt.date(2020, 12, 31))
    assert 245 <= n <= 260, f"unexpected 2020 trading-day count: {n}"


def test_get_cme_schedule_columns_and_tz() -> None:
    sched = session.get_cme_schedule(dt.date(2024, 3, 1), dt.date(2024, 3, 8))
    assert sched.columns == ["session_date", "market_open", "market_close"]
    assert sched.schema["market_open"].time_zone == session.CT_TIMEZONE  # type: ignore[union-attr]
    assert sched.schema["market_close"].time_zone == session.CT_TIMEZONE  # type: ignore[union-attr]
    assert sched.height >= 5


_REAL_DATA_FILE = data_loader.default_data_root() / "MNQ 03-26.Last.txt"
_REAL_DATA_AVAILABLE = _REAL_DATA_FILE.is_file()
_REAL_DATA_SKIP_REASON = (
    f"Raw MNQ data not present at {_REAL_DATA_FILE}; skipping real-data session-classifier tests."
)


@pytest.fixture(scope="module")
def real_classified() -> pl.DataFrame:
    """Full continuous MNQ dataset with session labels (cached per module)."""
    df = data_loader.load_all_contracts()
    cont = continuous_contract.build_continuous_contract(df)
    return session.classify_sessions(cont)


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_session_breakdown_dominated_by_in_session(
    real_classified: pl.DataFrame,
) -> None:
    """RTH+ETH together should be >99% of bars; out-of-session bars are stray ticks."""
    counts = real_classified.group_by("session").len().to_dict(as_series=False)
    by_label = dict(zip(counts["session"], counts["len"], strict=True))
    in_session = by_label.get(session.SESSION_RTH, 0) + by_label.get(session.SESSION_ETH, 0)
    total = real_classified.height
    assert in_session / total > 0.99, (
        f"in-session fraction {in_session / total:.4f} below expected 0.99"
    )


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_session_all_labels_emitted(real_classified: pl.DataFrame) -> None:
    """Across 6 years of bars every label should appear at least once."""
    actual = set(real_classified["session"].unique().to_list())
    assert actual == set(session.ALL_SESSIONS)


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_session_christmas_day_2024_no_rth_no_break(
    real_classified: pl.DataFrame,
) -> None:
    """2024-12-25 is closed all daytime hours; 17:00+ is Thursday's session."""
    xmas = real_classified.filter(pl.col("timestamp").dt.date() == dt.date(2024, 12, 25))
    labels = set(xmas["session"].unique().to_list())
    assert session.SESSION_RTH not in labels
    assert session.SESSION_BREAK not in labels
    assert labels.issubset({session.SESSION_HOLIDAY, session.SESSION_ETH})


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_session_black_friday_2024_post_close_is_holiday(
    real_classified: pl.DataFrame,
) -> None:
    """2024-11-29 closes at 12:00 CT; bars between 12:01 CT and 15:59 CT are HOLIDAY."""
    post_close = real_classified.filter(
        (pl.col("timestamp").dt.date() == dt.date(2024, 11, 29))
        & (pl.col("timestamp").dt.time() >= dt.time(12, 1))
        & (pl.col("timestamp").dt.time() < dt.time(16, 0))
    )
    if post_close.height > 0:
        assert post_close["session"].unique().to_list() == [session.SESSION_HOLIDAY]


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_session_normal_monday_has_rth_and_eth(
    real_classified: pl.DataFrame,
) -> None:
    """A non-holiday Monday in March should have a healthy mix of RTH and ETH."""
    monday = real_classified.filter(pl.col("timestamp").dt.date() == dt.date(2024, 3, 4))
    counts_df = monday.group_by("session").len()
    counts = dict(
        zip(
            counts_df["session"].to_list(),
            counts_df["len"].to_list(),
            strict=True,
        )
    )
    rth = counts.get(session.SESSION_RTH, 0)
    eth = counts.get(session.SESSION_ETH, 0)
    assert rth >= 350, f"normal Monday RTH bars {rth} (expected ~390)"
    assert eth >= 600, f"normal Monday ETH bars {eth} (expected >600)"


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_session_trading_day_count_in_range(
    real_classified: pl.DataFrame,
) -> None:
    """Trading days over the data span are within phase-plan-stated magnitude.

    Phase plan estimated ~1,580 (back-of-envelope). PMC gives the
    exact count; allow +/-15% tolerance since the estimate predates
    the actual data range.
    """
    min_date = real_classified["timestamp"].min().date()  # type: ignore[union-attr]
    max_date = real_classified["timestamp"].max().date()  # type: ignore[union-attr]
    n = session.count_trading_days(min_date, max_date)
    assert 1_350 <= n <= 1_820, f"unexpected trading-day count: {n}"
