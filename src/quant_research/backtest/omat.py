"""OneModuleAtATime (OMAT) + module priority order collection."""

from __future__ import annotations

from collections.abc import Sequence

from quant_research.backtest.specs import OrchestrationSpec
from quant_research.backtest.types import BarContext, OrderRequest, Strategy


class StrategyModule:
    """Named strategy slot for multi-module backtests (ORB + Opt3, etc.)."""

    __slots__ = ("module_id", "strategy")

    def __init__(self, module_id: str, strategy: Strategy) -> None:
        self.module_id = module_id
        self.strategy = strategy


def priority_module_ids(
    modules: Sequence[StrategyModule],
    orchestration: OrchestrationSpec,
) -> list[str]:
    """Earlier id = higher priority. ``orchestration.module_ids`` overrides list order."""
    got = {m.module_id for m in modules}
    if orchestration.module_ids:
        declared = list(orchestration.module_ids)
        if set(declared) != got:
            msg = (
                f"orchestration.module_ids {declared!r} must match "
                f"strategy module ids exactly: {sorted(got)!r}"
            )
            raise ValueError(msg)
        if len(declared) != len(got):
            msg = "orchestration.module_ids must not duplicate entries"
            raise ValueError(msg)
        return declared
    return [m.module_id for m in modules]


def collect_orders_for_bar(
    modules: Sequence[StrategyModule],
    ctx: BarContext,
    *,
    orchestration: OrchestrationSpec,
    position_qty: int,
    position_owner: str | None,
) -> list[OrderRequest]:
    """Return routed orders for this bar.

    - **Flat** + ``one_position_at_a_time``: every module runs ``on_bar``; if multiple
      submit orders, keep **only** the highest-priority module's list (first in
      ``priority_module_ids`` among those with non-empty proposals).
    - **In position** + OMAT: only ``position_owner`` runs; others are ignored.
    - OMAT off: concatenate all modules' orders in declaration order.
    """
    if not orchestration.one_position_at_a_time:
        out: list[OrderRequest] = []
        for m in modules:
            got = m.strategy.on_bar(ctx)
            _assert_module_ids(m.module_id, got)
            out.extend(got)
        return out

    if position_qty == 0:
        pri = priority_module_ids(modules, orchestration)
        candidates: list[tuple[int, list[OrderRequest]]] = []
        id_to_mod = {m.module_id: m for m in modules}
        for mid in pri:
            m = id_to_mod[mid]
            got = m.strategy.on_bar(ctx)
            _assert_module_ids(m.module_id, got)
            if got:
                candidates.append((pri.index(mid), got))
        if not candidates:
            return []
        candidates.sort(key=lambda t: t[0])
        return list(candidates[0][1])

    if position_owner is None:
        msg = "internal error: position_qty != 0 but position_owner is None"
        raise RuntimeError(msg)
    id_to_mod = {m.module_id: m for m in modules}
    if position_owner not in id_to_mod:
        msg = f"position_owner {position_owner!r} not in strategy modules"
        raise RuntimeError(msg)
    mod = id_to_mod[position_owner]
    got = mod.strategy.on_bar(ctx)
    _assert_module_ids(mod.module_id, got)
    return got


def _assert_module_ids(expected: str, orders: list[OrderRequest]) -> None:
    for req in orders:
        if req.module_id != expected:
            msg = (
                f"OrderRequest.module_id {req.module_id!r} must match "
                f"strategy module {expected!r}"
            )
            raise ValueError(msg)
