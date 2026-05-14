"""Statistical methodology for strategy research (Phase 1 M7)."""

from quant_research.statistics.bootstrap import (
    BootstrapCIs,
    BootstrapConfig,
    bootstrap_trade_metrics,
)
from quant_research.statistics.deflated_sharpe import (
    DeflatedSharpeResult,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    sample_moments_from_returns,
)
from quant_research.statistics.is_oos import IsoSplitConfig, split_trade_log_is_oos
from quant_research.statistics.purged_cv import (
    PurgedKFoldConfig,
    embargo_split_indices,
    iter_purged_k_fold_splits,
)
from quant_research.statistics.spa_test import (
    RealityCheckResult,
    reality_check_from_config,
    whites_reality_check,
)
from quant_research.statistics.trade_report import (
    DeflatedSharpeRunParams,
    ResearchReport,
    research_report_to_dict,
    trade_log_research_report,
)
from quant_research.statistics.walk_forward import (
    WalkForwardConfig,
    WalkForwardMode,
    WalkForwardResult,
    WalkForwardWindow,
    iter_walk_forward_indices,
    run_walk_forward,
)

__all__ = [
    "BootstrapCIs",
    "BootstrapConfig",
    "DeflatedSharpeResult",
    "DeflatedSharpeRunParams",
    "IsoSplitConfig",
    "PurgedKFoldConfig",
    "RealityCheckResult",
    "ResearchReport",
    "WalkForwardConfig",
    "WalkForwardMode",
    "WalkForwardResult",
    "WalkForwardWindow",
    "bootstrap_trade_metrics",
    "deflated_sharpe_ratio",
    "embargo_split_indices",
    "expected_max_sharpe",
    "iter_purged_k_fold_splits",
    "iter_walk_forward_indices",
    "probabilistic_sharpe_ratio",
    "reality_check_from_config",
    "research_report_to_dict",
    "run_walk_forward",
    "sample_moments_from_returns",
    "split_trade_log_is_oos",
    "trade_log_research_report",
    "whites_reality_check",
]
