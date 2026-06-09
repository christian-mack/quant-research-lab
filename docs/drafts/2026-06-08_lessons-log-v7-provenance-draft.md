# DRAFT — lessons-log entry (operator approval required; do not append)

## 2026-06-08 — V7 harness guard: engine provenance closes the bespoke-walker bypass class

**Phase:** 2 (Flux V2) / Wave 1 infrastructure (cross-cutting)
**Context:** P2-W3 H-7 exit-integrity forensic showed Gate #1 SURVIVOR (+$20.85/tr, 74.8% WR) was a look-ahead artifact from `simulate_p2_trade`, while V1–V6 harness **PASS** certified ledger coherence only. OTE and Track 1 had the same bypass pattern (lessons-log 2026-06-08).
**Finding:** V1–V6 answer "is this trade log internally consistent?" not "did the M4 engine produce it?" Bespoke walkers can pass V1–V6 while carrying fill-path bugs the M4 engine already prevents. **V7** stamps every `TradeLedger` row with `mfa_engine_provenance` via an engine-issued seal only `BacktestEngine` supplies; the harness fails logs missing the marker.
**Implication:** Standing convention upgrades to **V1–V7**. P2-W2/W3 results remain untrusted on path (W2 negatives stand; H-7 void). Future quant waves must route through `engine.py` before any gate economics are reported. Remediation track: migrate P2 strategies off `simulate_p2_trade`, delete bespoke walker, re-run only after V7 passes.
**Artifact:** `src/quant_research/backtest/provenance.py`; `src/quant_research/backtest/validation.py` (V7); `tests/backtest/test_validation.py`; `docs/ai-project-instructions.md`
