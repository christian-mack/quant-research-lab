"""Phase 3 step 3d — realistic OTE exit structures (stop + target pairs).

Entry logic is frozen (OTE 70.5% from step 3d scan). This module remaps
``stop_price`` / ``target_price`` on pre-detected :class:`OteSetup` rows before
M4 execution.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, Literal

import polars as pl

from quant_research.backtest.geometry import check_trade_geometry
from quant_research.ict.ote_strategy import DIRECTION_LONG, OteSetup

StopRule = Literal["swept_extreme", "fixed_10pt", "atr_1x"]
TargetRule = Literal["nearest_pool", "fixed_15pt", "atr_2x", "fixed_2r"]

STOP_SWEPT_EXTREME: Final[str] = "swept_extreme"
STOP_FIXED_10PT: Final[str] = "fixed_10pt"
STOP_ATR_1X: Final[str] = "atr_1x"

TARGET_NEAREST_POOL: Final[str] = "nearest_pool"
TARGET_FIXED_15PT: Final[str] = "fixed_15pt"
TARGET_ATR_2X: Final[str] = "atr_2x"
TARGET_FIXED_2R: Final[str] = "fixed_2r"

FIXED_STOP_POINTS: Final[float] = 10.0
FIXED_TARGET_POINTS: Final[float] = 15.0
ATR_STOP_MULT: Final[float] = 1.0
ATR_TARGET_MULT: Final[float] = 2.0
TARGET_RR_MULT: Final[float] = 2.0
DEFAULT_TICK_SIZE: Final[float] = 0.25
ATR_COL: Final[str] = "atr_14"


@dataclass(frozen=True, slots=True)
class ExitStructureCombo:
    """Pre-registered stop + target pair for step 3d."""

    combo_id: str
    stop_rule: StopRule
    target_rule: TargetRule
    rationale: str


STEP3D_COMBOS: dict[str, ExitStructureCombo] = {
    "C-base": ExitStructureCombo(
        "C-base",
        STOP_SWEPT_EXTREME,
        TARGET_NEAREST_POOL,
        "Current baseline: swept-extreme stop + nearest opposing pool target.",
    ),
    "C-1": ExitStructureCombo(
        "C-1",
        STOP_SWEPT_EXTREME,
        TARGET_FIXED_2R,
        "Keep structural stop; force 2R target — tests entry quality for 2R.",
    ),
    "C-2": ExitStructureCombo(
        "C-2",
        STOP_FIXED_10PT,
        TARGET_FIXED_15PT,
        "Fixed 10pt stop + 15pt target (1.5R tradeable structure).",
    ),
    "C-3": ExitStructureCombo(
        "C-3",
        STOP_ATR_1X,
        TARGET_ATR_2X,
        "1.0× ATR(14) stop + 2.0× ATR(14) target — regime-adaptive 2:1.",
    ),
    "C-4": ExitStructureCombo(
        "C-4",
        STOP_FIXED_10PT,
        TARGET_FIXED_2R,
        "Fixed 10pt stop + 2R target (= 20pt target).",
    ),
}


def round_to_tick(price: float, tick_size: float = DEFAULT_TICK_SIZE) -> float:
    """Round price to nearest instrument tick."""
    return round(price / tick_size) * tick_size


def compute_stop_price(
    setup: OteSetup,
    rule: StopRule,
    *,
    atr: float | None,
    tick_size: float = DEFAULT_TICK_SIZE,
) -> float | None:
    """Return stop price for ``rule``, or ``None`` when inputs are insufficient."""
    entry = setup.entry_price
    if rule == STOP_SWEPT_EXTREME:
        return setup.stop_arm_a
    if rule == STOP_FIXED_10PT:
        if setup.direction == DIRECTION_LONG:
            return round_to_tick(entry - FIXED_STOP_POINTS, tick_size)
        return round_to_tick(entry + FIXED_STOP_POINTS, tick_size)
    if rule == STOP_ATR_1X:
        if atr is None or atr <= 0:
            return None
        dist = ATR_STOP_MULT * atr
        if setup.direction == DIRECTION_LONG:
            return round_to_tick(entry - dist, tick_size)
        return round_to_tick(entry + dist, tick_size)
    raise ValueError(f"unknown stop rule: {rule!r}")


def compute_target_price(
    setup: OteSetup,
    rule: TargetRule,
    *,
    stop_price: float,
    atr: float | None,
    tick_size: float = DEFAULT_TICK_SIZE,
) -> float | None:
    """Return target price for ``rule``, or ``None`` when inputs are insufficient."""
    entry = setup.entry_price
    if rule == TARGET_NEAREST_POOL:
        return setup.target_nearest
    if rule == TARGET_FIXED_15PT:
        if setup.direction == DIRECTION_LONG:
            return round_to_tick(entry + FIXED_TARGET_POINTS, tick_size)
        return round_to_tick(entry - FIXED_TARGET_POINTS, tick_size)
    if rule == TARGET_ATR_2X:
        if atr is None or atr <= 0:
            return None
        dist = ATR_TARGET_MULT * atr
        if setup.direction == DIRECTION_LONG:
            return round_to_tick(entry + dist, tick_size)
        return round_to_tick(entry - dist, tick_size)
    if rule == TARGET_FIXED_2R:
        risk = abs(entry - stop_price)
        reward = TARGET_RR_MULT * risk
        if setup.direction == DIRECTION_LONG:
            return round_to_tick(entry + reward, tick_size)
        return round_to_tick(entry - reward, tick_size)
    raise ValueError(f"unknown target rule: {rule!r}")


def atr_at_entry(
    session_df: pl.DataFrame,
    entry_fill_index: int,
    *,
    atr_col: str = ATR_COL,
) -> float | None:
    """Look up session ATR at the entry bar."""
    if atr_col not in session_df.columns or entry_fill_index >= session_df.height:
        return None
    val = session_df[atr_col][entry_fill_index]
    if val is None:
        return None
    fval = float(val)
    if fval != fval or fval <= 0:  # NaN check
        return None
    return fval


def apply_exit_structure(
    setup: OteSetup,
    combo: ExitStructureCombo,
    session_df: pl.DataFrame,
    *,
    tick_size: float = DEFAULT_TICK_SIZE,
    atr_col: str = ATR_COL,
) -> tuple[OteSetup | None, str | None]:
    """Remap stop/target on one setup; return reject reason if geometry fails."""
    fill_idx = setup.entry_fill_index
    if fill_idx is None:
        return None, "no_fill"
    atr = (
        atr_at_entry(session_df, fill_idx, atr_col=atr_col)
        if combo.stop_rule == STOP_ATR_1X or combo.target_rule == TARGET_ATR_2X
        else None
    )
    stop = compute_stop_price(setup, combo.stop_rule, atr=atr, tick_size=tick_size)
    if stop is None:
        return None, "atr_unavailable"
    target = compute_target_price(
        setup, combo.target_rule, stop_price=stop, atr=atr, tick_size=tick_size
    )
    if target is None:
        return None, "atr_unavailable"
    reject = check_trade_geometry(setup.direction, setup.entry_price, stop, target)
    if reject is not None:
        return None, reject.reason
    remapped = replace(setup, stop_price=stop, target_price=target)
    return remapped, None


def remap_setups_for_combo(
    setups: list[OteSetup],
    sessions: dict[object, pl.DataFrame],
    combo: ExitStructureCombo,
    *,
    tick_size: float = DEFAULT_TICK_SIZE,
) -> tuple[list[OteSetup], dict[str, int]]:
    """Apply exit structure to all setups; count geometry/ATR rejects."""
    out: list[OteSetup] = []
    rejects: dict[str, int] = {}
    for setup in setups:
        if setup.session_date is None or setup.entry_fill_index is None:
            continue
        sess = sessions.get(setup.session_date)
        if sess is None:
            continue
        remapped, reason = apply_exit_structure(setup, combo, sess, tick_size=tick_size)
        if remapped is None:
            key = reason or "unknown"
            rejects[key] = rejects.get(key, 0) + 1
            continue
        out.append(remapped)
    return out, rejects
