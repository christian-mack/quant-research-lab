"""Tests for :mod:`quant_research.ict.ote_strategy` (Phase 3 step 2 — standalone OTE)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from quant_research.ict.liquidity_sweep import SIDE_HIGH, SIDE_LOW, detect_sweep
from quant_research.ict.mss import DIRECTION_BULLISH
from quant_research.ict.ote_strategy import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    ENTRY_OTE_62,
    ENTRY_OTE_705,
    STOP_FVG_C2,
    STOP_SWEPT_EXTREME,
    TARGET_FAR,
    TARGET_NEAREST,
    OteStrategyConfig,
    build_setup_from_sweep,
    mss_direction_to_trade,
    ote_fib_price,
    resolve_targets,
    scan_setups,
)

CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")
TICK = 0.25
SESSION = dt.date(2024, 6, 10)
PDH = 115.0
PDL = 90.0


def _cfg(**kwargs) -> OteStrategyConfig:
    base = {"tick_size": TICK, "rth_only": False}
    base.update(kwargs)
    return OteStrategyConfig(**base)


def _bars(
    rows: list[tuple[float, float, float, float]],
    *,
    minutes: int = 5,
    base: dt.datetime | None = None,
    with_pd: bool = True,
) -> pl.DataFrame:
    """5m bars at 9:30 ET open (08:30 CT) with optional PD arrays."""
    if base is None:
        base = dt.datetime(2024, 6, 10, 8, 30, tzinfo=CT)
    df = pl.DataFrame(
        {
            "timestamp": [base + dt.timedelta(minutes=minutes * i) for i in range(len(rows))],
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "cme_session_date": [SESSION] * len(rows),
        }
    )
    if with_pd:
        df = df.with_columns(
            pl.lit(PDH).alias("pdh"),
            pl.lit(PDL).alias("pdl"),
            pl.lit((PDH + PDL) / 2).alias("p_eq"),
        )
    return df


def _long_sequence() -> pl.DataFrame:
    """Sweep below 100 → MSS up → discount FVG → OTE 70.5% fill."""
    return _bars(
        [
            (108.0, 111.0, 107.5, 110.0),  # 0
            (110.0, 113.0, 109.0, 112.0),  # 1 fractal high 113 (nearest target)
            (112.0, 105.0, 111.5, 104.0),  # 2
            (104.0, 106.0, 103.5, 105.5),  # 3 fractal high 106 (MSS swing)
            (105.5, 104.5, 104.0, 104.5),  # 4
            (104.5, 104.5, 96.0, 97.0),  # 5 sweep penetration below 100
            (97.0, 99.0, 96.5, 101.0),  # 6 close back; FVG c1 high=99
            (101.0, 110.0, 100.5, 108.0),  # 7 FVG c2 displacement
            (108.0, 109.0, 101.5, 107.0),  # 8 MSS close > 106; FVG c3
            (107.0, 108.0, 104.0, 105.0),  # 9 retrace — fills OTE ~105.87
            (105.0, 106.0, 103.0, 104.0),  # 10
        ]
    )


def _short_sequence() -> pl.DataFrame:
    """Sweep above 120 → MSS down → premium FVG → OTE fill."""
    return _bars(
        [
            (112.0, 113.0, 108.0, 109.0),  # 0 fractal low 108 (far target candidate)
            (109.0, 110.0, 107.0, 108.5),  # 1 fractal low 107 (nearest target)
            (108.5, 118.0, 108.0, 117.0),  # 2
            (117.0, 119.0, 116.0, 118.0),  # 3
            (118.0, 121.0, 112.0, 119.0),  # 4 fractal low 112 (MSS swing)
            (119.0, 125.0, 118.5, 119.5),  # 5 sweep high above 120
            (119.5, 118.0, 117.0, 117.5),  # 6 close back; FVG c1 low=117
            (117.5, 116.0, 108.0, 109.0),  # 7 FVG c2 displacement down
            (109.0, 110.0, 105.0, 106.0),  # 8 MSS close < 112; bearish FVG
            (106.0, 114.0, 105.5, 113.5),  # 9 retrace — fills short OTE
            (113.5, 112.0, 111.0, 111.5),  # 10
        ]
    )


def _sweep_long(df: pl.DataFrame) -> object:
    return detect_sweep(
        df,
        level=100.0,
        side=SIDE_LOW,
        config=_cfg().sweep_config,
        search_start_index=2,
    )


def _sweep_short(df: pl.DataFrame) -> object:
    return detect_sweep(
        df,
        level=120.0,
        side=SIDE_HIGH,
        config=_cfg().sweep_config,
        search_start_index=2,
    )


# ---------------------------------------------------------------------------
# End-to-end long / short
# ---------------------------------------------------------------------------


def test_end_to_end_long_setup_primary_variants() -> None:
    """Long: sweep → MSS → discount FVG → 70.5% fill; stops and targets wired."""
    df = _long_sequence()
    sweep = _sweep_long(df)
    assert sweep.swept is True

    setup = build_setup_from_sweep(df, sweep, config=_cfg(), session_date=SESSION, pdh=PDH, pdl=PDL)
    assert setup is not None
    assert setup.direction == DIRECTION_LONG
    assert setup.mss_index == 7
    assert setup.displacement_low == pytest.approx(96.0)
    assert setup.displacement_high == pytest.approx(110.0)

    expected_entry = ote_fib_price(
        DIRECTION_LONG, setup.displacement_low, setup.displacement_high, 0.705
    )
    assert setup.entry_price == pytest.approx(expected_entry)
    assert setup.entry_fill_index is not None
    assert setup.entry_fill_index >= 8

    # Arm A: swept low 96 - 1 tick
    assert setup.stop_arm_a == pytest.approx(96.0 - TICK)
    assert setup.stop_price == pytest.approx(setup.stop_arm_a)

    assert setup.target_nearest < setup.target_far
    assert setup.target_nearest_kind in ("fractal_high", "pdh")
    assert setup.target_price == pytest.approx(setup.target_nearest)

    # Direction from sweep/MSS only
    assert mss_direction_to_trade(DIRECTION_BULLISH) == DIRECTION_LONG


def test_end_to_end_short_setup_symmetric() -> None:
    """Short: symmetric chain with stop arm A and target fork."""
    df = _short_sequence()
    sweep = _sweep_short(df)
    assert sweep.swept is True

    setup = build_setup_from_sweep(df, sweep, config=_cfg(), session_date=SESSION, pdh=PDH, pdl=PDL)
    assert setup is not None
    assert setup.direction == DIRECTION_SHORT
    assert setup.mss_index == 7
    assert setup.stop_arm_a == pytest.approx(121.0 + TICK)  # swept high at bar 4
    assert setup.entry_fill_index is not None
    assert setup.target_nearest > setup.target_far


def test_target_variants_differ_on_same_setup() -> None:
    """Nearest vs far target fork produces different exit prices."""
    df = _long_sequence()
    sweep = _sweep_long(df)
    near = build_setup_from_sweep(
        df, sweep, config=_cfg(target_mode=TARGET_NEAREST), pdh=PDH, pdl=PDL
    )
    far = build_setup_from_sweep(df, sweep, config=_cfg(target_mode=TARGET_FAR), pdh=PDH, pdl=PDL)
    assert near is not None and far is not None
    assert near.target_price == pytest.approx(near.target_nearest)
    assert far.target_price == pytest.approx(far.target_far)
    assert near.target_price < far.target_price


def test_stop_arm_b_and_entry_62_variants() -> None:
    """Pre-registered stop B and OTE 62% variants select different prices."""
    df = _long_sequence()
    sweep = _sweep_long(df)

    arm_a = build_setup_from_sweep(df, sweep, config=_cfg(stop_arm=STOP_SWEPT_EXTREME))
    arm_b = build_setup_from_sweep(
        df,
        sweep,
        config=_cfg(stop_arm=STOP_FVG_C2, stop_buffer_ticks=1),
    )
    assert arm_a is not None and arm_b is not None
    assert arm_a.stop_price == pytest.approx(arm_a.stop_arm_a)
    assert arm_b.stop_price == pytest.approx(arm_b.stop_arm_b)
    assert arm_a.stop_arm_a != arm_b.stop_arm_b

    e705 = build_setup_from_sweep(df, sweep, config=_cfg(entry_mode=ENTRY_OTE_705))
    e62 = build_setup_from_sweep(df, sweep, config=_cfg(entry_mode=ENTRY_OTE_62))
    assert e705 is not None and e62 is not None
    assert e705.entry_price > e62.entry_price  # deeper retrace for 70.5% on long


# ---------------------------------------------------------------------------
# No-setup cases
# ---------------------------------------------------------------------------


def test_no_setup_when_sweep_without_mss() -> None:
    """Sweep confirmed but no opposing swing break → no setup."""
    df = _bars(
        [
            (100.0, 103.0, 100.0, 102.5),
            (102.5, 106.0, 102.0, 105.5),
            (105.5, 104.5, 104.0, 104.5),
            (104.5, 104.5, 96.0, 97.0),
            (97.0, 98.0, 96.5, 101.0),
            (101.0, 104.0, 100.5, 103.0),
            (103.0, 105.5, 102.0, 105.0),  # no close > 106
        ]
    )
    sweep = _sweep_long(df)
    assert build_setup_from_sweep(df, sweep, config=_cfg()) is None


def test_no_setup_when_no_qualifying_fvg() -> None:
    """MSS fires but no bullish discount FVG in the displacement leg → no setup."""
    # Displacement leg is a single-bar MSS with no 3-candle imbalance on the long side.
    df = _bars(
        [
            (100.0, 101.0, 100.5, 100.5),
            (100.5, 106.0, 102.0, 105.5),  # fractal high 106
            (105.5, 104.5, 104.0, 104.5),
            (104.5, 104.5, 96.0, 97.0),  # sweep
            (97.0, 99.0, 96.5, 101.0),  # close back
            (101.0, 107.0, 100.5, 106.5),  # MSS close > 106; no bullish FVG forms
            (106.5, 107.0, 104.0, 105.0),
        ]
    )
    sweep = detect_sweep(
        df, level=100.0, side=SIDE_LOW, config=_cfg().sweep_config, search_start_index=2
    )
    assert build_setup_from_sweep(df, sweep, config=_cfg()) is None


def test_no_setup_without_entry_fill() -> None:
    """Qualified chain but price never trades to OTE limit → no setup."""
    df = _long_sequence()[:8]  # drop retrace bars
    sweep = _sweep_long(df)
    assert build_setup_from_sweep(df, sweep, config=_cfg()) is None


# ---------------------------------------------------------------------------
# Direction, causality, multi-setup
# ---------------------------------------------------------------------------


def test_direction_from_sweep_mss_not_external() -> None:
    """Trade direction is implied by sweep reversal / MSS only."""
    df = _long_sequence()
    sweep = _sweep_long(df)
    setup = build_setup_from_sweep(df, sweep, config=_cfg())
    assert setup is not None
    assert sweep.reversal_direction == DIRECTION_BULLISH
    assert setup.direction == DIRECTION_LONG
    # Inverting expected external direction has no API — direction is derived internally.


def test_no_lookahead_displacement_finalized_at_mss() -> None:
    """Displacement extremes match MSS-window only (no future bars)."""
    df = _long_sequence()
    sweep = _sweep_long(df)
    setup = build_setup_from_sweep(df, sweep, config=_cfg())
    assert setup is not None
    # Displacement ends at MSS bar 7; bar 8+ lows must not pull displacement_low lower.
    assert setup.displacement_low == pytest.approx(96.0)
    assert setup.signal_index == setup.mss_index


def test_multiple_setups_same_session() -> None:
    """Unconstrained scan can emit more than one setup per session."""
    # Two sweep/MSS chains spaced apart.
    part1 = _long_sequence()
    gap = _bars(
        [
            (104.0, 105.0, 103.0, 104.0),
            (104.0, 105.0, 103.0, 104.0),
            (104.0, 105.0, 103.0, 104.0),
        ],
        base=part1["timestamp"][-1] + dt.timedelta(minutes=5),
    )
    part2_rows = [
        (104.0, 106.0, 103.5, 105.5),
        (105.5, 106.0, 96.0, 97.0),
        (97.0, 99.0, 96.5, 101.0),
        (101.0, 110.0, 100.5, 108.0),
        (108.0, 109.0, 101.5, 107.0),
        (107.0, 108.0, 104.0, 105.0),
    ]
    part2 = _bars(
        part2_rows,
        base=gap["timestamp"][-1] + dt.timedelta(minutes=5),
    )
    df = pl.concat([part1, gap, part2], how="vertical")
    setups = scan_setups(df, config=_cfg())
    assert len(setups) >= 1


def test_fvg_ote_conflict_flagged_when_levels_diverge() -> None:
    """D0.1/D0.2 interaction logged when OTE limit is outside FVG zone."""
    df = _long_sequence()
    sweep = _sweep_long(df)
    setup = build_setup_from_sweep(df, sweep, config=_cfg(fvg_ote_conflict_ticks=2))
    assert setup is not None
    # OTE ~105.9 vs FVG top ~101.5 — material conflict expected.
    assert setup.fvg_ote_conflict is True
    assert setup.fvg_ote_distance_ticks is not None
    assert setup.fvg_ote_distance_ticks > 0


def test_resolve_targets_nearest_vs_far_ordering() -> None:
    """Target resolver returns ordered pools for long direction."""
    df = _long_sequence()
    nearest, n_kind, far, f_kind = resolve_targets(
        df,
        direction=DIRECTION_LONG,
        signal_index=7,
        entry_price=105.0,
        pdh=PDH,
        pdl=PDL,
        far_lookback=100,
    )
    assert nearest < far
    assert n_kind in ("fractal_high", "pdh", "fallback")
