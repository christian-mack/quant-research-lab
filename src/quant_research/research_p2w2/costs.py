"""P2-W2 cost model and bar-level trade execution with M4-equivalent fills."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import polars as pl

from quant_research.backtest.fill_resolution import slippage_for_tag
from quant_research.backtest.geometry import check_trade_geometry
from quant_research.backtest.specs import (
    BacktestConfig,
    CommissionSpec,
    FillModelSpec,
    IntradaySessionHygieneSpec,
    LimitFillMode,
    SessionSpec,
    SlippageMode,
    SlippageSpec,
    StopLimitIntrabarPolicy,
    TagSlippageOverride,
)
from quant_research.backtest.tick import apply_slippage
from quant_research.backtest.types import OrderSide

MNQ_POINT_VALUE = 2.0
MNQ_TICK = 0.25

COMMISSION_PER_FILL = 0.99
COMMISSION_RT = 1.98
SLIP_STOP_TICKS = 1.0
SLIP_TARGET_TICKS = 0.5

P2_ENTRY_TAG = "p2_entry"
P2_STOP_TAG = "p2_stop"
P2_TARGET_TAG = "p2_target"
P2_TIME_TAG = "p2_time"


def p2_w2_backtest_config() -> BacktestConfig:
    """$1.98 RT commission; 1 tick slip on stop/time, 0.5 tick on target."""
    return BacktestConfig(
        commission=CommissionSpec(per_contract_per_fill=COMMISSION_PER_FILL),
        slippage=SlippageSpec(
            mode=SlippageMode.FIXED_TICKS,
            ticks=SLIP_STOP_TICKS,
            tag_overrides=(
                TagSlippageOverride(P2_ENTRY_TAG, SlippageMode.NONE, ticks=0.0),
                TagSlippageOverride(P2_TARGET_TAG, SlippageMode.FIXED_TICKS, ticks=SLIP_TARGET_TICKS),
            ),
        ),
        fill_model=FillModelSpec(
            stop_limit_intrabar=StopLimitIntrabarPolicy.STOP_BEFORE_TARGET,
            limit_fill_mode=LimitFillMode.TOUCH,
            same_bar_exit_after_entry=True,
        ),
        session=SessionSpec(intraday_hygiene=IntradaySessionHygieneSpec(enabled=False)),
        enforce_trade_geometry=True,
    )


P2_W2_BACKTEST_CONFIG = p2_w2_backtest_config()


@dataclass(frozen=True, slots=True)
class P2Trade:
    """One closed MNQ round-trip at qty=1 with costs applied."""

    entry_time: dt.datetime
    exit_time: dt.datetime
    cme_session_date: dt.date
    direction: int
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    exit_reason: str
    gross_pnl: float
    commission: float
    net_pnl: float
    bars_held: int
    hypothesis_id: str = ""


def _slip_px(base: float, side: str, tag: str, config: BacktestConfig) -> float:
    slip_spec = slippage_for_tag(tag, config.slippage)
    os_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
    return apply_slippage(base, os_side, slip_spec, config.instrument)


def _exit_slip_tag(exit_reason: str) -> str:
    if exit_reason == "target":
        return P2_TARGET_TAG
    return P2_STOP_TAG


def simulate_p2_trade(
    bars: pl.DataFrame,
    *,
    entry_idx: int,
    direction: int,
    entry_price: float,
    stop_px: float,
    target_px: float,
    cme_session_date: dt.date,
    max_et_time_exit: dt.time | None = None,
    exit_tag_time: str = "time",
    hypothesis_id: str = "",
    config: BacktestConfig | None = None,
) -> P2Trade | None:
    """Walk minute bars with stop-before-target conflict rule and P2-W2 costs."""
    cfg = config or P2_W2_BACKTEST_CONFIG
    dir_str = "long" if direction == 1 else "short"
    geom_reject = check_trade_geometry(dir_str, entry_price, stop_px, target_px)
    if geom_reject is not None:
        return None

    n = bars.height
    if entry_idx >= n:
        return None

    entry_ts = bars["timestamp"][entry_idx]
    entry_side = "buy" if direction == 1 else "sell"
    entry_fill = _slip_px(float(entry_price), entry_side, P2_ENTRY_TAG, cfg)
    comm_entry = COMMISSION_PER_FILL

    exit_reason = "session_end"
    exit_base = float(bars["close"][n - 1])
    exit_bar = n - 1
    exit_ts = bars["timestamp"][n - 1]

    for i in range(entry_idx, n):
        o = float(bars["open"][i])
        hhi = float(bars["high"][i])
        lw = float(bars["low"][i])
        clo = float(bars["close"][i])
        ts = bars["timestamp"][i]
        ts_et = bars["ts_et"][i]

        if direction == 1:
            hit_stop = lw <= stop_px
            hit_t = hhi >= target_px
            if hit_stop and hit_t:
                exit_reason, exit_base, exit_bar, exit_ts = "stop", stop_px, i, ts
                break
            if hit_stop:
                exit_reason, exit_base, exit_bar, exit_ts = "stop", stop_px, i, ts
                break
            if hit_t:
                exit_reason, exit_base, exit_bar, exit_ts = "target", target_px, i, ts
                break
        else:
            hit_stop = hhi >= stop_px
            hit_t = lw <= target_px
            if hit_stop and hit_t:
                exit_reason, exit_base, exit_bar, exit_ts = "stop", stop_px, i, ts
                break
            if hit_stop:
                exit_reason, exit_base, exit_bar, exit_ts = "stop", stop_px, i, ts
                break
            if hit_t:
                exit_reason, exit_base, exit_bar, exit_ts = "target", target_px, i, ts
                break

        if max_et_time_exit is not None and ts_et.time() >= max_et_time_exit:
            exit_reason, exit_base, exit_bar, exit_ts = exit_tag_time, clo, i, ts
            break

    exit_side = "sell" if direction == 1 else "buy"
    slip_tag = _exit_slip_tag(exit_reason if exit_reason in ("stop", "target") else "time")
    exit_fill = _slip_px(exit_base, exit_side, slip_tag, cfg)
    comm_exit = COMMISSION_PER_FILL

    pts = (exit_fill - entry_fill) if direction == 1 else (entry_fill - exit_fill)
    gross = pts * MNQ_POINT_VALUE
    commission = comm_entry + comm_exit
    net = gross - commission

    return P2Trade(
        entry_time=entry_ts,
        exit_time=exit_ts,
        cme_session_date=cme_session_date,
        direction=direction,
        entry_price=entry_fill,
        exit_price=exit_fill,
        stop_price=float(stop_px),
        target_price=float(target_px),
        exit_reason=exit_reason,
        gross_pnl=float(gross),
        commission=float(commission),
        net_pnl=float(net),
        bars_held=max(0, exit_bar - entry_idx),
        hypothesis_id=hypothesis_id,
    )
