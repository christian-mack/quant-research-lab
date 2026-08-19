"""Execute P2 setups through the M4 BacktestEngine (single fill path)."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

import polars as pl

from quant_research.backtest.engine import BacktestEngine, BacktestResult, as_module
from quant_research.backtest.fill_resolution import (
    validate_bracket_geometry_in_orders,
    validate_order_request,
)
from quant_research.backtest.geometry import GeometryReject, check_trade_geometry
from quant_research.backtest.schema import empty_trade_log
from quant_research.backtest.specs import BacktestConfig
from quant_research.backtest.types import (
    BarContext,
    OrderRequest,
    OrderSide,
    OrderType,
    QueuedOrder,
    SimulatedFill,
)
from quant_research.backtest.validation import (
    ValidationReport,
    ValidationThresholds,
    validate_backtest_result,
)
from quant_research.research_p2w2.costs import (
    P2_ENTRY_TAG,
    P2_STOP_TAG,
    P2_TARGET_TAG,
    P2_TIME_TAG,
    P2_W2_BACKTEST_CONFIG,
)
from quant_research.research_p2w2.metrics import P2_W2_V4_TICK_THRESHOLD
from quant_research.research_p2w2.p2_setup import P2Setup

_EASTERN = ZoneInfo("America/New_York")


def _module_id(hypothesis_id: str) -> str:
    return hypothesis_id.lower().replace("-", "")


def _attach_ts_et(bars: pl.DataFrame) -> pl.DataFrame:
    if "ts_et" in bars.columns:
        return bars.sort("timestamp")
    return bars.sort("timestamp").with_columns(
        pl.col("timestamp").dt.convert_time_zone(_EASTERN).alias("ts_et")
    )


def _et_time(ts: object) -> dt.time:
    return ts.astimezone(_EASTERN).time()  # type: ignore[union-attr]


class P2SetupRunner:
    """Replay one pre-detected P2 setup on a session bar slice."""

    def __init__(self, setup: P2Setup) -> None:
        self._setup = setup
        self._entry_submitted = False
        self._was_open = False
        self._done = False
        self._time_stop = setup.time_stop_et

    def mark_entry_submitted(self) -> None:
        self._entry_submitted = True

    def entry_order_request(self) -> OrderRequest:
        return self._entry_order()

    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        if self._done:
            return []
        if ctx.position_qty != 0:
            self._was_open = True
            if self._time_stop is not None and _et_time(ctx.timestamp) >= self._time_stop:
                return [self._flatten_order(ctx.position_qty)]
            return []
        if self._was_open:
            self._done = True
            return []
        if ctx.bar_index == self._setup.entry_fill_index and not self._entry_submitted:
            self._entry_submitted = True
            return [self._entry_order()]
        return []

    def on_entry_fill(self, fill: SimulatedFill, ctx: BarContext) -> list[OrderRequest]:
        del ctx
        if fill.tag != P2_ENTRY_TAG:
            return []
        return self._bracket_orders()

    def _entry_order(self) -> OrderRequest:
        s = self._setup
        side = OrderSide.BUY if s.direction == "long" else OrderSide.SELL
        return OrderRequest(
            side=side,
            quantity=1,
            order_type=OrderType.MARKET,
            module_id=_module_id(s.hypothesis_id),
            tag=P2_ENTRY_TAG,
            bracket_entry=s.entry_price,
            bracket_stop=s.stop_price,
            bracket_target=s.target_price,
            bracket_direction=s.direction,
        )

    def _bracket_orders(self) -> list[OrderRequest]:
        s = self._setup
        exit_side = OrderSide.SELL if s.direction == "long" else OrderSide.BUY
        common = {
            "quantity": 1,
            "module_id": _module_id(s.hypothesis_id),
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
                tag=P2_STOP_TAG,
                dedupe_tag="p2_stop",
                **common,
            ),
            OrderRequest(
                exit_side,
                order_type=OrderType.LIMIT,
                limit_price=s.target_price,
                tag=P2_TARGET_TAG,
                dedupe_tag="p2_target",
                **common,
            ),
        ]

    def _flatten_order(self, position_qty: int) -> OrderRequest:
        s = self._setup
        if position_qty > 0:
            side = OrderSide.SELL
        else:
            side = OrderSide.BUY
        return OrderRequest(
            side=side,
            quantity=abs(position_qty),
            order_type=OrderType.MARKET,
            module_id=_module_id(s.hypothesis_id),
            tag=P2_TIME_TAG,
            bracket_entry=s.entry_price,
            bracket_stop=s.stop_price,
            bracket_target=s.target_price,
            bracket_direction=s.direction,
        )


@dataclass
class P2ExecutionBatch:
    """Batch M4 execution for one hypothesis."""

    hypothesis_id: str
    setups_scanned: int
    setups_filled: int
    geometry_rejects: dict[str, int] = field(default_factory=dict)
    trade_log: pl.DataFrame = field(default_factory=empty_trade_log)
    validation_report: ValidationReport | None = None
    ledger_geometry_rejects: dict[str, int] = field(default_factory=dict)


def execute_setup(
    setup: P2Setup,
    session_bars: pl.DataFrame,
    *,
    config: BacktestConfig | None = None,
) -> BacktestResult | GeometryReject | None:
    """Run one setup through M4; return result, geometry reject, or None."""
    reject = check_trade_geometry(
        setup.direction, setup.entry_price, setup.stop_price, setup.target_price
    )
    if reject is not None:
        return reject
    if setup.entry_fill_index < 0 or setup.entry_fill_index >= session_bars.height:
        return None

    cfg = config or P2_W2_BACKTEST_CONFIG
    bars = _attach_ts_et(session_bars)
    runner = P2SetupRunner(setup)
    engine = BacktestEngine(cfg)
    initial_working: list[QueuedOrder] = []
    if setup.entry_fill_index == 0:
        runner.mark_entry_submitted()
        req = runner.entry_order_request()
        validate_order_request(req)
        validate_bracket_geometry_in_orders([req], config=cfg)
        initial_working.append(QueuedOrder(1, req))
    return engine.run(
        bars,
        [as_module(_module_id(setup.hypothesis_id), runner)],
        initial_working=initial_working,
    )


_V4_THRESHOLD_BY_HYPOTHESIS: dict[str, float] = {
    "H-4": 150.0,
}


def execute_setups(
    setups: list[P2Setup],
    sessions: dict[dt.date, pl.DataFrame],
    *,
    hypothesis_id: str,
    config: BacktestConfig | None = None,
) -> P2ExecutionBatch:
    """Execute setups session-by-session; combine trade logs."""
    cfg = config or P2_W2_BACKTEST_CONFIG
    rejects: Counter[str] = Counter()
    ledger_rejects: Counter[str] = Counter()
    frames: list[pl.DataFrame] = []

    for setup in setups:
        sess = sessions.get(setup.cme_session_date)
        if sess is None or sess.is_empty():
            continue
        outcome = execute_setup(setup, sess, config=cfg)
        if isinstance(outcome, GeometryReject):
            rejects[outcome.reason] += 1
            continue
        if outcome is None:
            continue
        for reason, count in outcome.geometry_rejects.items():
            ledger_rejects[reason] += count
        if not outcome.trade_log.is_empty():
            frames.append(outcome.trade_log)

    if frames:
        combined = pl.concat(frames).sort("entry_time")
        combined = combined.with_columns(pl.arange(1, combined.height + 1).alias("trade_id"))
    else:
        combined = empty_trade_log()

    total_attempts = len(setups) + sum(rejects.values())
    validation = validate_backtest_result(
        combined,
        config=cfg,
        geometry_reject_rate=sum(rejects.values()) / max(total_attempts, 1),
        bars=None,
        thresholds=ValidationThresholds(
            implausible_net_ticks_per_trade=_V4_THRESHOLD_BY_HYPOTHESIS.get(
                hypothesis_id, P2_W2_V4_TICK_THRESHOLD
            ),
        ),
    )
    return P2ExecutionBatch(
        hypothesis_id=hypothesis_id,
        setups_scanned=len(setups),
        setups_filled=combined.height,
        geometry_rejects=dict(rejects),
        trade_log=combined,
        validation_report=validation,
        ledger_geometry_rejects=dict(ledger_rejects),
    )


def session_frames(mnq: pl.DataFrame) -> dict[dt.date, pl.DataFrame]:
    """Map cme_session_date → sorted session bars."""
    out: dict[dt.date, pl.DataFrame] = {}
    for sd in mnq["cme_session_date"].unique().drop_nulls().to_list():
        out[sd] = mnq.filter(pl.col("cme_session_date") == sd).sort("timestamp")
    return out
