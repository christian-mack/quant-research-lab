"""M4 BacktestEngine trade-log provenance (V7 harness).

Only ledgers constructed with the engine-issued seal receive
:data:`M4_ENGINE_PROVENANCE_MARKER` on finalized rows. Hand-built trade logs
and bespoke walkers cannot satisfy V7 without routing fills through
``BacktestEngine`` → ``TradeLedger``.
"""

from __future__ import annotations

M4_ENGINE_PROVENANCE_MARKER = "m4_backtest_engine@v1"

# Singleton seal minted at engine import; identity check prevents casual forgery.
_ENGINE_LEDGER_SEAL: object = object()


def engine_ledger_seal() -> object:
    """Return the seal ``BacktestEngine`` passes to ``TradeLedger``."""
    return _ENGINE_LEDGER_SEAL


def provenance_marker_for_ledger(seal: object | None) -> str:
    """Stamp value for a finalized trade row, or empty when seal is invalid."""
    if seal is _ENGINE_LEDGER_SEAL:
        return M4_ENGINE_PROVENANCE_MARKER
    return ""


def is_m4_engine_provenance(value: object | None) -> bool:
    """Whether a stored provenance field marks an M4 engine row."""
    return value == M4_ENGINE_PROVENANCE_MARKER
