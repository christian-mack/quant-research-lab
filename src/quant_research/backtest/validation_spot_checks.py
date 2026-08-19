"""V5 hand-computation spot checks (imports engine — keep separate to avoid cycles)."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import polars as pl

from quant_research.backtest.engine import BacktestEngine, as_module
from quant_research.backtest.geometry import GeometryError
from quant_research.backtest.specs import (
    BacktestConfig,
    FillModelSpec,
    IntradaySessionHygieneSpec,
    LimitFillMode,
    SessionSpec,
    StopLimitIntrabarPolicy,
)
from quant_research.backtest.types import (
    BarContext,
    OrderRequest,
    OrderSide,
    OrderType,
    SimulatedFill,
)
from quant_research.backtest.validation import CheckResult

CT = ZoneInfo("America/Chicago")


def run_spot_check_suite() -> CheckResult:
    """Audit Q6 ground-truth cases — must reproduce on every run."""
    ok_t1 = _run_spot(
        _bars([(100.0, 101.0, 99.8, 100.2), (100.2, 102.0, 100.0, 101.5)]),
        direction="long",
        entry=100.0,
        stop=99.0,
        target=102.0,
    ) == ("target", 102.0)

    ok_t2 = _run_spot(
        _bars([(100.0, 100.5, 99.8, 100.2), (100.2, 100.4, 98.5, 99.0)]),
        direction="long",
        entry=100.0,
        stop=99.0,
        target=105.0,
    ) == ("stop", 99.0)

    ok_t5 = (
        _run_spot(
            _bars([(100.0, 101.0, 99.5, 100.5), (100.5, 102.0, 100.0, 101.5)]),
            direction="long",
            entry=100.0,
            stop=100.5,
            target=103.0,
            expect_reject=True,
        )
        is None
    )

    passed = ok_t1 and ok_t2 and ok_t5
    return CheckResult(
        "V5",
        "Hand-computation spot check",
        passed,
        (
            f"T1={'ok' if ok_t1 else 'FAIL'} "
            f"T2={'ok' if ok_t2 else 'FAIL'} "
            f"T5_reject={'ok' if ok_t5 else 'FAIL'}"
        ),
        {},
    )


def _spot_check_config() -> BacktestConfig:
    return BacktestConfig(
        fill_model=FillModelSpec(
            stop_limit_intrabar=StopLimitIntrabarPolicy.STOP_BEFORE_TARGET,
            limit_fill_mode=LimitFillMode.TOUCH,
            same_bar_exit_after_entry=True,
        ),
        session=SessionSpec(intraday_hygiene=IntradaySessionHygieneSpec(enabled=False)),
        enforce_trade_geometry=True,
    )


def _bars(rows: list[tuple[float, float, float, float]]) -> pl.DataFrame:
    base = dt.datetime(2024, 6, 10, 8, 30, tzinfo=CT)
    return pl.DataFrame(
        {
            "timestamp": [base + dt.timedelta(minutes=i) for i in range(len(rows))],
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "volume": [100.0] * len(rows),
        }
    )


class _BracketOnce:
    def __init__(self, *, direction: str, entry: float, stop: float, target: float) -> None:
        self._direction = direction
        self._entry = entry
        self._stop = stop
        self._target = target
        self._submitted = False

    def _bracket_orders(self) -> list[OrderRequest]:
        exit_side = OrderSide.SELL if self._direction == "long" else OrderSide.BUY
        common = {
            "quantity": 1,
            "module_id": "spot",
            "bracket_entry": self._entry,
            "bracket_stop": self._stop,
            "bracket_target": self._target,
            "bracket_direction": self._direction,
        }
        return [
            OrderRequest(
                exit_side,
                order_type=OrderType.STOP,
                stop_price=self._stop,
                tag="stop",
                dedupe_tag="stop",
                **common,
            ),
            OrderRequest(
                exit_side,
                order_type=OrderType.LIMIT,
                limit_price=self._target,
                tag="target",
                dedupe_tag="target",
                **common,
            ),
        ]

    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        if ctx.bar_index == 0 and not self._submitted and ctx.position_qty == 0:
            self._submitted = True
            side = OrderSide.BUY if self._direction == "long" else OrderSide.SELL
            return [
                OrderRequest(
                    side,
                    quantity=1,
                    order_type=OrderType.LIMIT,
                    limit_price=self._entry,
                    module_id="spot",
                    tag="entry",
                    bracket_entry=self._entry,
                    bracket_stop=self._stop,
                    bracket_target=self._target,
                    bracket_direction=self._direction,
                )
            ]
        return []

    def on_entry_fill(self, fill: SimulatedFill, ctx: BarContext) -> list[OrderRequest]:
        if fill.tag == "entry":
            return self._bracket_orders()
        return []


def _run_spot(
    bars: pl.DataFrame,
    *,
    direction: str,
    entry: float,
    stop: float,
    target: float,
    expect_reject: bool = False,
) -> tuple[str, float] | None | str:
    engine = BacktestEngine(_spot_check_config())
    mod = _BracketOnce(direction=direction, entry=entry, stop=stop, target=target)
    try:
        result = engine.run(bars, [as_module("spot", mod)], run_validation=False)
    except GeometryError:
        return None if expect_reject else "geometry_error"
    if expect_reject:
        return None if result.trade_log.is_empty() else "unexpected_fill"
    if result.trade_log.is_empty():
        return None
    row = result.trade_log.row(0, named=True)
    return str(row["exit_reason"]), float(row["exit_price"])
