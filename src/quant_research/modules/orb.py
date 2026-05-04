"""Opening range breakout (ORB) strategy module — ported from NT8 ``ORBModule.cs``.

Opt3 (production) is **not** a separate module: it is the parameter set where
``latest_entry_hour_et == 11`` (and related ORB knobs from the funded CSV row).

**PYTHON_ASSUMPTIONS** vs NT8/C#:

- **Entry fill:** C# sizes stops/targets from signal-bar ``Close``; NT8 fills may
  differ. We adjust bracket levels from the **actual** ``avg_entry_price`` after
  the market entry fills, preserving C# stop **distance** and absolute target
  price derived from the opening range.
- **Bracket latency:** Exit orders arm on the first bar **after** the entry fill;
  NT8 attaches protective orders immediately post-fill (may intrabar the entry
  bar).
- **Session clock:** Requires a ``cme_session_date`` column on the bars
  ``DataFrame`` (see :func:`quant_research.data.session.assign_cme_session_date`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from quant_research.backtest.types import (
    BarContext,
    OrderRequest,
    OrderSide,
    OrderType,
)

ORB_MODULE_ID = "orb"
_EASTERN = ZoneInfo("America/New_York")

# 9:30–9:45 ET formation window; 14:30 ET session end for new entries (C# ORBModule).
_ORB_RANGE_START_ET = time(9, 30)
_ORB_RANGE_END_ET = time(9, 45)
_ORB_SESSION_END_ET = time(14, 30)


class _OrbState(StrEnum):
    IDLE = "idle"
    FORMING_RANGE = "forming_range"
    WATCHING = "watching"
    TRIGGERED = "triggered"
    NO_TRIGGER = "no_trigger"


@dataclass(frozen=True, slots=True)
class OrbParams:
    """ORB parameters; defaults follow ``Config.cs`` SetDefaults + funded CSV §8.4."""

    quantity: int = 3
    min_range_points: float = 10.0
    max_range_points: float = 100.0
    max_stop_points: float = 80.0
    stop_buffer: float = 2.0
    target_multiplier: float = 0.8
    breakout_buffer: float = 0.0
    enable_vwap_filter: bool = True
    enable_break_even: bool = True
    be_trigger_r: float = 1.0
    earliest_entry_hour_et: int = 10
    #: Opt3 production: 11 (0 = disabled).
    latest_entry_hour_et: int = 11
    use_atr_range_filter: bool = False
    min_range_atr: float = 0.25
    max_range_atr: float = 2.5
    use_atr_stop: bool = False
    max_stop_atr: float = 1.5
    max_atr15m: float = 0.0
    max_hold_minutes: int = 0
    #: When ATR filters are off or series is cold, keep 0.0.
    atr15m_series: float = 0.0


def production_orb_opt3_funded_params() -> OrbParams:
    """Production ORB+Opt3 (funded row ``PAAPEX3027390000003``, §8.4)."""
    return OrbParams(
        quantity=3,
        latest_entry_hour_et=11,
        max_range_atr=2.5,
        max_stop_atr=1.5,
        max_stop_points=80.0,
        min_range_atr=0.25,
        target_multiplier=0.8,
        use_atr_range_filter=False,
        use_atr_stop=False,
        max_atr15m=0.0,
        max_hold_minutes=0,
    )


def _time_et(ts: Any) -> time:
    if not hasattr(ts, "astimezone"):
        msg = "Bar timestamp must be timezone-aware Datetime-like"
        raise TypeError(msg)
    return ts.astimezone(_EASTERN).time()


def _hour_et(ts: Any) -> int:
    return ts.astimezone(_EASTERN).hour


class OrbStrategy:
    """Single-day ORB state machine aligned with ``ORBModule.cs``."""

    def __init__(self, params: OrbParams | None = None) -> None:
        self.params = params if params is not None else production_orb_opt3_funded_params()
        self._state = _OrbState.IDLE
        self._range_high = -math.inf
        self._range_low = math.inf
        self._range_size = 0.0
        self._last_session_date: Any = None
        self._session_vwap_num = 0.0
        self._session_vwap_den = 0.0
        self._pending_market_side: str | None = None
        self._stop_distance = 0.0
        self._target_price_snap = 0.0
        self._initial_stop_price = 0.0
        self._break_even_done = False

    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        mid = ORB_MODULE_ID
        sess = ctx.session_date
        if sess is None:
            msg = "ORBStrategy requires BarContext.session_date (e.g. cme_session_date column)"
            raise ValueError(msg)

        self._check_session_reset(sess)
        if self.params.enable_vwap_filter:
            self._update_vwap(ctx)

        t_et = _time_et(ctx.timestamp)
        h_et = _hour_et(ctx.timestamp)

        if ctx.position_qty != 0 and self._state == _OrbState.TRIGGERED:
            return self._manage_open(ctx, mid)

        if self._state == _OrbState.TRIGGERED:
            return []
        if self._state == _OrbState.NO_TRIGGER:
            return []

        if self._state == _OrbState.IDLE:
            if _ORB_RANGE_START_ET <= t_et < _ORB_RANGE_END_ET:
                self._state = _OrbState.FORMING_RANGE
                self._range_high = ctx.high
                self._range_low = ctx.low
            elif t_et >= _ORB_RANGE_END_ET:
                self._state = _OrbState.NO_TRIGGER
            return []

        if self._state == _OrbState.FORMING_RANGE:
            if t_et < _ORB_RANGE_END_ET:
                self._range_high = max(self._range_high, ctx.high)
                self._range_low = min(self._range_low, ctx.low)
                return []

            self._range_high = max(self._range_high, ctx.high)
            self._range_low = min(self._range_low, ctx.low)
            self._range_size = self._range_high - self._range_low
            eff_min, eff_max = self._effective_range_bounds()

            if self._range_size < eff_min:
                self._state = _OrbState.NO_TRIGGER
                return []
            if self._range_size > eff_max:
                self._state = _OrbState.NO_TRIGGER
                return []

            self._state = _OrbState.WATCHING
            if (
                self.params.earliest_entry_hour_et > 0
                and h_et < self.params.earliest_entry_hour_et
            ):
                return []
            return self._evaluate_breakout(ctx, mid, t_et, h_et)

        if self._state == _OrbState.WATCHING:
            if t_et > _ORB_SESSION_END_ET:
                self._state = _OrbState.NO_TRIGGER
                return []
            if (
                self.params.latest_entry_hour_et > 0
                and h_et >= self.params.latest_entry_hour_et
            ):
                self._state = _OrbState.NO_TRIGGER
                return []
            if (
                self.params.earliest_entry_hour_et > 0
                and h_et < self.params.earliest_entry_hour_et
            ):
                return []
            if (
                self.params.max_atr15m > 0
                and self.params.atr15m_series > 0
                and self.params.atr15m_series > self.params.max_atr15m
            ):
                return []
            if ctx.position_qty != 0:
                return []
            return self._evaluate_breakout(ctx, mid, t_et, h_et)

        return []

    def _check_session_reset(self, session_date: Any) -> None:
        if session_date != self._last_session_date:
            self._last_session_date = session_date
            self._reset_session_state()

    def _reset_session_state(self) -> None:
        self._state = _OrbState.IDLE
        self._range_high = -math.inf
        self._range_low = math.inf
        self._range_size = 0.0
        self._session_vwap_num = 0.0
        self._session_vwap_den = 0.0
        self._pending_market_side = None
        self._break_even_done = False

    def _update_vwap(self, ctx: BarContext) -> None:
        px_vol = ctx.close * ctx.volume
        self._session_vwap_num += px_vol
        self._session_vwap_den += ctx.volume

    def _session_vwap(self) -> float:
        if self._session_vwap_den <= 0:
            return 0.0
        return self._session_vwap_num / self._session_vwap_den

    def _effective_range_bounds(self) -> tuple[float, float]:
        atr = self.params.atr15m_series
        if self.params.use_atr_range_filter and atr > 0:
            return (
                atr * self.params.min_range_atr,
                atr * self.params.max_range_atr,
            )
        return (self.params.min_range_points, self.params.max_range_points)

    def _resolve_max_stop_distance(self) -> float:
        if self.params.use_atr_stop and self.params.atr15m_series > 0:
            atr_cap = self.params.atr15m_series * self.params.max_stop_atr
            return min(self.params.max_stop_points, atr_cap)
        return self.params.max_stop_points

    def _evaluate_breakout(
        self,
        ctx: BarContext,
        mid: str,
        t_et: time,
        h_et: int,
    ) -> list[OrderRequest]:
        if (
            self.params.latest_entry_hour_et > 0
            and h_et >= self.params.latest_entry_hour_et
        ):
            self._state = _OrbState.NO_TRIGGER
            return []
        if (
            self.params.max_atr15m > 0
            and self.params.atr15m_series > 0
            and self.params.atr15m_series > self.params.max_atr15m
        ):
            return []

        close = ctx.close
        rh = self._range_high
        rl = self._range_low
        buf = self.params.breakout_buffer
        long_break = close > rh + buf
        short_break = close < rl - buf

        vwap_val = self._session_vwap() if self.params.enable_vwap_filter else 0.0
        vwap_long_ok = (not self.params.enable_vwap_filter) or (
            vwap_val > 0 and close > vwap_val
        )
        vwap_short_ok = (not self.params.enable_vwap_filter) or (
            vwap_val > 0 and close < vwap_val
        )

        long_sig = long_break and vwap_long_ok
        short_sig = short_break and vwap_short_ok

        if long_sig:
            return self._emit_long(ctx, mid, close)
        if short_sig:
            return self._emit_short(ctx, mid, close)
        return []

    def _emit_long(self, ctx: BarContext, mid: str, entry_close: float) -> list[OrderRequest]:
        rl = self._range_low
        raw_stop_dist = (entry_close - rl) + self.params.stop_buffer
        max_stop = self._resolve_max_stop_distance()
        stop_dist = min(raw_stop_dist, max_stop)
        target_px = self._range_high + self._range_size * self.params.target_multiplier
        self._pending_market_side = "long"
        self._stop_distance = stop_dist
        self._target_price_snap = target_px
        self._initial_stop_price = entry_close - stop_dist
        self._state = _OrbState.TRIGGERED
        return [
            OrderRequest(
                OrderSide.BUY,
                self.params.quantity,
                OrderType.MARKET,
                module_id=mid,
                tag="orb_entry",
            ),
        ]

    def _emit_short(self, ctx: BarContext, mid: str, entry_close: float) -> list[OrderRequest]:
        rh = self._range_high
        raw_stop_dist = (rh - entry_close) + self.params.stop_buffer
        max_stop = self._resolve_max_stop_distance()
        stop_dist = min(raw_stop_dist, max_stop)
        target_px = self._range_low - self._range_size * self.params.target_multiplier
        self._pending_market_side = "short"
        self._stop_distance = stop_dist
        self._target_price_snap = target_px
        self._initial_stop_price = entry_close + stop_dist
        self._state = _OrbState.TRIGGERED
        return [
            OrderRequest(
                OrderSide.SELL,
                self.params.quantity,
                OrderType.MARKET,
                module_id=mid,
                tag="orb_entry",
            ),
        ]

    def _manage_open(self, ctx: BarContext, mid: str) -> list[OrderRequest]:
        outs: list[OrderRequest] = []
        q = abs(ctx.position_qty)
        entry = ctx.avg_entry_price
        if entry is None:
            return outs

        if self._pending_market_side is not None:
            if ctx.position_qty != 0:
                side = self._pending_market_side
                self._pending_market_side = None
                if side == "long":
                    stop_px = entry - self._stop_distance
                    outs.append(
                        OrderRequest(
                            OrderSide.SELL,
                            q,
                            OrderType.STOP,
                            stop_price=stop_px,
                            module_id=mid,
                            tag="orb_exit_stop",
                            dedupe_tag="orb_exit_stop",
                        ),
                    )
                    outs.append(
                        OrderRequest(
                            OrderSide.SELL,
                            q,
                            OrderType.LIMIT,
                            limit_price=self._target_price_snap,
                            module_id=mid,
                            tag="orb_exit_target",
                            dedupe_tag="orb_exit_target",
                        ),
                    )
                else:
                    stop_px = entry + self._stop_distance
                    outs.append(
                        OrderRequest(
                            OrderSide.BUY,
                            q,
                            OrderType.STOP,
                            stop_price=stop_px,
                            module_id=mid,
                            tag="orb_exit_stop",
                            dedupe_tag="orb_exit_stop",
                        ),
                    )
                    outs.append(
                        OrderRequest(
                            OrderSide.BUY,
                            q,
                            OrderType.LIMIT,
                            limit_price=self._target_price_snap,
                            module_id=mid,
                            tag="orb_exit_target",
                            dedupe_tag="orb_exit_target",
                        ),
                    )
            return outs

        if not self.params.enable_break_even or self._break_even_done:
            return outs

        init_risk = abs(entry - self._initial_stop_price)
        if init_risk <= 0:
            return outs
        trigger = init_risk * self.params.be_trigger_r
        if ctx.position_qty > 0:
            profit = ctx.close - entry
            old_stop = entry - self._stop_distance
            would_tighten = entry > old_stop
            if profit >= trigger and would_tighten:
                self._break_even_done = True
                outs.append(
                    OrderRequest(
                        OrderSide.SELL,
                        q,
                        OrderType.STOP,
                        stop_price=entry,
                        module_id=mid,
                        tag="orb_break_even",
                        dedupe_tag="orb_exit_stop",
                    ),
                )
        elif ctx.position_qty < 0:
            profit = entry - ctx.close
            old_stop = entry + self._stop_distance
            would_tighten = entry < old_stop
            if profit >= trigger and would_tighten:
                self._break_even_done = True
                outs.append(
                    OrderRequest(
                        OrderSide.BUY,
                        q,
                        OrderType.STOP,
                        stop_price=entry,
                        module_id=mid,
                        tag="orb_break_even",
                        dedupe_tag="orb_exit_stop",
                    ),
                )

        return outs
