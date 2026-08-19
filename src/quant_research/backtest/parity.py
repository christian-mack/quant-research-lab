"""Hand-computed ground truth for OTE fills (M4-equivalent rules)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from quant_research.backtest.fill_resolution import slippage_for_tag
from quant_research.backtest.specs import BacktestConfig
from quant_research.backtest.tick import apply_slippage
from quant_research.ict.ote_execution import (
    COMMISSION_PER_FILL,
    OTE_ENTRY_TAG,
    OTE_STOP_TAG,
    OTE_TARGET_TAG,
    SLIP_STOP_TICKS,
    SLIP_TARGET_TICKS,
    ote_research_backtest_config,
)
from quant_research.ict.ote_strategy import DIRECTION_LONG, OteSetup

MNQ_POINT_VALUE = 2.0


@dataclass(frozen=True)
class HandTraceResult:
    """Tick-exact hand trace under M4-equivalent stop-first + cost rules."""

    entry_price: float
    stop_price: float
    target_price: float
    exit_price: float
    exit_reason: str
    exit_bar: int
    gross_pnl: float
    commission: float
    net_pnl: float


def _slip_px(base: float, side: str, tag: str, config: BacktestConfig) -> float:
    from quant_research.backtest.types import OrderSide

    slip_spec = slippage_for_tag(tag, config.slippage)
    os_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
    return apply_slippage(base, os_side, slip_spec, config.instrument)


def hand_trace_setup(
    setup: OteSetup,
    sess: pl.DataFrame,
    *,
    config: BacktestConfig | None = None,
) -> HandTraceResult | None:
    """Hand-compute one OTE round-trip using M4 fill rules."""
    if setup.entry_fill_index is None:
        return None
    cfg = config or ote_research_backtest_config()
    direction = setup.direction
    entry_base = setup.entry_price
    stop_base = setup.stop_price
    target_base = setup.target_price
    fill_idx = setup.entry_fill_index

    entry_side = "buy" if direction == DIRECTION_LONG else "sell"
    entry_px = _slip_px(entry_base, entry_side, OTE_ENTRY_TAG, cfg)
    comm_entry = COMMISSION_PER_FILL

    highs = sess["high"].to_list()
    lows = sess["low"].to_list()
    closes = sess["close"].to_list()
    is_long = direction == DIRECTION_LONG
    exit_reason = "time"
    exit_base = closes[-1]
    exit_bar = len(closes) - 1
    exit_tag = "time"

    for i in range(fill_idx, len(closes)):
        if is_long:
            if lows[i] <= stop_base:
                exit_reason, exit_base, exit_bar, exit_tag = "stop", stop_base, i, OTE_STOP_TAG
                break
            if highs[i] >= target_base:
                exit_reason, exit_base, exit_bar, exit_tag = "target", target_base, i, OTE_TARGET_TAG
                break
        else:
            if highs[i] >= stop_base:
                exit_reason, exit_base, exit_bar, exit_tag = "stop", stop_base, i, OTE_STOP_TAG
                break
            if lows[i] <= target_base:
                exit_reason, exit_base, exit_bar, exit_tag = "target", target_base, i, OTE_TARGET_TAG
                break

    exit_side = "sell" if is_long else "buy"
    exit_px = _slip_px(exit_base, exit_side, exit_tag, cfg)
    comm_exit = COMMISSION_PER_FILL

    pts = (exit_px - entry_px) if is_long else (entry_px - exit_px)
    gross = pts * MNQ_POINT_VALUE
    commission = comm_entry + comm_exit
    net = gross - commission

    return HandTraceResult(
        entry_price=entry_px,
        stop_price=stop_base,
        target_price=target_base,
        exit_price=exit_px,
        exit_reason=exit_reason,
        exit_bar=exit_bar,
        gross_pnl=gross,
        commission=commission,
        net_pnl=net,
    )


def compare_m4_bespoke_hand(
    setup: OteSetup,
    sess: pl.DataFrame,
    *,
    m4_net: float,
    m4_gross: float,
    bespoke_net: float,
    config: BacktestConfig | None = None,
) -> dict[str, Any]:
    """Compare three P&L sources for one setup."""
    hand = hand_trace_setup(setup, sess, config=config)
    if hand is None:
        return {"setup": "no_fill"}
    m4_match = abs(m4_net - hand.net_pnl) < 0.02 and abs(m4_gross - hand.gross_pnl) < 0.02
    besp_match = abs(bespoke_net - hand.net_pnl) < 0.02
    winner = "hand"
    if m4_match:
        winner = "m4"
    elif besp_match:
        winner = "bespoke"
    elif abs(m4_net - hand.net_pnl) < abs(bespoke_net - hand.net_pnl):
        winner = "m4_closer"
    else:
        winner = "bespoke_closer"
    return {
        "session": str(setup.session_date),
        "entry": setup.entry_price,
        "hand_net": hand.net_pnl,
        "m4_net": m4_net,
        "bespoke_net": bespoke_net,
        "hand_exit": hand.exit_reason,
        "m4_match": m4_match,
        "bespoke_match": besp_match,
        "winner": winner,
        "net_diff_m4_hand": m4_net - hand.net_pnl,
    }
