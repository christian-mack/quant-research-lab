"""OTE setup execution via the M4 :class:`~quant_research.backtest.engine.BacktestEngine`."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from quant_research.backtest.schema import empty_trade_log
from quant_research.backtest.validation import ValidationReport, validate_backtest_result
from quant_research.backtest.engine import BacktestEngine, BacktestResult, as_module
from quant_research.backtest.fill_resolution import (
    validate_bracket_geometry_in_orders,
    validate_order_request,
)
from quant_research.backtest.geometry import GeometryError, GeometryReject, check_trade_geometry
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
from quant_research.backtest.types import BarContext, OrderRequest, OrderSide, OrderType, QueuedOrder, SimulatedFill
from quant_research.ict.ote_strategy import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    OteSetup,
    OteStrategyConfig,
    scan_setups_with_stats,
)

OTE_MODULE_ID = "ote"
OTE_ENTRY_TAG = "ote_entry"
OTE_STOP_TAG = "ote_stop"
OTE_TARGET_TAG = "ote_target"

COMMISSION_PER_FILL = 0.99
COMMISSION_RT = 1.98
SLIP_STOP_TICKS = 1.0
SLIP_TARGET_TICKS = 0.5


def ote_research_backtest_config() -> BacktestConfig:
    """Single cost model for OTE research: $1.98 RT, tag-based slippage."""
    return BacktestConfig(
        commission=CommissionSpec(per_contract_per_fill=COMMISSION_PER_FILL),
        slippage=SlippageSpec(
            mode=SlippageMode.FIXED_TICKS,
            ticks=SLIP_STOP_TICKS,
            tag_overrides=(
                TagSlippageOverride(OTE_ENTRY_TAG, SlippageMode.NONE, ticks=0.0),
                TagSlippageOverride(OTE_TARGET_TAG, SlippageMode.FIXED_TICKS, ticks=SLIP_TARGET_TICKS),
            ),
        ),
        fill_model=FillModelSpec(
            stop_limit_intrabar=StopLimitIntrabarPolicy.STOP_BEFORE_TARGET,
            limit_fill_mode=LimitFillMode.TOUCH,
            same_bar_exit_after_entry=True,
        ),
        session=SessionSpec(
            intraday_hygiene=IntradaySessionHygieneSpec(enabled=False),
        ),
        enforce_trade_geometry=True,
    )


@dataclass(frozen=True)
class OteExecutedTrade:
    """One OTE round-trip from the M4 engine trade log."""

    session_date: str | None
    direction: str
    entry_price: float
    exit_price: float
    exit_reason: str
    net_pnl: float
    gross_pnl: float
    commission: float
    quantity: int


@dataclass
class OteExecutionBatch:
    """Batch execution summary for a scan + sim pass."""

    setups_detected: int
    geometry_rejects: dict[str, int]
    setups_filled: int
    trades: list[OteExecutedTrade] = field(default_factory=list)
    setups_passed_scan: int = 0
    trade_log: pl.DataFrame = field(default_factory=empty_trade_log)
    validation_report: ValidationReport | None = None
    ledger_geometry_rejects: dict[str, int] = field(default_factory=dict)

    @property
    def geometry_reject_total(self) -> int:
        return sum(self.geometry_rejects.values())

    @property
    def geometry_reject_rate(self) -> float:
        if self.setups_detected == 0:
            return 0.0
        return self.geometry_reject_total / self.setups_detected


class OteSetupRunner:
    """Replay one pre-detected OTE setup on a session bar slice."""

    def __init__(self, setup: OteSetup) -> None:
        self._setup = setup
        self._entry_submitted = False
        self._was_open = False
        self._done = False

    def mark_entry_submitted(self) -> None:
        self._entry_submitted = True

    def entry_order_request(self) -> OrderRequest:
        return self._entry_order()

    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        if self._done or self._setup.entry_fill_index is None:
            return []
        if ctx.position_qty != 0:
            self._was_open = True
            return self._bracket_orders()
        if self._was_open:
            self._done = True
            return []
        fill_idx = self._setup.entry_fill_index
        if ctx.bar_index == fill_idx - 1 and not self._entry_submitted:
            self._entry_submitted = True
            return [self._entry_order()]
        return []

    def on_entry_fill(self, fill: SimulatedFill, ctx: BarContext) -> list[OrderRequest]:
        if fill.tag != OTE_ENTRY_TAG:
            return []
        return self._bracket_orders()

    def _entry_order(self) -> OrderRequest:
        s = self._setup
        side = OrderSide.BUY if s.direction == DIRECTION_LONG else OrderSide.SELL
        return OrderRequest(
            side=side,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=s.entry_price,
            module_id=OTE_MODULE_ID,
            tag=OTE_ENTRY_TAG,
            bracket_entry=s.entry_price,
            bracket_stop=s.stop_price,
            bracket_target=s.target_price,
            bracket_direction=s.direction,
        )

    def _bracket_orders(self) -> list[OrderRequest]:
        s = self._setup
        if s.direction == DIRECTION_LONG:
            exit_side = OrderSide.SELL
        else:
            exit_side = OrderSide.BUY
        common = {
            "quantity": 1,
            "module_id": OTE_MODULE_ID,
            "bracket_entry": s.entry_price,
            "bracket_stop": s.stop_price,
            "bracket_target": s.target_price,
            "bracket_direction": s.direction,
        }
        return [
            OrderRequest(
                exit_side,
                order_type=OrderType.STOP,
                stop_price=s.stop_price,
                tag=OTE_STOP_TAG,
                dedupe_tag="ote_stop",
                **common,
            ),
            OrderRequest(
                exit_side,
                order_type=OrderType.LIMIT,
                limit_price=s.target_price,
                tag=OTE_TARGET_TAG,
                dedupe_tag="ote_target",
                **common,
            ),
        ]


def execute_setup(
    setup: OteSetup,
    session_bars: pl.DataFrame,
    *,
    config: BacktestConfig | None = None,
) -> OteExecutedTrade | GeometryReject | None:
    """Run one setup through M4; return trade, geometry reject, or None if no fill."""
    reject = check_trade_geometry(
        setup.direction, setup.entry_price, setup.stop_price, setup.target_price
    )
    if reject is not None:
        return reject
    if setup.entry_fill_index is None:
        return None

    cfg = config or ote_research_backtest_config()
    runner = OteSetupRunner(setup)
    engine = BacktestEngine(cfg)
    initial_working: list[QueuedOrder] = []
    if setup.entry_fill_index == 0:
        runner.mark_entry_submitted()
        oid = 1
        req = runner.entry_order_request()
        validate_order_request(req)
        validate_bracket_geometry_in_orders([req], config=cfg)
        initial_working.append(QueuedOrder(oid, req))
    result = engine.run(
        session_bars.sort("timestamp"),
        [as_module(OTE_MODULE_ID, runner)],
        initial_working=initial_working,
    )
    return _trade_from_result(result, setup)


def execute_setups_on_sessions(
    setups: list[OteSetup],
    sessions: dict[Any, pl.DataFrame],
    *,
    config: BacktestConfig | None = None,
    geometry_rejects: dict[str, int] | None = None,
) -> OteExecutionBatch:
    """Execute many setups; count geometry rejects from scan plus runtime guard."""
    cfg = config or ote_research_backtest_config()
    rejects: Counter[str] = Counter(geometry_rejects or {})
    trades, combined_log, ledger_rejects = _execute_and_collect(setups, sessions, cfg, rejects)
    total_attempts = len(setups) + sum(rejects.values()) - sum(ledger_rejects.values())
    validation = validate_backtest_result(
        combined_log,
        config=cfg,
        geometry_reject_rate=sum(rejects.values()) / max(total_attempts, 1),
    )
    return OteExecutionBatch(
        setups_detected=total_attempts,
        geometry_rejects=dict(rejects),
        setups_filled=len(trades),
        trades=trades,
        trade_log=combined_log,
        validation_report=validation,
        ledger_geometry_rejects=dict(ledger_rejects),
    )


def _execute_and_collect(
    setups: list[OteSetup],
    sessions: dict[Any, pl.DataFrame],
    cfg: BacktestConfig,
    rejects: Counter[str],
) -> tuple[list[OteExecutedTrade], pl.DataFrame, Counter[str]]:
    trades: list[OteExecutedTrade] = []
    frames: list[pl.DataFrame] = []
    ledger_rejects: Counter[str] = Counter()
    for setup in setups:
        if setup.session_date is None:
            continue
        sess = sessions.get(setup.session_date)
        if sess is None:
            continue
        if setup.entry_fill_index is None:
            continue
        runner = OteSetupRunner(setup)
        engine = BacktestEngine(cfg)
        initial_working: list[QueuedOrder] = []
        if setup.entry_fill_index == 0:
            runner.mark_entry_submitted()
            req = runner.entry_order_request()
            validate_order_request(req)
            validate_bracket_geometry_in_orders([req], config=cfg)
            initial_working.append(QueuedOrder(1, req))
        result = engine.run(
            sess.sort("timestamp"),
            [as_module(OTE_MODULE_ID, runner)],
            initial_working=initial_working,
        )
        for reason, count in result.geometry_rejects.items():
            ledger_rejects[reason] += count
        if not result.trade_log.is_empty():
            frames.append(result.trade_log)
            trade = _trade_from_result(result, setup)
            if trade is not None:
                trades.append(trade)
    if not frames:
        return trades, empty_trade_log(), ledger_rejects
    combined = pl.concat(frames).sort("entry_time")
    return trades, combined, ledger_rejects


def run_config_backtest(
    mnq: pl.DataFrame,
    *,
    config: OteStrategyConfig,
    backtest_config: BacktestConfig | None = None,
) -> OteExecutionBatch:
    """Scan + execute one OTE config on a full MNQ frame."""
    scan = scan_setups_with_stats(mnq, config=config)
    sessions = _session_frames(mnq)
    batch = execute_setups_on_sessions(
        scan.setups,
        sessions,
        config=backtest_config,
        geometry_rejects=scan.geometry_rejects,
    )
    batch.setups_detected = scan.setups_detected
    batch.setups_passed_scan = len(scan.setups)
    return batch


def _session_frames(mnq: pl.DataFrame) -> dict[Any, pl.DataFrame]:
    out: dict[Any, pl.DataFrame] = {}
    for sd in mnq["cme_session_date"].unique().sort().to_list():
        if sd is None:
            continue
        out[sd] = mnq.filter(pl.col("cme_session_date") == sd).sort("timestamp")
    return out


def _trade_from_result(result: BacktestResult, setup: OteSetup) -> OteExecutedTrade | None:
    log = result.trade_log
    if log.is_empty():
        return None
    row = log.row(0, named=True)
    sess = setup.session_date.isoformat() if setup.session_date else None
    return OteExecutedTrade(
        session_date=sess,
        direction=str(row["direction"]),
        entry_price=float(row["entry_price"]),
        exit_price=float(row["exit_price"]),
        exit_reason=str(row["exit_reason"]),
        net_pnl=float(row["net_pnl"]),
        gross_pnl=float(row["gross_pnl"]),
        commission=float(row["commission"]),
        quantity=int(row["quantity"]),
    )


def economics_summary(trades: list[OteExecutedTrade], *, eval_years: tuple[int, ...] | None = None) -> dict[str, Any]:
    """Net economics from executed trades (already includes comm+slip from engine)."""
    if not trades:
        return {"n_trades": 0}
    nets = [t.net_pnl for t in trades]
    wins = [p for p in nets if p > 0]
    losses = [p for p in nets if p <= 0]
    by_year: dict[str, float] = {}
    for t, n in zip(trades, nets):
        if t.session_date is None:
            continue
        yr = t.session_date[:4]
        if eval_years is not None and int(yr) not in eval_years:
            continue
        by_year[yr] = by_year.get(yr, 0.0) + n
    n_years = max(len(by_year), 1)
    tick_val = 0.25 * 2.0
    return {
        "n_trades": len(trades),
        "trades_per_year": len(trades) / n_years if eval_years else len(trades) / n_years,
        "total_net_usd": sum(nets),
        "annual_net_usd": sum(by_year.values()) / n_years if by_year else sum(nets) / n_years,
        "avg_net_per_trade_usd": sum(nets) / len(trades),
        "avg_net_ticks": sum(nets) / len(trades) / tick_val,
        "win_rate": len(wins) / len(trades),
        "avg_win_usd": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss_usd": sum(losses) / len(losses) if losses else 0.0,
        "reward_risk_ratio": abs(sum(wins) / len(wins) / (sum(losses) / len(losses))) if wins and losses else None,
        "year_net_usd": dict(sorted(by_year.items())),
    }
