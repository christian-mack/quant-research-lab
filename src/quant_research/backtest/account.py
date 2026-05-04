"""Account: futures-style P&amp;L from fills (no notional debit on open)."""

from __future__ import annotations

from dataclasses import dataclass

from quant_research.backtest.specs import InstrumentSpec
from quant_research.backtest.types import OrderSide, SimulatedFill


@dataclass(slots=True)
class Account:
    """``tick_value`` = USD per **one full price index point** per contract (MNQ: $2)."""

    instrument: InstrumentSpec
    initial_cash: float
    cash: float
    position_qty: int
    avg_entry: float
    realized_pnl: float
    total_commission: float

    def __init__(self, initial_cash: float, instrument: InstrumentSpec) -> None:
        self.instrument = instrument
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.position_qty = 0
        self.avg_entry = 0.0
        self.realized_pnl = 0.0
        self.total_commission = 0.0

    def _dollars_per_point(self) -> float:
        return self.instrument.tick_value

    def apply_fill(self, fill: SimulatedFill) -> None:
        self.cash -= fill.commission
        self.total_commission += fill.commission
        pnl = self._apply_signed_fill(fill.side, fill.quantity, fill.price)
        self.cash += pnl
        self.realized_pnl += pnl

    def unrealized_pnl(self, mark: float) -> float:
        if self.position_qty == 0:
            return 0.0
        if self.position_qty > 0:
            return (mark - self.avg_entry) * self.position_qty * self._dollars_per_point()
        absq = -self.position_qty
        return (self.avg_entry - mark) * absq * self._dollars_per_point()

    def equity(self, mark: float) -> float:
        return self.cash + self.unrealized_pnl(mark)

    def _apply_signed_fill(self, side: OrderSide, qty: int, price: float) -> float:
        if side == OrderSide.BUY:
            return self._apply_buy(qty, price)
        return self._apply_sell(qty, price)

    def _apply_buy(self, q: int, price: float) -> float:
        realized = 0.0
        if self.position_qty < 0:
            cover = min(q, -self.position_qty)
            realized += (self.avg_entry - price) * cover * self._dollars_per_point()
            self.position_qty += cover
            q -= cover
            if self.position_qty == 0:
                self.avg_entry = 0.0
        if q > 0:
            if self.position_qty > 0:
                n = self.position_qty + q
                self.avg_entry = (self.avg_entry * self.position_qty + price * q) / n
                self.position_qty = n
            else:
                self.avg_entry = price
                self.position_qty = q
        return realized

    def _apply_sell(self, q: int, price: float) -> float:
        realized = 0.0
        if self.position_qty > 0:
            close = min(q, self.position_qty)
            realized += (price - self.avg_entry) * close * self._dollars_per_point()
            self.position_qty -= close
            q -= close
            if self.position_qty == 0:
                self.avg_entry = 0.0
        if q > 0:
            if self.position_qty < 0:
                absq = -self.position_qty
                self.avg_entry = (self.avg_entry * absq + price * q) / (absq + q)
                self.position_qty -= q
            else:
                self.avg_entry = price
                self.position_qty = -q
        return realized
