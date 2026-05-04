"""OMAT and module priority (order collection only)."""

from __future__ import annotations

import pytest

from quant_research.backtest.omat import StrategyModule, collect_orders_for_bar
from quant_research.backtest.specs import BacktestConfig, OrchestrationSpec
from quant_research.backtest.types import BarContext, OrderRequest, OrderSide, OrderType

_CTX = BarContext(0, None, 100.0, 101.0, 99.0, 100.5, 1.0)


class _Always:
    def __init__(self, mid: str, n: int = 1) -> None:
        self.mid = mid
        self.n = n

    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        return [
            OrderRequest(
                OrderSide.BUY,
                self.n,
                OrderType.MARKET,
                module_id=self.mid,
            )
        ]


class _Never:
    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        return []


def test_priority_high_wins_when_both_fire() -> None:
    orch = OrchestrationSpec(module_ids=("orb", "opt3"), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)
    mods = [
        StrategyModule("orb", _Always("orb")),
        StrategyModule("opt3", _Always("opt3")),
    ]
    out = collect_orders_for_bar(
        mods,
        _CTX,
        orchestration=cfg.orchestration,
        position_qty=0,
        position_owner=None,
    )
    assert len(out) == 1
    assert out[0].module_id == "orb"


def test_in_position_only_owner_runs() -> None:
    orch = OrchestrationSpec(module_ids=("orb", "opt3"), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)
    mods = [
        StrategyModule("orb", _Never()),
        StrategyModule("opt3", _Always("opt3")),
    ]
    out = collect_orders_for_bar(
        mods,
        _CTX,
        orchestration=cfg.orchestration,
        position_qty=1,
        position_owner="orb",
    )
    assert out == []


def test_omat_off_concatenates() -> None:
    orch = OrchestrationSpec(
        module_ids=("a", "b"),
        one_position_at_a_time=False,
    )
    cfg = BacktestConfig(orchestration=orch)
    mods = [
        StrategyModule("a", _Always("a", n=1)),
        StrategyModule("b", _Always("b", n=2)),
    ]
    out = collect_orders_for_bar(
        mods,
        _CTX,
        orchestration=cfg.orchestration,
        position_qty=0,
        position_owner=None,
    )
    assert len(out) == 2
    assert sum(o.quantity for o in out) == 3


def test_declared_module_ids_must_match() -> None:
    orch = OrchestrationSpec(module_ids=("orb", "opt3"), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)
    mods = [StrategyModule("orb", _Always("orb"))]
    with pytest.raises(ValueError, match="orchestration.module_ids"):
        collect_orders_for_bar(
            mods,
            _CTX,
            orchestration=cfg.orchestration,
            position_qty=0,
            position_owner=None,
        )


def test_order_module_id_mismatch_raises() -> None:
    class _Bad:
        def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
            return [
                OrderRequest(OrderSide.BUY, 1, OrderType.MARKET, module_id="wrong"),
            ]

    orch = OrchestrationSpec(module_ids=("orb",), one_position_at_a_time=True)
    cfg = BacktestConfig(orchestration=orch)
    mods = [StrategyModule("orb", _Bad())]
    with pytest.raises(ValueError, match="must match"):
        collect_orders_for_bar(
            mods,
            _CTX,
            orchestration=cfg.orchestration,
            position_qty=0,
            position_owner=None,
        )
