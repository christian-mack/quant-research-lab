"""P2-W2 tight-loss-tail / arbitrage-resistant hypothesis research."""

from quant_research.research_p2w2.costs import P2_W2_BACKTEST_CONFIG, P2Trade
from quant_research.research_p2w2.data_verify import MnqDatasetReport, verify_mnq_dataset
from quant_research.research_p2w2.hypothesis_sims import (
    simulate_h1,
    simulate_h2,
    simulate_h3,
    simulate_h4,
    simulate_h6,
)
from quant_research.research_p2w2.metrics import gate1_is_screen, split_is_oos, trades_to_harness_log

__all__ = [
    "P2Trade",
    "P2_W2_BACKTEST_CONFIG",
    "MnqDatasetReport",
    "gate1_is_screen",
    "simulate_h1",
    "simulate_h2",
    "simulate_h3",
    "simulate_h4",
    "simulate_h6",
    "split_is_oos",
    "trades_to_harness_log",
    "verify_mnq_dataset",
]
