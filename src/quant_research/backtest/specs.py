"""Configuration types for the research backtest engine.

Contract is ``docs/m4-backtest-engine-design.md`` §2 and **§8 adopted defaults**
(2026-04-28). Values align with PT3 where helpful; anything that is a deliberate
simplification is labeled in type docstrings as a ``PYTHON_ASSUMPTION``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from enum import StrEnum


class MarketFillTiming(StrEnum):
    OPEN_OF_NEXT_BAR = "open_of_next_bar"
    CLOSE_OF_SIGNAL_BAR = "close_of_signal_bar"


class StopLimitIntrabarPolicy(StrEnum):
    FIRST_TOUCH_OHLC_ORDER = "first_touch_ohlc_order"
    PESSIMISTIC = "pessimistic"
    OPTIMISTIC = "optimistic"


class GapPolicy(StrEnum):
    """When the bar open gaps through a stop/limit level."""

    FILL_AT_OPEN = "fill_at_open"
    NO_FILL_ON_GAP = "no_fill_on_gap"


class IntrabarPricePath(StrEnum):
    """Corner visit order after the open (see fill_model.intrabar_pivots)."""

    OPEN_HIGH_LOW_CLOSE = "open_high_low_close"
    OPEN_LOW_HIGH_CLOSE = "open_low_high_close"


class SlippageMode(StrEnum):
    NONE = "none"
    FIXED_TICKS = "fixed_ticks"
    FIXED_POINTS = "fixed_points"


class SlippageSide(StrEnum):
    SYMMETRIC = "symmetric"
    ADVERSE_ONLY = "adverse_only"


class RoundTurnMode(StrEnum):
    ONE_WAY_CREDITS_BOTH_LEGS = "one_way_credits_both_legs"
    EXPLICIT_ENTRY_EXIT = "explicit_entry_exit"


class TimeInForce(StrEnum):
    """DAY = backtest-window validity (PYTHON_ASSUMPTION stand-in for NT8 GTC in v1)."""

    DAY = "day"
    GTC = "gtc"


@dataclass(frozen=True, slots=True)
class BacktestRunSpec:
    start: date | None = None
    end: date | None = None
    initial_cash: float = 50_000.0


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    symbol: str = "MNQ"
    tick_size: float = 0.25
    #: USD per **one full price index point** per contract (MNQ ≈ $2).
    tick_value: float = 2.0
    currency: str = "USD"
    min_lot: int = 1
    strict_tick_grid: bool = True


@dataclass(frozen=True, slots=True)
class IntradaySessionHygieneSpec:
    """NT8 **break-at-end-of-session** analogue: flat into maintenance; entry deadzone.

    Wall-clock **America/New_York** (handles DST via tz-aware bar timestamps).

    - **Flatten time:** Any open position is closed with a market fill at this bar's
      **close** (after normal fills and strategy ``on_bar`` for that bar).
    - **Deadzone:** While flat, the engine drops **all** strategy orders so modules
      cannot open new risk; if still open (missing 16:59 bar, etc.), also flattened
      at **close** for every bar in the deadzone.

    Disable with ``enabled=False`` for unit tests that intentionally span maintenance.
    """

    enabled: bool = True
    flatten_time_et: time = time(16, 59)
    entry_deadzone_start_et: time = time(17, 0)
    entry_deadzone_end_et: time = time(18, 0)


@dataclass(frozen=True, slots=True)
class SessionSpec:
    calendar_name: str = "CME_Equity"
    classify_sessions: bool = True
    trade_rth_only: bool = False
    intraday_hygiene: IntradaySessionHygieneSpec = field(
        default_factory=IntradaySessionHygieneSpec,
    )


@dataclass(frozen=True, slots=True)
class CommissionSpec:
    per_contract_per_fill: float = 0.0
    currency: str = "USD"
    round_turn_mode: RoundTurnMode = RoundTurnMode.ONE_WAY_CREDITS_BOTH_LEGS


@dataclass(frozen=True, slots=True)
class SlippageSpec:
    mode: SlippageMode = SlippageMode.NONE
    ticks: float = 0.0
    points: float = 0.0
    side: SlippageSide = SlippageSide.ADVERSE_ONLY


@dataclass(frozen=True, slots=True)
class FillModelSpec:
    market_fill_timing: MarketFillTiming = MarketFillTiming.OPEN_OF_NEXT_BAR
    stop_limit_intrabar: StopLimitIntrabarPolicy = (
        StopLimitIntrabarPolicy.FIRST_TOUCH_OHLC_ORDER
    )
    gap_policy: GapPolicy = GapPolicy.FILL_AT_OPEN
    intrabar_path: IntrabarPricePath = IntrabarPricePath.OPEN_HIGH_LOW_CLOSE


@dataclass(frozen=True, slots=True)
class PartialFillSpec:
    enabled: bool = False
    min_fill_fraction: float = 1.0


@dataclass(frozen=True, slots=True)
class TimeInForceSpec:
    market: TimeInForce = TimeInForce.DAY
    limit: TimeInForce = TimeInForce.DAY
    stop: TimeInForce = TimeInForce.DAY


@dataclass(frozen=True, slots=True)
class OrchestrationSpec:
    module_ids: tuple[str, ...] = ()
    one_position_at_a_time: bool = True


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    run: BacktestRunSpec = field(default_factory=BacktestRunSpec)
    instrument: InstrumentSpec = field(default_factory=InstrumentSpec)
    session: SessionSpec = field(default_factory=SessionSpec)
    commission: CommissionSpec = field(default_factory=CommissionSpec)
    slippage: SlippageSpec = field(default_factory=SlippageSpec)
    fill_model: FillModelSpec = field(default_factory=FillModelSpec)
    partial_fills: PartialFillSpec = field(default_factory=PartialFillSpec)
    time_in_force: TimeInForceSpec = field(default_factory=TimeInForceSpec)
    orchestration: OrchestrationSpec = field(default_factory=OrchestrationSpec)
