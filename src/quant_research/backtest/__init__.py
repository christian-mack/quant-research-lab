"""Research backtest engine (M4). See ``docs/m4-backtest-engine-design.md``."""

from quant_research.backtest.account import Account
from quant_research.backtest.engine import BacktestEngine, BacktestResult, as_module
from quant_research.backtest.omat import StrategyModule, collect_orders_for_bar
from quant_research.backtest.schema import empty_trade_log, trade_log_schema
from quant_research.backtest.specs import (
    BacktestConfig,
    BacktestRunSpec,
    InstrumentSpec,
    OrchestrationSpec,
)
from quant_research.backtest.trade_ledger import TradeLedger
from quant_research.backtest.types import BarContext, OrderRequest, OrderSide, OrderType, Strategy

__all__ = [
    "Account",
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "BacktestRunSpec",
    "BarContext",
    "InstrumentSpec",
    "OrderRequest",
    "OrderSide",
    "OrderType",
    "OrchestrationSpec",
    "Strategy",
    "StrategyModule",
    "TradeLedger",
    "as_module",
    "collect_orders_for_bar",
    "empty_trade_log",
    "trade_log_schema",
]
