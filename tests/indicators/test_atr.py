"""Tests for :mod:`quant_research.indicators.atr`.

Test layers:

1. *Numerical primitive* — a hand-computed 5-bar example pinning the
   True Range and the seeded SMA so the formula is locked even if the
   pandas-ta reference goes away.
2. *Cross-check vs pandas-ta* — a 1000-bar synthetic OHLC series; ATR
   in all three smoothing modes (rma/sma/ema) must match pandas-ta
   within ``1e-6`` relative error post-warmup. This is the M3
   validation criterion in the phase plan.
3. *Edge cases / error paths* — length validation, mamode validation,
   missing columns, length larger than data, length=1 corner.
4. *Real-data smoke* — load the continuous MNQ contract, compute
   ATR(14), assert (a) right warmup count, (b) all post-warmup values
   are positive and finite, (c) magnitude is within the historical
   range of MNQ bar volatility.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas_ta as ta
import polars as pl
import pytest

from quant_research.data import continuous_contract, data_loader
from quant_research.indicators import atr as atr_mod
from quant_research.indicators.atr import (
    ATR_DEFAULT_LENGTH,
    add_atr,
    add_true_range,
    atr_expr,
    true_range_expr,
)


def _make_ohlc(rows: list[tuple[float, float, float]]) -> pl.DataFrame:
    """Build a DataFrame from a list of (high, low, close) tuples."""
    return pl.DataFrame(
        {
            "high": [r[0] for r in rows],
            "low": [r[1] for r in rows],
            "close": [r[2] for r in rows],
        }
    )


def _synthetic_ohlc(*, n: int = 1000, seed: int = 42) -> tuple[pl.DataFrame, pd.DataFrame]:
    """Generate a deterministic OHLC series in both polars and pandas form."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.5, size=n))
    high = close + rng.uniform(0.1, 1.0, size=n)
    low = close - rng.uniform(0.1, 1.0, size=n)
    pdf = pd.DataFrame({"high": high, "low": low, "close": close})
    pldf = pl.DataFrame({"high": high, "low": low, "close": close})
    return pldf, pdf


def test_true_range_matches_hand_computation() -> None:
    """5-bar example with explicit per-bar True Range values."""
    df = _make_ohlc(
        [
            (10.0, 9.0, 9.5),
            (11.0, 10.0, 10.8),
            (10.5, 9.5, 9.7),
            (12.0, 11.0, 11.5),
            (11.5, 10.5, 11.0),
        ]
    )
    out = add_true_range(df)
    expected = [
        1.0,
        max(11.0 - 10.0, abs(11.0 - 9.5), abs(10.0 - 9.5)),
        max(10.5 - 9.5, abs(10.5 - 10.8), abs(9.5 - 10.8)),
        max(12.0 - 11.0, abs(12.0 - 9.7), abs(11.0 - 9.7)),
        max(11.5 - 10.5, abs(11.5 - 11.5), abs(10.5 - 11.5)),
    ]
    assert out["true_range"].to_list() == pytest.approx(expected, rel=1e-12)


def test_true_range_first_bar_is_high_minus_low() -> None:
    """With no prior close, TR collapses to today's range."""
    df = _make_ohlc([(50.0, 40.0, 45.0)])
    out = add_true_range(df)
    assert out["true_range"][0] == pytest.approx(10.0, rel=1e-12)


def test_atr_seeded_sma_at_warmup_index() -> None:
    """At index ``length-1``, ATR equals the simple mean of the first ``length`` TR values."""
    n = 50
    length = 14
    pldf, _ = _synthetic_ohlc(n=n)
    out = add_atr(pldf, length=length)
    tr_first_n = pldf.with_columns(true_range_expr().alias("tr"))["tr"].to_numpy()[:length]
    expected_seed = float(np.mean(tr_first_n))
    assert out[f"atr_{length}"][: length - 1].is_null().all()
    assert out[f"atr_{length}"][length - 1] == pytest.approx(expected_seed, rel=1e-12)


@pytest.mark.parametrize("mamode", ["rma", "sma", "ema"])
def test_atr_matches_pandas_ta_within_1e6_relative(mamode: str) -> None:
    """1000-bar synthetic series, all three modes, max relative error < 1e-6."""
    pldf, pdf = _synthetic_ohlc()
    length = ATR_DEFAULT_LENGTH

    out = add_atr(pldf, length=length, mamode=mamode)  # type: ignore[arg-type]
    ours = out[out.columns[-1]].to_numpy()
    theirs = ta.atr(pdf["high"], pdf["low"], pdf["close"], length=length, mamode=mamode).to_numpy()

    mask = ~(np.isnan(theirs) | np.isnan(ours))
    assert mask.sum() > 900, f"unexpected NaN coverage for {mamode}: {mask.sum()}/1000"

    abs_diff = np.abs(ours[mask] - theirs[mask])
    rel_diff = abs_diff / np.maximum(np.abs(theirs[mask]), 1e-12)
    assert rel_diff.max() < 1e-6, f"{mamode}: max rel error {rel_diff.max():.3e} exceeds 1e-6"

    assert np.array_equal(np.isnan(ours), np.isnan(theirs)), (
        f"{mamode}: NaN pattern mismatch with pandas-ta"
    )


@pytest.mark.parametrize("length", [5, 14, 50])
def test_atr_default_rma_matches_pandas_ta_at_various_lengths(length: int) -> None:
    """Pin the seed-and-RMA equivalence at non-default lengths too."""
    pldf, pdf = _synthetic_ohlc()
    out = add_atr(pldf, length=length)
    ours = out[f"atr_{length}"].to_numpy()
    theirs = ta.atr(pdf["high"], pdf["low"], pdf["close"], length=length).to_numpy()
    mask = ~(np.isnan(theirs) | np.isnan(ours))
    rel = np.abs(ours[mask] - theirs[mask]) / np.maximum(np.abs(theirs[mask]), 1e-12)
    assert rel.max() < 1e-6


def test_atr_length_one_returns_true_range() -> None:
    """ATR with length=1 is degenerate: the smoothing is the identity, output equals TR."""
    pldf, _ = _synthetic_ohlc(n=50)
    out = add_atr(pldf, length=1)
    tr = pldf.with_columns(true_range_expr().alias("tr"))["tr"].to_numpy()
    atr1 = out["atr_1"].to_numpy()
    assert np.array_equal(np.isnan(tr), np.isnan(atr1))
    mask = ~np.isnan(tr)
    assert np.allclose(atr1[mask], tr[mask], rtol=1e-12)


def test_atr_length_larger_than_data_returns_all_null() -> None:
    """If ``length`` exceeds the row count, every ATR value is null."""
    pldf, _ = _synthetic_ohlc(n=10)
    out = add_atr(pldf, length=14)
    assert out["atr_14"].is_null().all()


def test_atr_zero_length_raises() -> None:
    pldf, _ = _synthetic_ohlc(n=50)
    with pytest.raises(ValueError, match="length"):
        add_atr(pldf, length=0)


def test_atr_negative_length_raises() -> None:
    pldf, _ = _synthetic_ohlc(n=50)
    with pytest.raises(ValueError, match="length"):
        add_atr(pldf, length=-3)


def test_atr_invalid_mamode_raises() -> None:
    pldf, _ = _synthetic_ohlc(n=50)
    with pytest.raises(ValueError, match="mamode"):
        add_atr(pldf, mamode="bogus")  # type: ignore[arg-type]


def test_atr_missing_columns_raises() -> None:
    df = pl.DataFrame({"high": [1.0], "low": [0.5]})
    with pytest.raises(ValueError, match="missing required columns"):
        add_atr(df)


def test_true_range_missing_columns_raises() -> None:
    df = pl.DataFrame({"high": [1.0], "close": [0.7]})
    with pytest.raises(ValueError, match="missing required columns"):
        add_true_range(df)


def test_add_atr_default_output_name_for_rma() -> None:
    pldf, _ = _synthetic_ohlc(n=50)
    out = add_atr(pldf, length=14)
    assert "atr_14" in out.columns


def test_add_atr_default_output_name_for_non_rma() -> None:
    pldf, _ = _synthetic_ohlc(n=50)
    out = add_atr(pldf, length=14, mamode="sma")
    assert "atr_sma_14" in out.columns
    out2 = add_atr(pldf, length=14, mamode="ema")
    assert "atr_ema_14" in out2.columns


def test_add_atr_custom_output_name() -> None:
    pldf, _ = _synthetic_ohlc(n=50)
    out = add_atr(pldf, length=14, output="my_atr")
    assert "my_atr" in out.columns
    assert "atr_14" not in out.columns


def test_add_atr_preserves_input_columns_and_row_count() -> None:
    pldf, _ = _synthetic_ohlc(n=50)
    pldf = pldf.with_columns(pl.lit("MNQ").alias("contract_symbol"))
    out = add_atr(pldf)
    assert out.height == pldf.height
    assert set(pldf.columns).issubset(set(out.columns))


def test_atr_expr_works_in_lazy_pipeline() -> None:
    """The Expr factory should compose into a LazyFrame chain."""
    pldf, _ = _synthetic_ohlc(n=50)
    out = (
        pldf.lazy()
        .with_columns(atr_expr(length=10).alias("atr_10"))
        .filter(pl.col("atr_10").is_not_null())
        .collect()
    )
    assert out.height == 50 - 9
    assert (out["atr_10"] > 0).all()


def test_atr_uses_custom_column_names() -> None:
    """When OHLC columns are renamed, kw args route around the rename."""
    pldf, pdf = _synthetic_ohlc(n=200)
    pldf_renamed = pldf.rename({"high": "h", "low": "l", "close": "c"})
    out = add_atr(pldf_renamed, length=14, high="h", low="l", close="c", output="atr")
    ours = out["atr"].to_numpy()
    theirs = ta.atr(pdf["high"], pdf["low"], pdf["close"], length=14).to_numpy()
    mask = ~(np.isnan(theirs) | np.isnan(ours))
    rel = np.abs(ours[mask] - theirs[mask]) / np.maximum(np.abs(theirs[mask]), 1e-12)
    assert rel.max() < 1e-6


def test_seed_with_sma_helper_pattern() -> None:
    """The internal seeder produces null for first n-1, SMA at n-1, identity after."""
    df = pl.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
    seeded = df.with_columns(atr_mod._seed_with_sma(pl.col("x"), length=3).alias("s"))[
        "s"
    ].to_list()
    assert seeded[0] is None
    assert seeded[1] is None
    assert seeded[2] == pytest.approx((1.0 + 2.0 + 3.0) / 3, rel=1e-12)
    assert seeded[3] == 4.0
    assert seeded[4] == 5.0
    assert seeded[5] == 6.0


_REAL_DATA_FILE = data_loader.default_data_root() / "MNQ 03-26.Last.txt"
_REAL_DATA_AVAILABLE = _REAL_DATA_FILE.is_file()
_REAL_DATA_SKIP_REASON = (
    f"Raw MNQ data not present at {_REAL_DATA_FILE}; skipping real-data ATR tests."
)


@pytest.fixture(scope="module")
def real_continuous() -> pl.DataFrame:
    """Full continuous MNQ dataset (cached per module)."""
    df = data_loader.load_all_contracts()
    return continuous_contract.build_continuous_contract(df)


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_atr14_warmup_and_population(real_continuous: pl.DataFrame) -> None:
    """ATR(14) on the full dataset: 13 leading nulls, all post-warmup positive and finite."""
    out = add_atr(real_continuous, length=14)
    atr = out["atr_14"]
    assert atr[:13].is_null().all()
    valid = atr[13:]
    assert valid.is_not_null().all()
    arr = valid.to_numpy()
    assert np.isfinite(arr).all()
    assert (arr > 0).all()


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_atr14_magnitude_in_expected_range(real_continuous: pl.DataFrame) -> None:
    """MNQ 1-min ATR(14) should sit in single-digit-points territory most of the time.

    A 1-min bar on /MNQ rarely exceeds ~25 points outside extreme regimes
    (e.g. early-COVID 2020-03 was the worst on record). The mean and
    median should be small (1-5 points); the max can spike but the
    99.9th percentile should still be well under 100.
    """
    out = add_atr(real_continuous, length=14)
    arr = out["atr_14"].drop_nulls().to_numpy()
    median = float(np.median(arr))
    p999 = float(np.percentile(arr, 99.9))
    assert 0.5 < median < 10.0, f"unexpected ATR(14) median: {median:.3f}"
    assert p999 < 100.0, f"unexpected ATR(14) 99.9th percentile: {p999:.3f}"


@pytest.mark.skipif(not _REAL_DATA_AVAILABLE, reason=_REAL_DATA_SKIP_REASON)
def test_real_atr_matches_pandas_ta_on_first_50k(real_continuous: pl.DataFrame) -> None:
    """First 50k bars of the real dataset: cross-check ATR(14) vs pandas-ta.

    Sized to keep the test fast (full 2.1M would be slow to round-trip
    through pandas) while still covering tens of trading days. Same
    1e-6 tolerance as the synthetic test.
    """
    head = real_continuous.head(50_000)
    out = add_atr(head, length=14)
    ours = out["atr_14"].to_numpy()
    pdf = head.select("high", "low", "close").to_pandas()
    theirs = ta.atr(pdf["high"], pdf["low"], pdf["close"], length=14).to_numpy()
    mask = ~(np.isnan(theirs) | np.isnan(ours))
    rel = np.abs(ours[mask] - theirs[mask]) / np.maximum(np.abs(theirs[mask]), 1e-12)
    assert rel.max() < 1e-6
