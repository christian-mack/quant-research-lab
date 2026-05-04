"""Tick grid and post-fill price adjustment (slippage)."""

from __future__ import annotations

from quant_research.backtest.specs import InstrumentSpec, SlippageMode, SlippageSide, SlippageSpec
from quant_research.backtest.types import OrderSide


def snap_to_tick(price: float, instrument: InstrumentSpec) -> float:
    """Round to nearest valid tick. Raises if ``tick_size`` is non-positive."""
    tick = instrument.tick_size
    if tick <= 0.0:
        msg = "tick_size must be positive"
        raise ValueError(msg)
    steps = round(price / tick)
    rounded = steps * tick
    if not instrument.strict_tick_grid:
        return rounded
    return rounded


def apply_slippage(
    price: float,
    side: OrderSide,
    spec: SlippageSpec,
    instrument: InstrumentSpec,
) -> float:
    """Apply slippage in the **adverse** direction (worse fill), then snap.

    ``FIXED_TICKS`` / ``FIXED_POINTS`` add magnitude away from the trader for
    ``ADVERSE_ONLY``; ``SYMMETRIC`` uses the same magnitude for both sides
    (still adverse for buy = higher, for sell = lower).
    """
    tick = instrument.tick_size
    if spec.mode == SlippageMode.NONE:
        adj = price
    elif spec.mode == SlippageMode.FIXED_TICKS:
        delta = spec.ticks * tick
        adj = _adverse_raw(price, side, delta, spec.side)
    elif spec.mode == SlippageMode.FIXED_POINTS:
        adj = _adverse_raw(price, side, spec.points, spec.side)
    else:
        msg = f"unknown slippage mode: {spec.mode!r}"
        raise ValueError(msg)
    return snap_to_tick(adj, instrument)


def _adverse_raw(price: float, side: OrderSide, delta: float, slip_side: SlippageSide) -> float:
    if slip_side == SlippageSide.SYMMETRIC:
        # Same convention as adverse: buy pays more, sell receives less.
        if side == OrderSide.BUY:
            return price + delta
        return price - delta
    if side == OrderSide.BUY:
        return price + delta
    return price - delta
