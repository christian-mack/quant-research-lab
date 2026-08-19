"""Tests for :mod:`quant_research.ict.smt` (Primitive 4 — SMT divergence).

Hand-constructed divergence and aligned cases across two and three instruments,
including the TTrades "8:35 NASDAQ takes the lows -> SMT" example (@312s).
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.ict.smt import (
    DIRECTION_BEARISH,
    DIRECTION_BULLISH,
    detect_smt_from_frames,
    smt_divergence,
)

CT = ZoneInfo("America/Chicago")


def test_bullish_smt_two_instruments_present() -> None:
    """NQ lower low, ES higher low -> bullish SMT; ES is the diverging instrument."""
    res = smt_divergence(
        prior_levels={"MNQ": 100.0, "MES": 50.0},
        current_extremes={"MNQ": 98.0, "MES": 51.0},  # NQ took lows, ES held
        direction=DIRECTION_BULLISH,
    )
    assert res.present is True
    assert res.took_out == {"MNQ": True, "MES": False}
    assert res.diverged_instruments == ["MES"]


def test_bearish_smt_two_instruments_present() -> None:
    """SP lower high, Dow higher high -> bearish SMT; MES is diverging (lower high)."""
    res = smt_divergence(
        prior_levels={"MES": 50.0, "MYM": 400.0},
        current_extremes={"MES": 49.0, "MYM": 402.0},  # YM took highs, ES held
        direction=DIRECTION_BEARISH,
    )
    assert res.present is True
    assert res.took_out == {"MES": False, "MYM": True}
    assert res.diverged_instruments == ["MES"]


def test_aligned_lows_no_smt() -> None:
    """Both instruments make lower lows (aligned) -> no divergence."""
    res = smt_divergence(
        prior_levels={"MNQ": 100.0, "MES": 50.0},
        current_extremes={"MNQ": 98.0, "MES": 49.0},
        direction=DIRECTION_BULLISH,
    )
    assert res.present is False
    assert res.diverged_instruments == []


def test_aligned_highs_no_smt() -> None:
    """Both instruments make higher highs (aligned) -> no divergence."""
    res = smt_divergence(
        prior_levels={"MES": 50.0, "MYM": 400.0},
        current_extremes={"MES": 51.0, "MYM": 402.0},
        direction=DIRECTION_BEARISH,
    )
    assert res.present is False


def test_equal_low_is_neither_higher_nor_lower() -> None:
    """A double bottom (equal low) is not a strict higher/lower low."""
    # MNQ lower low, MES exactly equal -> only one side strict -> no SMT.
    res = smt_divergence(
        prior_levels={"MNQ": 100.0, "MES": 50.0},
        current_extremes={"MNQ": 98.0, "MES": 50.0},
        direction=DIRECTION_BULLISH,
    )
    assert res.present is False


def test_three_instruments_one_diverges() -> None:
    """NQ takes lows; ES and YM both hold -> bullish SMT, two diverging instruments."""
    res = smt_divergence(
        prior_levels={"MNQ": 100.0, "MES": 50.0, "MYM": 400.0},
        current_extremes={"MNQ": 97.0, "MES": 51.0, "MYM": 401.0},
        direction=DIRECTION_BULLISH,
    )
    assert res.present is True
    assert res.took_out == {"MNQ": True, "MES": False, "MYM": False}
    assert set(res.diverged_instruments) == {"MES", "MYM"}


def test_three_instruments_all_aligned_no_smt() -> None:
    res = smt_divergence(
        prior_levels={"MNQ": 100.0, "MES": 50.0, "MYM": 400.0},
        current_extremes={"MNQ": 97.0, "MES": 49.0, "MYM": 399.0},
        direction=DIRECTION_BULLISH,
    )
    assert res.present is False


def test_mismatched_instruments_raises() -> None:
    with pytest.raises(ValueError, match="same instruments"):
        smt_divergence(
            prior_levels={"MNQ": 100.0, "MES": 50.0},
            current_extremes={"MNQ": 98.0},
            direction=DIRECTION_BULLISH,
        )


def test_single_instrument_raises() -> None:
    with pytest.raises(ValueError, match="at least two instruments"):
        smt_divergence({"MNQ": 100.0}, {"MNQ": 98.0}, direction=DIRECTION_BULLISH)


def test_invalid_direction_raises() -> None:
    with pytest.raises(ValueError, match="direction must be"):
        smt_divergence({"A": 1.0, "B": 2.0}, {"A": 1.0, "B": 2.0}, direction="x")


# --- frame-based extraction ---


def _two_bar_frame(prior_low: float, current_low: float, prior_high: float, current_high: float):
    """Frame with one bar in the prior window (08:30) and one in the current (09:30)."""
    return pl.DataFrame(
        {
            "timestamp": [
                dt.datetime(2024, 6, 10, 8, 30, tzinfo=CT),
                dt.datetime(2024, 6, 10, 9, 30, tzinfo=CT),
            ],
            "high": [prior_high, current_high],
            "low": [prior_low, current_low],
        }
    )


def test_detect_smt_from_frames_8_35_nasdaq_takes_lows() -> None:
    """@312s style: at the swing, NASDAQ takes the prior low; ES/YM hold -> bullish SMT."""
    prior_w = (
        dt.datetime(2024, 6, 10, 8, 0, tzinfo=CT),
        dt.datetime(2024, 6, 10, 9, 0, tzinfo=CT),
    )
    current_w = (
        dt.datetime(2024, 6, 10, 9, 0, tzinfo=CT),
        dt.datetime(2024, 6, 10, 10, 0, tzinfo=CT),
    )
    frames = {
        "MNQ": _two_bar_frame(prior_low=100.0, current_low=98.0, prior_high=110, current_high=108),
        "MES": _two_bar_frame(prior_low=50.0, current_low=51.0, prior_high=55, current_high=54),
        "MYM": _two_bar_frame(prior_low=400.0, current_low=401.0, prior_high=410, current_high=409),
    }
    res = detect_smt_from_frames(
        frames, direction=DIRECTION_BULLISH, prior_window=prior_w, current_window=current_w
    )
    assert res.present is True
    assert res.took_out["MNQ"] is True
    assert set(res.diverged_instruments) == {"MES", "MYM"}
    assert res.swing_window == current_w


def test_detect_smt_from_frames_uses_window_extremes() -> None:
    """Min low over a multi-bar window is used as the swing extreme."""
    prior_w = (
        dt.datetime(2024, 6, 10, 8, 0, tzinfo=CT),
        dt.datetime(2024, 6, 10, 9, 0, tzinfo=CT),
    )
    current_w = (
        dt.datetime(2024, 6, 10, 9, 0, tzinfo=CT),
        dt.datetime(2024, 6, 10, 10, 0, tzinfo=CT),
    )

    def frame(lows_prior, lows_cur):
        ts = [
            dt.datetime(2024, 6, 10, 8, 0, tzinfo=CT),
            dt.datetime(2024, 6, 10, 8, 30, tzinfo=CT),
            dt.datetime(2024, 6, 10, 9, 0, tzinfo=CT),
            dt.datetime(2024, 6, 10, 9, 30, tzinfo=CT),
        ]
        lows = lows_prior + lows_cur
        return pl.DataFrame({"timestamp": ts, "high": [x + 5 for x in lows], "low": lows})

    frames = {
        "MNQ": frame([102.0, 100.0], [99.0, 98.0]),  # prior min 100, current min 98 -> lower low
        "MES": frame([52.0, 50.0], [51.0, 53.0]),  # prior min 50, current min 51 -> higher low
    }
    res = detect_smt_from_frames(
        frames, direction=DIRECTION_BULLISH, prior_window=prior_w, current_window=current_w
    )
    assert res.prior_levels == {"MNQ": pytest.approx(100.0), "MES": pytest.approx(50.0)}
    assert res.current_extremes == {"MNQ": pytest.approx(98.0), "MES": pytest.approx(51.0)}
    assert res.present is True


def test_detect_smt_from_frames_empty_window_raises() -> None:
    prior_w = (
        dt.datetime(2024, 6, 10, 8, 0, tzinfo=CT),
        dt.datetime(2024, 6, 10, 9, 0, tzinfo=CT),
    )
    # current window with no bars
    current_w = (
        dt.datetime(2024, 6, 10, 12, 0, tzinfo=CT),
        dt.datetime(2024, 6, 10, 13, 0, tzinfo=CT),
    )
    frames = {
        "MNQ": _two_bar_frame(100.0, 98.0, 110, 108),
        "MES": _two_bar_frame(50.0, 51.0, 55, 54),
    }
    with pytest.raises(ValueError, match="no bars in the current window"):
        detect_smt_from_frames(
            frames, direction=DIRECTION_BULLISH, prior_window=prior_w, current_window=current_w
        )
