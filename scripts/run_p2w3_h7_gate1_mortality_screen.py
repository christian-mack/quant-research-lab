#!/usr/bin/env python3
"""RETIRED — bespoke H-7 walker removed; use M4 engine re-run instead."""

from __future__ import annotations

import sys

_MSG = (
    "RETIRED: simulate_p2_trade / run_hypothesis walker removed (P2 M4 migration).\n"
    "Use: uv run python scripts/run_p2_m4_gate1_rerun.py\n"
    "Artifact: notebooks/validation/2026-06-08_p2_m4_gate1_rerun.md"
)


def main() -> int:
    print(_MSG, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
