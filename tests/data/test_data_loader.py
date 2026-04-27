"""Tests for :mod:`quant_research.data.data_loader`.

The synthetic-fixture tests always run and exercise the loader's contract
without depending on any real vendor data.

The real-data tests (decorated with ``@pytest.mark.skipif``) validate that
the loader's bar count and endpoint timestamps match a direct read of the
on-disk file. They are skipped automatically when the raw data is absent
(e.g. on CI or a fresh checkout, since ``data/raw/`` is gitignored).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
import pytest

from quant_research.data import data_loader

_SAMPLE_LINES = [
    "20260101 233000;100.00;100.50;99.75;100.25;42",
    "20260101 233100;100.25;100.30;100.10;100.15;30",
    "20260101 233200;100.15;100.20;100.05;100.10;25",
    "20260101 233300;100.10;100.40;100.05;100.35;55",
    "20260101 233400;100.35;100.40;100.30;100.32;18",
]


@pytest.fixture
def tiny_contract_file(tmp_path: Path) -> Path:
    """Write a 5-bar synthetic contract file in the NT8 export format."""
    path = tmp_path / "SAMPLE 01-26.Last.txt"
    path.write_text("\n".join(_SAMPLE_LINES) + "\n", encoding="ascii")
    return path


def test_load_contract_file_returns_expected_shape(tiny_contract_file: Path) -> None:
    df = data_loader.load_contract_file(tiny_contract_file)
    assert df.height == len(_SAMPLE_LINES)
    assert tuple(df.columns) == data_loader.CANONICAL_COLUMNS


def test_load_contract_file_schema(tiny_contract_file: Path) -> None:
    df = data_loader.load_contract_file(tiny_contract_file)
    assert df.schema["timestamp"] == pl.Datetime("us", "America/Chicago")
    assert df.schema["open"] == pl.Float64
    assert df.schema["high"] == pl.Float64
    assert df.schema["low"] == pl.Float64
    assert df.schema["close"] == pl.Float64
    assert df.schema["volume"] == pl.Int64
    assert df.schema["contract_symbol"] == pl.String


def test_load_contract_file_first_and_last_rows(tiny_contract_file: Path) -> None:
    df = data_loader.load_contract_file(tiny_contract_file)
    first = df.row(0, named=True)
    assert first["open"] == pytest.approx(100.0)
    assert first["close"] == pytest.approx(100.25)
    assert first["volume"] == 42
    assert first["contract_symbol"] == "SAMPLE 01-26"
    last = df.row(-1, named=True)
    assert last["open"] == pytest.approx(100.35)
    assert last["close"] == pytest.approx(100.32)
    assert last["volume"] == 18


def test_load_contract_file_alternate_timezone(tiny_contract_file: Path) -> None:
    df = data_loader.load_contract_file(tiny_contract_file, timezone="UTC")
    assert df.schema["timestamp"] == pl.Datetime("us", "UTC")


def test_load_contract_file_converts_utc_source_to_ct(tmp_path: Path) -> None:
    """Source timestamps are UTC; loader converts to CT before returning.

    Three UTC bars on 2025-03-09 (the day the 02:00 CST DST spring-forward
    happens). The loader must:

    1. Treat the naive source values as UTC (not CT — see lessons-log
       2026-04-26 UTC discovery entry).
    2. Convert to America/Chicago. Since the source is UTC there is no
       DST gap to handle: every UTC instant has exactly one CT
       wall-clock representation.
    3. Retain all input rows; out-of-trading-hours filtering is the
       responsibility of session classification, not the loader.

    Expected CT wall-clocks:
      - 01:14 UTC -> 19:14 CST on 2025-03-08 (Saturday before DST starts)
      - 02:14 UTC -> 20:14 CST on 2025-03-08 (no longer in any "DST gap")
      - 03:14 UTC -> 21:14 CST on 2025-03-08
    """
    path = tmp_path / "DST 01-25.Last.txt"
    path.write_text(
        "\n".join(
            [
                "20250309 011400;100.00;100.50;99.75;100.25;5",
                "20250309 021400;100.25;100.30;100.10;100.15;1",
                "20250309 031400;100.15;100.20;100.05;100.10;7",
            ]
        )
        + "\n",
        encoding="ascii",
    )
    df = data_loader.load_contract_file(path)
    assert df.height == 3

    rows = list(df.iter_rows(named=True))
    ct_wall_clocks = [(r["timestamp"].date(), r["timestamp"].time()) for r in rows]
    saturday = dt.date(2025, 3, 8)
    assert ct_wall_clocks == [
        (saturday, dt.time(19, 14)),
        (saturday, dt.time(20, 14)),
        (saturday, dt.time(21, 14)),
    ]


def test_load_contract_file_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        data_loader.load_contract_file(tmp_path / "does_not_exist.txt")


def test_contract_symbol_extraction() -> None:
    assert (
        data_loader._contract_symbol_from_filename(Path("data/raw/MNQ 03-26.Last.txt"))
        == "MNQ 03-26"
    )
    assert (
        data_loader._contract_symbol_from_filename(Path("/abs/path/MNQ 12-25.Last.txt"))
        == "MNQ 12-25"
    )


def test_default_data_root_points_under_repo() -> None:
    root = data_loader.default_data_root()
    assert root.parent.name == "data"
    assert root.name == "raw"


def test_discover_contract_files_with_explicit_root(tmp_path: Path) -> None:
    (tmp_path / "MNQ 03-26.Last.txt").write_text("", encoding="ascii")
    (tmp_path / "MNQ 06-26.Last.txt").write_text("", encoding="ascii")
    (tmp_path / "unrelated.csv").write_text("", encoding="ascii")
    found = data_loader.discover_contract_files(tmp_path)
    assert [p.name for p in found] == [
        "MNQ 03-26.Last.txt",
        "MNQ 06-26.Last.txt",
    ]


def test_discover_contract_files_returns_empty_for_missing_dir(tmp_path: Path) -> None:
    assert data_loader.discover_contract_files(tmp_path / "no_such_dir") == []


_REAL_DATA_FILE = data_loader.default_data_root() / "MNQ 03-26.Last.txt"
_REAL_DATA_AVAILABLE = _REAL_DATA_FILE.is_file()
_REAL_DATA_SKIP_REASON = (
    f"Raw MNQ data not present at {_REAL_DATA_FILE}; skipping real-data validation tests."
)


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_mnq_03_26_bar_count_matches_raw_file() -> None:
    """Loader's row count equals the count of non-empty lines in the file."""
    df = data_loader.load_contract_file(_REAL_DATA_FILE)
    expected = sum(1 for line in _REAL_DATA_FILE.read_text().splitlines() if line.strip())
    assert df.height == expected


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_mnq_03_26_endpoints_match_raw_file_after_utc_round_trip() -> None:
    """First/last timestamps round-trip back to the raw file's UTC strings.

    The loader converts the source UTC timestamps to CT for the canonical
    DataFrame. To verify the underlying instant in time is preserved (no
    parsing or rounding error), convert the loaded CT timestamp BACK to
    UTC and compare strings to the raw file.
    """
    df = data_loader.load_contract_file(_REAL_DATA_FILE)
    raw_lines = [line for line in _REAL_DATA_FILE.read_text().splitlines() if line.strip()]
    raw_first_ts_str = raw_lines[0].split(";", 1)[0]
    raw_last_ts_str = raw_lines[-1].split(";", 1)[0]
    first_ts_utc = df.row(0, named=True)["timestamp"].astimezone(dt.UTC)
    last_ts_utc = df.row(-1, named=True)["timestamp"].astimezone(dt.UTC)
    assert first_ts_utc.strftime("%Y%m%d %H%M%S") == raw_first_ts_str
    assert last_ts_utc.strftime("%Y%m%d %H%M%S") == raw_last_ts_str


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_mnq_contract_symbol_set_correctly() -> None:
    df = data_loader.load_contract_file(_REAL_DATA_FILE)
    symbols = df["contract_symbol"].unique().to_list()
    assert symbols == ["MNQ 03-26"]


_SECOND_SAMPLE_LINES = [
    "20260201 091500;200.00;200.50;199.75;200.25;100",
    "20260201 091600;200.25;200.30;200.10;200.15;80",
    "20260201 091700;200.15;200.20;200.05;200.10;65",
]


@pytest.fixture
def two_synthetic_files(tmp_path: Path) -> list[Path]:
    """Two distinct synthetic contract files in the canonical NT8 format."""
    a = tmp_path / "SAMPLE 01-26.Last.txt"
    a.write_text("\n".join(_SAMPLE_LINES) + "\n", encoding="ascii")
    b = tmp_path / "SAMPLE 02-26.Last.txt"
    b.write_text("\n".join(_SECOND_SAMPLE_LINES) + "\n", encoding="ascii")
    return [a, b]


def test_load_contracts_concatenates_two_files(two_synthetic_files: list[Path]) -> None:
    df = data_loader.load_contracts(two_synthetic_files)
    assert df.height == len(_SAMPLE_LINES) + len(_SECOND_SAMPLE_LINES)
    assert tuple(df.columns) == data_loader.CANONICAL_COLUMNS


def test_load_contracts_preserves_per_file_order(two_synthetic_files: list[Path]) -> None:
    df = data_loader.load_contracts(two_synthetic_files)
    symbols_in_order = df["contract_symbol"].to_list()
    expected = ["SAMPLE 01-26"] * len(_SAMPLE_LINES) + ["SAMPLE 02-26"] * len(_SECOND_SAMPLE_LINES)
    assert symbols_in_order == expected


def test_load_contracts_distinct_symbols_in_output(two_synthetic_files: list[Path]) -> None:
    df = data_loader.load_contracts(two_synthetic_files)
    assert sorted(df["contract_symbol"].unique().to_list()) == [
        "SAMPLE 01-26",
        "SAMPLE 02-26",
    ]


def test_load_contracts_empty_iterable_returns_empty_canonical_df() -> None:
    df = data_loader.load_contracts([])
    assert df.height == 0
    assert tuple(df.columns) == data_loader.CANONICAL_COLUMNS
    assert df.schema["timestamp"] == pl.Datetime("us", "America/Chicago")
    assert df.schema["volume"] == pl.Int64
    assert df.schema["contract_symbol"] == pl.String


def test_load_contracts_alternate_timezone_propagates(two_synthetic_files: list[Path]) -> None:
    df = data_loader.load_contracts(two_synthetic_files, timezone="UTC")
    assert df.schema["timestamp"] == pl.Datetime("us", "UTC")


def test_load_all_contracts_uses_explicit_data_root(tmp_path: Path) -> None:
    a = tmp_path / "MNQ 03-26.Last.txt"
    a.write_text("\n".join(_SAMPLE_LINES) + "\n", encoding="ascii")
    b = tmp_path / "MNQ 06-26.Last.txt"
    b.write_text("\n".join(_SECOND_SAMPLE_LINES) + "\n", encoding="ascii")
    (tmp_path / "ignored.csv").write_text("nope", encoding="ascii")
    df = data_loader.load_all_contracts(tmp_path)
    assert df.height == len(_SAMPLE_LINES) + len(_SECOND_SAMPLE_LINES)
    assert sorted(df["contract_symbol"].unique().to_list()) == [
        "MNQ 03-26",
        "MNQ 06-26",
    ]


def test_load_all_contracts_empty_dir_returns_empty(tmp_path: Path) -> None:
    df = data_loader.load_all_contracts(tmp_path)
    assert df.height == 0
    assert tuple(df.columns) == data_loader.CANONICAL_COLUMNS


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_load_all_contracts_total_bar_count_matches_raw_files() -> None:
    """Loaded row count equals raw file line count exactly.

    With the loader treating source as UTC and converting to CT, no rows
    are dropped. The previous DST-gap drop logic was based on a wrong
    premise about the source timezone (see lessons-log 2026-04-26 UTC
    discovery + DST correction entries). Every raw line maps 1:1 to a
    canonical bar.
    """
    df = data_loader.load_all_contracts()
    paths = data_loader.discover_contract_files()
    raw_total = sum(sum(1 for line in p.read_text().splitlines() if line.strip()) for p in paths)
    assert df.height == raw_total, (
        f"row mismatch: loader returned {df.height:,}, raw files have {raw_total:,} non-empty lines"
    )


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_load_all_contracts_in_phase_plan_magnitude() -> None:
    """Total bar count is in the phase-plan-stated magnitude (~2.1M, +/- 30%).

    Wide tolerance because:
      - the dataset still has documented gaps (Jun-Jul 2024, Feb-Mar 2026)
      - additional contracts will be added quarterly
      - this is a sanity check against catastrophic loader regressions, not a
        fingerprint of the dataset.
    """
    df = data_loader.load_all_contracts()
    assert 1_400_000 <= df.height <= 2_800_000, (
        f"unexpected total bar count: {df.height:,} (phase plan: ~2.1M)"
    )


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_load_all_contracts_distinct_contract_count() -> None:
    """All discovered contracts are present in the output exactly once."""
    df = data_loader.load_all_contracts()
    discovered = data_loader.discover_contract_files()
    expected_symbols = {data_loader._contract_symbol_from_filename(p) for p in discovered}
    actual_symbols = set(df["contract_symbol"].unique().to_list())
    assert actual_symbols == expected_symbols
