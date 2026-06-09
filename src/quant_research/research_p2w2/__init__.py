"""P2-W2 tight-loss-tail / arbitrage-resistant hypothesis research."""

from quant_research.research_p2w2.costs import P2_W2_BACKTEST_CONFIG
from quant_research.research_p2w2.data_verify import MnqDatasetReport, verify_mnq_dataset
from quant_research.research_p2w2.hypothesis_sims import (
    run_hypothesis_m4,
    scan_h1,
    scan_h2,
    scan_h3,
    scan_h4,
    scan_h6,
    scan_h7,
)
from quant_research.research_p2w2.metrics import gate1_is_screen_log, split_is_oos_log
from quant_research.research_p2w2.p2_execution import P2ExecutionBatch

__all__ = [
    "P2ExecutionBatch",
    "P2_W2_BACKTEST_CONFIG",
    "MnqDatasetReport",
    "gate1_is_screen_log",
    "run_hypothesis_m4",
    "scan_h1",
    "scan_h2",
    "scan_h3",
    "scan_h4",
    "scan_h6",
    "scan_h7",
    "split_is_oos_log",
    "verify_mnq_dataset",
]
