#!/usr/bin/env python3
"""RETIRED — bespoke simulate_p2_trade removed; forensic artifact is frozen."""

from __future__ import annotations

import sys

_MSG = (
    "RETIRED: simulate_p2_trade removed (P2 M4 migration).\n"
    "Frozen artifact: notebooks/validation/2026-06-08_p2w3_h7_exit_integrity_forensic.md\n"
    "H-7 M4 re-run: notebooks/validation/2026-06-08_p2_m4_gate1_rerun.md"
)


def main() -> int:
    print(_MSG, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
