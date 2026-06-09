"""P2-W2 cost model — single BacktestConfig for M4 engine execution."""

from __future__ import annotations

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
                TagSlippageOverride(
                    P2_TARGET_TAG, SlippageMode.FIXED_TICKS, ticks=SLIP_TARGET_TICKS
                ),
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
