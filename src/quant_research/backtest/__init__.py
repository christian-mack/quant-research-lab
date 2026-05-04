"""Research backtest engine (M4). See ``docs/m4-backtest-engine-design.md``."""

from quant_research.backtest.engine import BacktestEngine
from quant_research.backtest.schema import empty_trade_log, trade_log_schema
from quant_research.backtest.specs import BacktestConfig, BacktestRunSpec, InstrumentSpec
from quant_research.backtest.types import BarContext, OrderRequest, OrderSide, OrderType, Strategy

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestRunSpec",
    "BarContext",
    "InstrumentSpec",
    "OrderRequest",
    "OrderSide",
    "OrderType",
    "Strategy",
    "empty_trade_log",
    "trade_log_schema",
]
