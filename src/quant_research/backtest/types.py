"""Strategy-facing execution types (orders, bar context)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


@dataclass(slots=True)
class OrderRequest:
    side: OrderSide
    quantity: int
    order_type: OrderType
    limit_price: float | None = None
    stop_price: float | None = None
    #: Owning module (required for multi-module / OMAT runs).
    module_id: str = ""
    tag: str = ""


@dataclass(slots=True)
class QueuedOrder:
    """Order waiting in the simulator (market at next open, or working stop/limit)."""

    order_id: int
    request: OrderRequest


@dataclass(slots=True)
class SimulatedFill:
    order_id: int
    timestamp: Any
    side: OrderSide
    quantity: int
    base_price: float
    price: float
    commission: float
    module_id: str = ""
    tag: str = ""


@dataclass(slots=True)
class BarContext:
    bar_index: int
    timestamp: Any
    open: float
    high: float
    low: float
    close: float
    volume: float


class Strategy(Protocol):
    def on_bar(self, ctx: BarContext) -> list[OrderRequest]:
        """Return orders to submit after observing the closed bar."""
        ...
