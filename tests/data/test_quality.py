"""Tests for :mod:`quant_research.data.quality`.

Synthetic tests build small CT-aware DataFrames covering specific
gap and OHLC scenarios and assert the quality utilities behave
correctly.

Real-data tests load the full MNQ dataset and pin the empirical
findings about gap structure (4 known regions, 61 missing trading
days total, no unexpected gaps remain). They are skipped
automatically when the raw data is absent.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.data import continuous_contract, data_loader, quality, session

CT = ZoneInfo("America/Chicago")


def _make_minute_bar_frame(start: dt.datetime, n_minutes: int) -> pl.DataFrame:
    """Synthetic minute-bar frame: ``n_minutes`` consecutive bars from ``start``.

    OHLCV values are deterministic but trivial -- the tests using
    this care about classification and aggregation behavior, not
    price sequences.
    """
    timestamps = [start + dt.timedelta(minutes=i) for i in range(n_minutes)]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + i * 0.01 for i in range(n_minutes)],
            "high": [100.5 + i * 0.01 for i in range(n_minutes)],
            "low": [99.5 + i * 0.01 for i in range(n_minutes)],
            "close": [100.25 + i * 0.01 for i in range(n_minutes)],
            "volume": [10] * n_minutes,
        }
    )


def test_known_gap_contains_inclusive_boundaries() -> None:
    g = quality.KnownGap(
        start_date=dt.date(2024, 6, 18),
        end_date=dt.date(2024, 7, 31),
        description="x",
    )
    assert g.contains(dt.date(2024, 6, 18))
    assert g.contains(dt.date(2024, 7, 31))
    assert g.contains(dt.date(2024, 7, 1))
    assert not g.contains(dt.date(2024, 6, 17))
    assert not g.contains(dt.date(2024, 8, 1))


def test_known_gaps_registry_covers_61_trading_days_total() -> None:
    """The 4 registered gaps span exactly 61 PMC trading days.

    This pins the operator-acknowledged total. If a new export
    arrives or a region is amended, this test should fail and prompt
    a deliberate update.
    """
    total = 0
    for g in quality.KNOWN_GAPS:
        total += session.count_trading_days(g.start_date, g.end_date)
    assert total == 61, f"KNOWN_GAPS now span {total} trading days; expected 61"


def test_find_missing_trading_days_empty_input() -> None:
    df = pl.DataFrame(
        schema={
            "timestamp": pl.Datetime("us", "America/Chicago"),
            "session": pl.String,
        }
    )
    assert quality.find_missing_trading_days(df) == []


def test_find_missing_trading_days_synthetic_full_week() -> None:
    """A synthetic week with bars on every weekday should yield zero missing days.

    Bars are placed at 09:00 CT (firmly in RTH) on Mon-Fri across
    one regular week. The classifier labels them RTH; PMC reports
    those weekdays as trading days; therefore no day is missing.
    """
    week_dates = [
        dt.date(2024, 3, 4),
        dt.date(2024, 3, 5),
        dt.date(2024, 3, 6),
        dt.date(2024, 3, 7),
        dt.date(2024, 3, 8),
    ]
    timestamps = [dt.datetime(d.year, d.month, d.day, 9, 0, tzinfo=CT) for d in week_dates]
    df = pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * 5,
            "high": [100.5] * 5,
            "low": [99.5] * 5,
            "close": [100.25] * 5,
            "volume": [10] * 5,
        }
    )
    assert quality.find_missing_trading_days(df) == []


def test_find_missing_trading_days_one_missing_in_synthetic_week() -> None:
    """Drop Wednesday -- it should surface as the only missing day."""
    week_dates = [
        dt.date(2024, 3, 4),
        dt.date(2024, 3, 5),
        dt.date(2024, 3, 7),
        dt.date(2024, 3, 8),
    ]
    timestamps = [dt.datetime(d.year, d.month, d.day, 9, 0, tzinfo=CT) for d in week_dates]
    df = pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * 4,
            "high": [100.5] * 4,
            "low": [99.5] * 4,
            "close": [100.25] * 4,
            "volume": [10] * 4,
        }
    )
    assert quality.find_missing_trading_days(df) == [dt.date(2024, 3, 6)]


def test_find_unexpected_missing_days_subtracts_known_gap() -> None:
    """A missing day inside a KnownGap should NOT surface as unexpected."""
    week_dates = [dt.date(2024, 3, 4), dt.date(2024, 3, 5), dt.date(2024, 3, 7)]
    timestamps = [dt.datetime(d.year, d.month, d.day, 9, 0, tzinfo=CT) for d in week_dates]
    df = pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0] * 3,
            "high": [100.5] * 3,
            "low": [99.5] * 3,
            "close": [100.25] * 3,
            "volume": [10] * 3,
        }
    )
    fake_gap = (
        quality.KnownGap(
            start_date=dt.date(2024, 3, 6),
            end_date=dt.date(2024, 3, 6),
            description="synthetic test gap",
        ),
    )
    assert quality.find_missing_trading_days(df) == [dt.date(2024, 3, 6)]
    assert quality.find_unexpected_missing_days(df, known_gaps=fake_gap) == []


def test_compute_daily_rth_ohlc_single_day() -> None:
    """One full RTH session (390 bars 08:30-15:00) collapses to a single row.

    The aggregation should pull the open from the first bar, the
    close from the last bar, max/min from the appropriate columns,
    and sum the volume.
    """
    start = dt.datetime(2024, 3, 4, 8, 30, tzinfo=CT)
    df = _make_minute_bar_frame(start, 390)

    daily = quality.compute_daily_rth_ohlc(df)
    assert daily.height == 1
    row = daily.to_dicts()[0]
    assert row["date"] == dt.date(2024, 3, 4)
    assert row["rth_bar_count"] == 390
    assert row["rth_open"] == pytest.approx(100.0)
    assert row["rth_close"] == pytest.approx(100.25 + 389 * 0.01)
    assert row["rth_high"] == pytest.approx(100.5 + 389 * 0.01)
    assert row["rth_low"] == pytest.approx(99.5)
    assert row["rth_volume"] == 390 * 10


def test_compute_daily_rth_ohlc_skips_non_rth_bars() -> None:
    """ETH/BREAK/etc. bars are filtered out before aggregation."""
    rth_start = dt.datetime(2024, 3, 4, 8, 30, tzinfo=CT)
    eth_start = dt.datetime(2024, 3, 4, 17, 0, tzinfo=CT)
    rth = _make_minute_bar_frame(rth_start, 30)
    eth = _make_minute_bar_frame(eth_start, 30)
    df = pl.concat([rth, eth])

    daily = quality.compute_daily_rth_ohlc(df)
    assert daily.height == 1
    assert daily["rth_bar_count"][0] == 30


def test_compute_daily_rth_ohlc_missing_columns_raises() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [dt.datetime(2024, 3, 4, 9, 0, tzinfo=CT)],
            "open": [100.0],
        }
    )
    with pytest.raises(ValueError, match="missing required columns"):
        quality.compute_daily_rth_ohlc(df)


def test_spot_check_ohlc_deterministic_with_seed() -> None:
    """Same seed should pick the same dates across calls."""
    days = [
        _make_minute_bar_frame(dt.datetime(2024, 3, d, 8, 30, tzinfo=CT), 390)
        for d in (4, 5, 6, 7, 8)
    ]
    df = pl.concat(days)
    a = quality.spot_check_ohlc(df, n_dates=3, seed=42)
    b = quality.spot_check_ohlc(df, n_dates=3, seed=42)
    assert a["date"].to_list() == b["date"].to_list()
    assert a.height == 3


_REAL_DATA_FILE = data_loader.default_data_root() / "MNQ 03-26.Last.txt"
_REAL_DATA_AVAILABLE = _REAL_DATA_FILE.is_file()
_REAL_DATA_SKIP_REASON = (
    f"Raw MNQ data not present at {_REAL_DATA_FILE}; skipping real-data quality tests."
)


@pytest.fixture(scope="module")
def real_classified() -> pl.DataFrame:
    """Full continuous MNQ dataset with session labels (cached per module)."""
    df = data_loader.load_all_contracts()
    cont = continuous_contract.build_continuous_contract(df)
    return session.classify_sessions(cont)


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_find_missing_trading_days_matches_known_61(
    real_classified: pl.DataFrame,
) -> None:
    """Empirical: 61 PMC trading days have no bars on the calendar date."""
    missing = quality.find_missing_trading_days(real_classified)
    assert len(missing) == 61, f"expected 61 missing days; got {len(missing)}"


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_no_unexpected_missing_days(real_classified: pl.DataFrame) -> None:
    """All 61 missing days should be covered by KNOWN_GAPS.

    A failure here means a new data gap has appeared (re-export,
    vendor change, etc.) and either the data needs investigation or
    KNOWN_GAPS needs an explicit update with a description.
    """
    unexpected = quality.find_unexpected_missing_days(real_classified)
    assert unexpected == [], f"unexpected missing days surfaced: {unexpected}"


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_each_known_gap_has_missing_days_inside(
    real_classified: pl.DataFrame,
) -> None:
    """Every registered gap should still correspond to actual missing days.

    Guards against stale ``KNOWN_GAPS`` entries that no longer match
    the data (e.g. after a re-export). Each gap should contain at
    least one day reported missing.
    """
    missing_set = set(quality.find_missing_trading_days(real_classified))
    for gap in quality.KNOWN_GAPS:
        days_in_gap = [d for d in missing_set if gap.contains(d)]
        assert days_in_gap, (
            f"KNOWN_GAPS entry {gap.start_date}..{gap.end_date} no longer "
            f"matches any missing day in the dataset"
        )


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_spot_check_ohlc_returns_5_normal_rth_days(
    real_classified: pl.DataFrame,
) -> None:
    """Spot-check should yield 5 dates each with the standard 390 RTH bars."""
    spot = quality.spot_check_ohlc(real_classified, n_dates=5, seed=42)
    assert spot.height == 5
    assert (spot["rth_bar_count"] == 390).all()
    for col in ("rth_open", "rth_high", "rth_low", "rth_close", "rth_volume"):
        assert col in spot.columns


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_spot_check_ohlc_high_low_invariants(
    real_classified: pl.DataFrame,
) -> None:
    """For every spot-check row: low <= open, close <= high; volume > 0."""
    spot = quality.spot_check_ohlc(real_classified, n_dates=5, seed=42)
    for row in spot.to_dicts():
        assert row["rth_low"] <= row["rth_open"] <= row["rth_high"]
        assert row["rth_low"] <= row["rth_close"] <= row["rth_high"]
        assert row["rth_volume"] > 0
