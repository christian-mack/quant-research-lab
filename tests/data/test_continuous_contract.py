"""Tests for :mod:`quant_research.data.continuous_contract`.

Synthetic tests construct small DataFrames directly so we can verify
roll detection and stitching against known answers without needing
real vendor data.

Real-data tests are guarded by ``pytest.mark.skipif`` so the suite
passes on a fresh checkout where ``data/raw/`` is empty.
"""

from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from quant_research.data import continuous_contract as cc
from quant_research.data import data_loader
from quant_research.data.data_loader import CANONICAL_COLUMNS, CME_TIMEZONE


def _make_daily_bars(
    contract: str,
    dates: list[dt.date],
    daily_volumes: list[int],
    *,
    base_price: float = 100.0,
    timezone: str = CME_TIMEZONE,
) -> pl.DataFrame:
    """Build a synthetic per-contract DataFrame with one bar per date.

    Each "bar" is timestamped at 12:00 in ``timezone`` so it never
    collides with DST transitions or session boundaries.
    """
    assert len(dates) == len(daily_volumes)
    timestamps_naive = [dt.datetime(d.year, d.month, d.day, 12, 0) for d in dates]
    return (
        pl.DataFrame(
            {
                "timestamp": pl.Series(timestamps_naive).cast(pl.Datetime("us")),
                "open": [base_price] * len(dates),
                "high": [base_price + 0.5] * len(dates),
                "low": [base_price - 0.5] * len(dates),
                "close": [base_price + 0.25] * len(dates),
                "volume": daily_volumes,
                "contract_symbol": [contract] * len(dates),
            }
        )
        .with_columns(pl.col("timestamp").dt.replace_time_zone(timezone))
        .select(*CANONICAL_COLUMNS)
    )


def test_parse_contract_code_valid() -> None:
    code = cc.parse_contract_code("MNQ 03-26")
    assert code.symbol == "MNQ"
    assert code.expiry_year == 2026
    assert code.expiry_month == 3
    assert code.sort_key == (2026, 3)


def test_parse_contract_code_handles_two_digit_year_pre_and_post() -> None:
    assert cc.parse_contract_code("MNQ 12-19").expiry_year == 2019
    assert cc.parse_contract_code("MNQ 12-99").expiry_year == 2099


def test_parse_contract_code_invalid_raises() -> None:
    with pytest.raises(ValueError, match="Cannot parse"):
        cc.parse_contract_code("not a contract")
    with pytest.raises(ValueError):
        cc.parse_contract_code("MNQ_03-26")
    with pytest.raises(ValueError):
        cc.parse_contract_code("MNQ 3-26")


def test_sort_contracts_chronologically_handles_year_boundary() -> None:
    """Lexicographic sort would put 'MNQ 12-20' before 'MNQ 03-21'; we don't."""
    inputs = ["MNQ 03-21", "MNQ 12-20", "MNQ 06-20", "MNQ 09-20"]
    assert cc.sort_contracts_chronologically(inputs) == [
        "MNQ 06-20",
        "MNQ 09-20",
        "MNQ 12-20",
        "MNQ 03-21",
    ]


def test_find_roll_dates_simple_crossover() -> None:
    """Three consecutive dominance days trigger volume_crossover roll on the next day."""
    base = dt.date(2025, 1, 1)
    a_dates = [base + dt.timedelta(days=i) for i in range(11)]
    b_dates = [base + dt.timedelta(days=i) for i in range(15)]

    a_volumes = [100, 95, 80, 60, 40, 20, 10, 5, 2, 1, 1]
    b_volumes = [30, 50, 90, 100, 120, 130, 140, 150, 160, 170, 180, 200, 220, 240, 260]

    df = pl.concat(
        [
            _make_daily_bars("MNQ 03-25", a_dates, a_volumes),
            _make_daily_bars("MNQ 06-25", b_dates, b_volumes),
        ]
    )

    rolls = cc.find_roll_dates(df, crossover_window=3)

    assert len(rolls) == 1
    event = rolls[0]
    assert event.from_contract == "MNQ 03-25"
    assert event.to_contract == "MNQ 06-25"
    assert event.method == "volume_crossover"
    assert event.trigger_date == base + dt.timedelta(days=4)
    assert event.roll_at.date() == base + dt.timedelta(days=5)
    assert event.roll_at.hour == 0
    assert event.roll_at.minute == 0


def test_find_roll_dates_no_dominance_falls_back_to_data_boundary() -> None:
    """If the next contract never dominates, fallback emits a data_boundary event."""
    base = dt.date(2025, 1, 1)
    dates = [base + dt.timedelta(days=i) for i in range(10)]
    df = pl.concat(
        [
            _make_daily_bars("MNQ 03-25", dates, [100] * 10),
            _make_daily_bars("MNQ 06-25", dates, [10] * 10),
        ]
    )
    rolls = cc.find_roll_dates(df, crossover_window=3)
    assert len(rolls) == 1
    event = rolls[0]
    assert event.method == "data_boundary"
    assert event.trigger_date is None
    assert event.roll_at > df.filter(pl.col("contract_symbol") == "MNQ 03-25")["timestamp"].max()


def test_find_roll_dates_intermittent_dominance_falls_back_to_data_boundary() -> None:
    """Dominance must be ``N`` *consecutive* days; otherwise we use data boundary."""
    base = dt.date(2025, 1, 1)
    dates = [base + dt.timedelta(days=i) for i in range(10)]
    df = pl.concat(
        [
            _make_daily_bars("MNQ 03-25", dates, [50, 50, 50, 50, 50, 50, 50, 50, 50, 50]),
            _make_daily_bars("MNQ 06-25", dates, [60, 30, 60, 30, 60, 30, 60, 30, 60, 30]),
        ]
    )
    rolls = cc.find_roll_dates(df, crossover_window=3)
    assert len(rolls) == 1
    assert rolls[0].method == "data_boundary"


def test_find_roll_dates_invalid_window_raises() -> None:
    df = _make_daily_bars("MNQ 03-25", [dt.date(2025, 1, 1)], [1])
    with pytest.raises(ValueError):
        cc.find_roll_dates(df, crossover_window=0)


def test_find_roll_dates_empty_input_returns_empty() -> None:
    empty = data_loader._empty_canonical_dataframe(CME_TIMEZONE)
    assert cc.find_roll_dates(empty) == []


def test_build_continuous_contract_simple() -> None:
    """End-to-end: 2 contracts, known crossover, verify stitching."""
    base = dt.date(2025, 1, 1)
    a_dates = [base + dt.timedelta(days=i) for i in range(11)]
    b_dates = [base + dt.timedelta(days=i) for i in range(15)]
    a_volumes = [100, 95, 80, 60, 40, 20, 10, 5, 2, 1, 1]
    b_volumes = [30, 50, 90, 100, 120, 130, 140, 150, 160, 170, 180, 200, 220, 240, 260]

    df = pl.concat(
        [
            _make_daily_bars("MNQ 03-25", a_dates, a_volumes),
            _make_daily_bars("MNQ 06-25", b_dates, b_volumes),
        ]
    )

    cont = cc.build_continuous_contract(df, crossover_window=3)

    assert cont.height == 5 + 10

    a_portion = cont.filter(pl.col("contract_symbol") == "MNQ 03-25")
    b_portion = cont.filter(pl.col("contract_symbol") == "MNQ 06-25")
    assert a_portion.height == 5
    assert b_portion.height == 10

    last_a_date = a_portion["timestamp"].max().date()
    first_b_date = b_portion["timestamp"].min().date()
    assert last_a_date == base + dt.timedelta(days=4)
    assert first_b_date == base + dt.timedelta(days=5)

    assert cont["timestamp"].n_unique() == cont.height


def test_build_continuous_contract_three_contracts_two_rolls() -> None:
    """Three sequential contracts produce two roll events and three active periods."""
    base = dt.date(2025, 1, 1)

    def date_range(start_offset: int, n_days: int) -> list[dt.date]:
        return [base + dt.timedelta(days=start_offset + i) for i in range(n_days)]

    a_dates = date_range(0, 11)
    b_dates = date_range(0, 21)
    c_dates = date_range(10, 15)

    a_volumes = [100, 95, 80, 60, 40, 20, 10, 5, 2, 1, 1]
    b_volumes = [30, 50, 90, 100, 120, 130, 140, 150, 160, 170] + [
        200,
        180,
        160,
        100,
        80,
        60,
        40,
        20,
        10,
        5,
        2,
    ]
    c_volumes = [50, 70, 90, 110, 130, 150, 170, 190, 210, 230, 250, 270, 290, 310, 330]

    df = pl.concat(
        [
            _make_daily_bars("MNQ 03-25", a_dates, a_volumes),
            _make_daily_bars("MNQ 06-25", b_dates, b_volumes),
            _make_daily_bars("MNQ 09-25", c_dates, c_volumes),
        ]
    )

    rolls = cc.find_roll_dates(df, crossover_window=3)
    assert len(rolls) == 2
    assert rolls[0].from_contract == "MNQ 03-25"
    assert rolls[0].to_contract == "MNQ 06-25"
    assert rolls[1].from_contract == "MNQ 06-25"
    assert rolls[1].to_contract == "MNQ 09-25"

    cont = cc.build_continuous_contract(df, crossover_window=3)
    assert cont["timestamp"].n_unique() == cont.height
    symbols_seq = cont["contract_symbol"].to_list()
    transitions = [
        (symbols_seq[i], symbols_seq[i + 1])
        for i in range(len(symbols_seq) - 1)
        if symbols_seq[i] != symbols_seq[i + 1]
    ]
    assert transitions == [("MNQ 03-25", "MNQ 06-25"), ("MNQ 06-25", "MNQ 09-25")]


def test_build_continuous_contract_empty_returns_empty_canonical() -> None:
    empty = data_loader._empty_canonical_dataframe(CME_TIMEZONE)
    cont = cc.build_continuous_contract(empty)
    assert cont.height == 0
    assert tuple(cont.columns) == CANONICAL_COLUMNS


def test_build_continuous_contract_single_contract_passes_through() -> None:
    base = dt.date(2025, 1, 1)
    dates = [base + dt.timedelta(days=i) for i in range(5)]
    df = _make_daily_bars("MNQ 03-25", dates, [100, 90, 80, 70, 60])
    cont = cc.build_continuous_contract(df)
    assert cont.height == 5
    assert cont["contract_symbol"].unique().to_list() == ["MNQ 03-25"]


def test_build_continuous_contract_no_overlap_falls_back_to_data_boundary() -> None:
    """Contracts that don't overlap still produce a roll event (data_boundary fallback)."""
    base = dt.date(2025, 1, 1)
    a_dates = [base + dt.timedelta(days=i) for i in range(5)]
    b_dates = [base + dt.timedelta(days=20 + i) for i in range(5)]
    df = pl.concat(
        [
            _make_daily_bars("MNQ 03-25", a_dates, [100] * 5),
            _make_daily_bars("MNQ 06-25", b_dates, [100] * 5),
        ]
    )
    rolls = cc.find_roll_dates(df, crossover_window=3)
    assert len(rolls) == 1
    assert rolls[0].method == "data_boundary"
    cont = cc.build_continuous_contract(df, crossover_window=3)
    assert cont.height == 10
    assert cont["timestamp"].n_unique() == 10


_REAL_DATA_AVAILABLE = (data_loader.default_data_root() / "MNQ 03-26.Last.txt").is_file()
_REAL_DATA_SKIP_REASON = "data/raw/ not present; skipping continuous-contract real-data tests."


@pytest.fixture(scope="module")
def real_full_dataset() -> pl.DataFrame:
    return data_loader.load_all_contracts()


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_continuous_contract_no_duplicate_timestamps(
    real_full_dataset: pl.DataFrame,
) -> None:
    cont = cc.build_continuous_contract(real_full_dataset)
    assert cont["timestamp"].n_unique() == cont.height


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_continuous_contract_total_bars_no_more_than_raw(
    real_full_dataset: pl.DataFrame,
) -> None:
    cont = cc.build_continuous_contract(real_full_dataset)
    assert cont.height <= real_full_dataset.height
    assert cont.height >= int(real_full_dataset.height * 0.50)


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_continuous_contract_roll_dates_plausible(
    real_full_dataset: pl.DataFrame,
) -> None:
    """Every adjacent contract pair produces a roll event in a sensible window.

    For 26 chronologically-sorted MNQ contracts there are 25 inter-contract
    rolls. Each roll's date must fall within ±60 calendar days of the
    *from* contract's expiry month start (i.e., somewhere in the 2-month
    window leading up to expiry, allowing some slack for the documented
    Jun-Jul 2024 and Feb-Mar 2026 gaps where roll happens at the very end
    of the from-contract's data).
    """
    rolls = cc.find_roll_dates(real_full_dataset)
    assert len(rolls) == 25

    for event in rolls:
        from_code = cc.parse_contract_code(event.from_contract)
        from_expiry_month_first = dt.date(from_code.expiry_year, from_code.expiry_month, 1)
        roll_date = event.trigger_date if event.trigger_date is not None else event.roll_at.date()
        days_diff = (roll_date - from_expiry_month_first).days
        assert -60 <= days_diff <= 60, (
            f"implausible roll {event.from_contract}->{event.to_contract} "
            f"({event.method}) at {roll_date}, "
            f"{days_diff} days from from-contract expiry month start "
            f"{from_expiry_month_first}"
        )


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_continuous_contract_methods_breakdown(
    real_full_dataset: pl.DataFrame,
) -> None:
    """Document the empirical method mix for the current NT8 dataset.

    For the 2026-04-26 dataset, all 25 rolls fall through to
    ``data_boundary`` because NT8 exports each contract only during its
    dominant period (see lessons-log 2026-04-26 — to be added). This
    test pins the observation so we notice if a future dataset upgrade
    starts to produce volume_crossover rolls (a good thing — more signal).
    """
    rolls = cc.find_roll_dates(real_full_dataset)
    methods = [r.method for r in rolls]
    n_volume = sum(1 for m in methods if m == "volume_crossover")
    n_boundary = sum(1 for m in methods if m == "data_boundary")
    assert n_volume + n_boundary == len(rolls)
    assert n_boundary >= 20, (
        f"expected most rolls to be data_boundary on this dataset; "
        f"got {n_boundary} boundary, {n_volume} volume_crossover"
    )


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_continuous_contract_chronological_symbol_progression(
    real_full_dataset: pl.DataFrame,
) -> None:
    """contract_symbol changes in chronological expiry order, never reversing."""
    cont = cc.build_continuous_contract(real_full_dataset)
    distinct_in_order: list[str] = []
    seen: set[str] = set()
    for sym in cont["contract_symbol"].to_list():
        if sym in seen:
            continue
        if distinct_in_order and sym in seen:
            pytest.fail(f"contract_symbol {sym!r} re-appears after another symbol")
        distinct_in_order.append(sym)
        seen.add(sym)

    expected_order = cc.sort_contracts_chronologically(distinct_in_order)
    assert distinct_in_order == expected_order


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_continuous_contract_one_active_contract_per_timestamp(
    real_full_dataset: pl.DataFrame,
) -> None:
    """Within the continuous series, no timestamp belongs to two contracts."""
    cont = cc.build_continuous_contract(real_full_dataset)
    grouped = cont.group_by("timestamp").agg(pl.col("contract_symbol").n_unique().alias("n"))
    max_n = grouped["n"].max()
    assert max_n == 1
