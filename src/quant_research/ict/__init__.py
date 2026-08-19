"""ICT (Inner Circle Trader) primitive components for Wave 1 Track 2.

This subpackage holds **standalone, unit-tested primitives** used to assemble the
daily-bias module (Phase 2) and the liquidity-sweep reversal strategy (Spec A,
Phase 3). Each primitive is built and validated in isolation before any module
or strategy depends on it, per the strategy-chat "primitives first" review and
``docs/ai-project-instructions.md`` (type hints, Google-style docstrings,
pytest coverage including boundary conditions).

Primitives
----------
- :mod:`quant_research.ict.pd_arrays` — Primitive 1: prior-day high/low/EQ
  (PD-array reference levels for bias and sweep detection).
- :mod:`quant_research.ict.fvg` — Primitive 2: fair-value-gap (3-candle
  imbalance) detection with top/bottom/midpoint, both directions.
- :mod:`quant_research.ict.cisd` — Primitive 3: change-in-state-of-delivery
  (CISD) detection per the TTrades mechanical definition, exposing the order-block
  zone used for entry.
- :mod:`quant_research.ict.smt` — Primitive 4: SMT (cross-instrument divergence)
  detection at swing points.
- :mod:`quant_research.ict.liquidity_sweep` — Primitive 5: liquidity-sweep
  detection (trade through a level then close back inside within N bars).
- :mod:`quant_research.ict.mss` — Primitive 6: market structure shift (MSS)
  detection per 2022 mentorship (swing-break after sweep; distinct from CISD).
- :mod:`quant_research.ict.ote_strategy` — Phase 3 standalone OTE strategy
  assembly (sweep → MSS → FVG → OTE; self-contained, no bias gate).

Source specifications: Spec A (liquidity-sweep reversal) and the Bias Module
Spec (TTrades mechanical daily bias). Worked examples for the load-bearing
mechanics (CISD, SMT) are the TTrades transcripts ingested under the ``cisd_smt``
corpus (see ``docs/research-log.md`` 2026-06-02 entries and
``docs/ict_bias_concept_maps/ttrades_{cisd,smt}.json``).
"""

from __future__ import annotations
