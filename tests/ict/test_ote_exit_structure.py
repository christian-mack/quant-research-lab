"""Tests for Phase 3 step 3d OTE exit structure remapping."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl

from quant_research.ict.ote_exit_structure import (
    STEP3D_COMBOS,
    apply_exit_structure,
    compute_stop_price,
    compute_target_price,
    remap_setups_for_combo,
)
from quant_research.ict.ote_strategy import DIRECTION_LONG, DIRECTION_SHORT, OteSetup

CT = ZoneInfo("America/Chicago")


def _setup(*, direction: str = DIRECTION_LONG, entry: float = 100.0) -> OteSetup:
    stop_a = 85.0 if direction == DIRECTION_LONG else 115.0
    target_n = 113.0 if direction == DIRECTION_LONG else 87.0
    return OteSetup(
        direction=direction,
        session_date=dt.date(2024, 1, 2),
        sweep_level=90.0,
        sweep_side="low",
        sweep_penetration_index=1,
        sweep_close_back_index=2,
        swept_extreme=84.0 if direction == DIRECTION_LONG else 116.0,
        mss_index=3,
        mss_swing_broken=95.0,
        displacement_low=88.0,
        displacement_high=102.0,
        equilibrium=95.0,
        fvg_top=99.0,
        fvg_bottom=98.0,
        fvg_c2_index=3,
        fvg_ote_conflict=False,
        fvg_ote_distance_ticks=None,
        entry_price=entry,
        ote_level_pct=0.705,
        entry_fill_index=5,
        entry_fill_timestamp=dt.datetime(2024, 1, 2, 9, 45, tzinfo=CT),
        stop_arm_a=stop_a,
        stop_arm_b=97.0 if direction == DIRECTION_LONG else 103.0,
        stop_price=stop_a,
        target_nearest=target_n,
        target_nearest_kind="fractal_high",
        target_far=120.0 if direction == DIRECTION_LONG else 80.0,
        target_far_kind="fractal_high_far",
        target_price=target_n,
        signal_index=3,
        signal_timestamp=dt.datetime(2024, 1, 2, 9, 30, tzinfo=CT),
    )


def _session(atr_at_5: float | None = 5.0) -> pl.DataFrame:
    n = 10
    atrs = [None] * n
    if atr_at_5 is not None:
        atrs[5] = atr_at_5
    return pl.DataFrame({"atr_14": atrs})


def test_fixed_10pt_stop_long() -> None:
    s = _setup(direction=DIRECTION_LONG, entry=100.0)
    stop = compute_stop_price(s, "fixed_10pt", atr=None)
    assert stop == 90.0


def test_fixed_2r_target_long() -> None:
    s = _setup(direction=DIRECTION_LONG, entry=100.0)
    stop = 90.0
    target = compute_target_price(s, "fixed_2r", stop_price=stop, atr=None)
    assert target == 120.0


def test_c2_combo_geometry_passes() -> None:
    s = _setup()
    sess = _session()
    remapped, reason = apply_exit_structure(s, STEP3D_COMBOS["C-2"], sess)
    assert reason is None
    assert remapped is not None
    assert remapped.stop_price == 90.0
    assert remapped.target_price == 115.0


def test_c3_requires_atr() -> None:
    s = _setup()
    sess = pl.DataFrame({"atr_14": [None] * 10})
    remapped, reason = apply_exit_structure(s, STEP3D_COMBOS["C-3"], sess)
    assert remapped is None
    assert reason == "atr_unavailable"


def test_remap_counts_geometry_rejects() -> None:
    from dataclasses import replace

    s = _setup(direction=DIRECTION_SHORT, entry=100.0)
    bad = replace(s, target_nearest=105.0, target_price=105.0)
    setups, rejects = remap_setups_for_combo(
        [bad], {s.session_date: _session()}, STEP3D_COMBOS["C-base"]
    )
    assert len(setups) == 0
    assert sum(rejects.values()) == 1
