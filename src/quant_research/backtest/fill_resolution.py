"""Stop/limit first-touch resolution and market fills at bar open."""

from __future__ import annotations

from quant_research.backtest.specs import (
    BacktestConfig,
    FillModelSpec,
    GapPolicy,
    IntrabarPricePath,
    StopLimitIntrabarPolicy,
)
from quant_research.backtest.tick import apply_slippage
from quant_research.backtest.types import (
    OrderRequest,
    OrderSide,
    OrderType,
    QueuedOrder,
    SimulatedFill,
)


def effective_intrabar_path(fill_model: FillModelSpec) -> IntrabarPricePath:
    pol = fill_model.stop_limit_intrabar
    if pol == StopLimitIntrabarPolicy.PESSIMISTIC:
        return IntrabarPricePath.OPEN_LOW_HIGH_CLOSE
    if pol == StopLimitIntrabarPolicy.OPTIMISTIC:
        return IntrabarPricePath.OPEN_HIGH_LOW_CLOSE
    return fill_model.intrabar_path


def intrabar_pivot_prices(
    open_px: float,
    high: float,
    low: float,
    close: float,
    path: IntrabarPricePath,
) -> list[float]:
    if path == IntrabarPricePath.OPEN_HIGH_LOW_CLOSE:
        seq = (open_px, high, low, close)
    else:
        seq = (open_px, low, high, close)
    out: list[float] = []
    for p in seq:
        if not out or p != out[-1]:
            out.append(p)
    return out


def gap_would_trigger(
    req: OrderRequest,
    prior_close: float | None,
    open_px: float,
) -> bool:
    """Whether the open alone (vs prior close) crosses the stop/limit for gap purposes."""
    if req.order_type == OrderType.STOP:
        sp = req.stop_price
        if sp is None:
            msg = "stop order requires stop_price"
            raise ValueError(msg)
        if req.side == OrderSide.BUY:
            if prior_close is None:
                return open_px >= sp
            return prior_close < sp <= open_px
        if prior_close is None:
            return open_px <= sp
        return prior_close > sp >= open_px
    if req.order_type == OrderType.LIMIT:
        lp = req.limit_price
        if lp is None:
            msg = "limit order requires limit_price"
            raise ValueError(msg)
        if req.side == OrderSide.BUY:
            if prior_close is None:
                return open_px <= lp
            return prior_close > lp >= open_px
        if prior_close is None:
            return open_px >= lp
        return prior_close < lp <= open_px
    return False


def fill_pending_market_at_open(
    pending: list[QueuedOrder],
    open_px: float,
    ts: object,
    config: BacktestConfig,
) -> list[SimulatedFill]:
    fills: list[SimulatedFill] = []
    for w in sorted(pending, key=lambda x: x.order_id):
        req = w.request
        if req.order_type != OrderType.MARKET:
            msg = "pending queue may only contain market orders"
            raise ValueError(msg)
        validate_order_request(req)
        fills.append(_make_fill(w, open_px, ts, config))
    return fills


def resolve_stop_limit_for_bar(
    working: list[QueuedOrder],
    open_px: float,
    high: float,
    low: float,
    close: float,
    prior_close: float | None,
    ts: object,
    config: BacktestConfig,
) -> tuple[list[SimulatedFill], list[QueuedOrder]]:
    """First-touch along intrabar pivots; optional gap-at-open batch."""
    fm = config.fill_model
    remaining = list(working)
    fills: list[SimulatedFill] = []

    for w in remaining:
        validate_order_request(w.request)
        if w.request.order_type == OrderType.MARKET:
            msg = "working stop/limit queue may not contain market orders"
            raise ValueError(msg)

    if fm.gap_policy == GapPolicy.FILL_AT_OPEN:
        gap_hits = [w for w in remaining if gap_would_trigger(w.request, prior_close, open_px)]
        gap_hits.sort(key=lambda w: w.order_id)
        for w in gap_hits:
            fills.append(_make_fill(w, open_px, ts, config))
            remaining.remove(w)

    path = effective_intrabar_path(fm)
    pivots = intrabar_pivot_prices(open_px, high, low, close, path)
    prev = pivots[0]
    for curr in pivots[1:]:
        hits: list[tuple[int, QueuedOrder, float]] = []
        for w in remaining:
            px = _touch_price_if_triggers(w.request, prev, curr)
            if px is not None:
                hits.append((w.order_id, w, px))
        hits.sort(key=lambda t: t[0])
        for _, w, px in hits:
            fills.append(_make_fill(w, px, ts, config))
            remaining.remove(w)
        prev = curr

    return fills, remaining


def _buy_stop_crosses(prev: float, curr: float, stop: float) -> bool:
    return curr > prev and prev < stop <= curr


def _sell_stop_crosses(prev: float, curr: float, stop: float) -> bool:
    return curr < prev and prev > stop >= curr


def _buy_limit_crosses(prev: float, curr: float, limit: float) -> bool:
    return curr < prev and prev > limit >= curr


def _sell_limit_crosses(prev: float, curr: float, limit: float) -> bool:
    return curr > prev and prev < limit <= curr


def _touch_price_if_triggers(req: OrderRequest, prev: float, curr: float) -> float | None:
    if req.order_type == OrderType.STOP:
        sp = req.stop_price
        assert sp is not None
        if req.side == OrderSide.BUY and _buy_stop_crosses(prev, curr, sp):
            return sp
        if req.side == OrderSide.SELL and _sell_stop_crosses(prev, curr, sp):
            return sp
        return None
    if req.order_type == OrderType.LIMIT:
        lp = req.limit_price
        assert lp is not None
        if req.side == OrderSide.BUY and _buy_limit_crosses(prev, curr, lp):
            return lp
        if req.side == OrderSide.SELL and _sell_limit_crosses(prev, curr, lp):
            return lp
        return None
    return None


def _make_fill(
    order: QueuedOrder,
    base_price: float,
    ts: object,
    config: BacktestConfig,
) -> SimulatedFill:
    req = order.request
    slip_px = apply_slippage(base_price, req.side, config.slippage, config.instrument)
    comm = abs(req.quantity) * config.commission.per_contract_per_fill
    return SimulatedFill(
        order_id=order.order_id,
        timestamp=ts,
        side=req.side,
        quantity=req.quantity,
        base_price=base_price,
        price=slip_px,
        commission=comm,
        module_id=req.module_id,
        tag=req.tag,
    )


def validate_order_request(req: OrderRequest) -> None:
    if req.quantity <= 0:
        msg = "order quantity must be positive"
        raise ValueError(msg)
    if req.order_type == OrderType.MARKET:
        if req.limit_price is not None or req.stop_price is not None:
            msg = "market order must not set limit_price or stop_price"
            raise ValueError(msg)
    elif req.order_type == OrderType.LIMIT:
        if req.limit_price is None:
            msg = "limit order requires limit_price"
            raise ValueError(msg)
    elif req.order_type == OrderType.STOP:
        if req.stop_price is None:
            msg = "stop order requires stop_price"
            raise ValueError(msg)
    else:
        msg = f"unknown order type: {req.order_type!r}"
        raise ValueError(msg)


def synthetic_market_fill(
    *,
    order_id: int,
    module_id: str,
    side: OrderSide,
    quantity: int,
    base_price: float,
    ts: object,
    config: BacktestConfig,
    tag: str,
) -> SimulatedFill:
    """Used for end-of-series flatten at last bar close (engine applies slippage + snap)."""
    req = OrderRequest(
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET,
        module_id=module_id,
        tag=tag,
    )
    validate_order_request(req)
    q = QueuedOrder(order_id, req)
    return _make_fill(q, base_price, ts, config)
