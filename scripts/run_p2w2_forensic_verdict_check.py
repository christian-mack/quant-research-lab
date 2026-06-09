#!/usr/bin/env python3
"""RETIRED — bespoke P2Trade walker removed; forensic artifacts are frozen."""

from __future__ import annotations

import sys

_MSG = (
    "RETIRED: P2Trade / run_hypothesis walker removed (P2 M4 migration).\n"
    "Frozen artifact: notebooks/validation/2026-06-08_p2w2_forensic_verdict_check.md\n"
    "Trusted re-run: uv run python scripts/run_p2_m4_gate1_rerun.py"
)


def main() -> int:
    print(_MSG, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
