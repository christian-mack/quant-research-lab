"""Trade geometry invariants: entry, stop, and target must be coherent at entry time."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

REJECT_STOP_WRONG_SIDE: Final[str] = "stop_wrong_side"
REJECT_TARGET_WRONG_SIDE: Final[str] = "target_unreachable"

TradeDirection = Literal["long", "short"]


@dataclass(frozen=True, slots=True)
class GeometryReject:
    """Recorded when a setup or bracket fails the geometry invariant."""

    reason: str
    direction: str
    entry: float
    stop: float
    target: float


class GeometryError(ValueError):
    """Raised when bracket geometry violates the loss-side stop invariant."""

    def __init__(self, reject: GeometryReject) -> None:
        self.reject = reject
        super().__init__(
            f"geometry reject ({reject.reason}): {reject.direction} "
            f"entry={reject.entry} stop={reject.stop} target={reject.target}"
        )


def check_trade_geometry(
    direction: str,
    entry: float,
    stop: float,
    target: float,
) -> GeometryReject | None:
    """Return a reject record when geometry is incoherent, else ``None``.

    Long: stop must be below entry; target must be above entry.
    Short: stop must be above entry; target must be below entry.
    """
    if direction == "long":
        if stop >= entry:
            return GeometryReject(REJECT_STOP_WRONG_SIDE, direction, entry, stop, target)
        if target <= entry:
            return GeometryReject(REJECT_TARGET_WRONG_SIDE, direction, entry, stop, target)
    elif direction == "short":
        if stop <= entry:
            return GeometryReject(REJECT_STOP_WRONG_SIDE, direction, entry, stop, target)
        if target >= entry:
            return GeometryReject(REJECT_TARGET_WRONG_SIDE, direction, entry, stop, target)
    else:
        msg = f"direction must be 'long' or 'short'; got {direction!r}"
        raise ValueError(msg)
    return None


def validate_trade_geometry(
    direction: str,
    entry: float,
    stop: float,
    target: float,
) -> None:
    """Raise :class:`GeometryError` when geometry is incoherent."""
    reject = check_trade_geometry(direction, entry, stop, target)
    if reject is not None:
        raise GeometryError(reject)
