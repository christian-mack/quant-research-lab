# Wave 1 Track 2 — Phase 1: ICT primitive components

**Date:** 2026-06-04
**Wave:** Wave 1, Track 2 (ICT-derived hypotheses) — Phase 1 (primitives only)
**Scope:** Five standalone, unit-tested ICT primitives under
`src/quant_research/ict/`, plus MYM data preparation. **No** bias module
(Phase 2) and **no** strategy (Phase 3) are built here.
**Status:** RESULT-LOGGED — all five primitives validated cleanly against the
worked examples cited in the source specs. No stop condition fired.

Source specs (authoritative): Spec A (liquidity-sweep reversal) and the Bias
Module Spec (TTrades mechanical daily bias). Worked examples for the
load-bearing mechanics (CISD, SMT) are the TTrades transcripts ingested as the
`cisd_smt` corpus (research-log 2026-06-02; concept maps
`docs/ict_bias_concept_maps/ttrades_{cisd,smt}.json`).

---

## 0. Data preparation — MYM through the MNQ-style pipeline

MYM (Micro E-mini Dow) raw exports (`data/raw/mym/MYM *.Last.txt`, 26 quarterly
files 03-20…06-26) were run through the **same** pipeline as MNQ/MES:
UTC→CT conversion (`data_loader`), continuous contract via data-boundary
fallback (`continuous_contract`), session classification + `cme_session_date`
(`session`), RTH filter (`instrument_pipeline.load_continuous_rth_mnq_style`).
A new `MYM_CONTRACT_GLOB = "mym/MYM *.Last.txt"` was added to `data_loader`.

Coverage verified by `scripts/verify_mym_coverage.py`
(`scripts/_mym_coverage_report.json`), protocol window 2020-01-01 → 2026-06-30:

| Instrument | RTH bars | Session dates | First → Last RTH bar (CT) |
|---|---|---|---|
| MNQ | 599,533 | 1,561 | 2020-01-02 → 2026-04-17 |
| MES | 629,048 | 1,639 | 2020-01-02 → 2026-05-26 |
| **MYM** | **632,947** | **1,650** | **2020-01-02 → 2026-06-04** |

**Gaps:** MYM's only >4-day session gap is **2023-04-05 → 2023-04-17**
(6 session dates) — the *same* Apr 2023 cluster MES has (documented for MES in
research-log Track 1b). It is **not** MYM-specific. MYM does **not** have the
operator-known MNQ export holes (2024-06-18→07-31, 2026-02-03→03-11); it covers
both (32 and 27 session dates respectively).

**Overlap (inner join on `cme_session_date`):**

- MNQ ∩ MES ∩ MYM = **1,551** sessions
- MNQ ∩ MES = **1,551** (so MYM adds **zero** loss — every MNQ∩MES day is an MYM day)
- MNQ ∩ MYM = 1,555

**Decision:** MYM coverage is **additive, not blocking** — materially the same
length as MNQ/MES with no MYM-specific gaps. SMT (Primitive 4) can run the full
three-instrument MNQ/MES/MYM on 1,551 overlapping sessions; the MES-only
fallback is not needed. Because MYM processed exactly like MES with no surprise
(same single shared Apr-2023 gap), **no lessons-log entry** is warranted per
ai-project-instructions Section 6.

---

## Primitives

All primitives are timeframe-agnostic (pass bars at the desired timeframe;
resample upstream with `fvg.resample_ohlc`). Tests live under `tests/ict/`
(58 tests, all passing). Boundary conditions covered per
ai-project-instructions Section 4: first bar, last bar, empty/short frames,
strict-equality edges, missing columns, unsorted input.

### Primitive 1 — PD-array / level marking (`ict/pd_arrays.py`)

Per session, on the daily timeframe: **PDH** (prior-day high), **PDL**
(prior-day low), **prior-day EQ** = `(PDH + PDL) / 2`. Grouped by
`cme_session_date`; prior-day levels are the *previous* session's high/low, so
there is no look-ahead. First session of data → null (no prior day).

Validation (`test_pd_arrays.py`, 6 tests):
- Hand-built 3-session sequence (110/90, 120/100, 105/95): Day 2 PDH/PDL/EQ =
  110/90/100; Day 3 = 120/100/110. ✓
- Intraday→daily OHLC aggregation (first-open / max-high / min-low / last-close). ✓
- First-day null edge case; null-session-date (break/weekend) bars excluded. ✓

### Primitive 2 — FVG detection + midpoint (`ict/fvg.py`)

3-candle imbalance. Bullish: `c3.low > c1.high` → zone `[c1.high, c3.low]`.
Bearish: `c3.high < c1.low` → zone `[c3.high, c1.low]`. Reports
`top`/`bottom`/`midpoint = (top+bottom)/2`/`gap_size`, both directions,
confirmed at c3. `min_gap_size` filters negligible gaps. `resample_ohlc` builds
coarser timeframes.

Validation (`test_fvg.py`, 11 tests):
- Hand-built bullish gap [101,105] midpoint 103; bearish [95,99] midpoint 97. ✓
- No-gap and exact-touch sequences detect nothing (strict inequality). ✓
- `min_gap_size` filtering; both-direction multi-FVG ordering; <3 bars empty. ✓

**Real-data sanity (MNQ, Mar 2024, 20 sessions)** — counts plausible, roughly
bull/bear balanced, scaling correctly with timeframe (no famine/explosion →
stop condition not triggered):

| TF | bars | FVGs | bull | bear | per session | median gap (pts) |
|---|---|---|---|---|---|---|
| 1m | 7,800 | 1,621 | 855 | 766 | 81.0 | 2.75 |
| 5m | 1,560 | 315 | 173 | 142 | 15.8 | 7.0 |
| 15m | 520 | 108 | 57 | 51 | 5.4 | 14.25 |

### Primitive 3 — CISD detection (`ict/cisd.py`) — load-bearing

Per the TTrades mechanical definition (`CHIK5oBRKiw`): **Bearish CISD** — anchor
on the swing high; take the maximal run of consecutive **up-close** candles that
made it; the CISD level is the **opening price of the FIRST** candle in that
run; CISD **fires** when a subsequent candle **closes strictly below** that
level. **Bullish CISD** is the mirror (down-close run at a low, close above
first candle's open). The opposing-close run is exposed as the **order block**
(`ob_top`/`ob_bottom`, `run_start_index`/`run_end_index`).

The "first candle of the series" rule and the "closes below the opening price"
rule are quoted directly from the transcript (@41–53s, @75–101s, @133–151s for
bearish; @60–71s for bullish symmetric; @819–824s for the order block). The
cited example timestamps (@47s, @49s, @61s, @80s, @163s) all map to one
unambiguous mechanic — **no ambiguity stop condition fired**.

Validation (`test_cisd.py`, 13 tests):
- Single up-close candle → level = its open; fires on close below. ✓
- **Series → level is the FIRST candle's open** (not the last); a close between
  the two opens does *not* fire. ✓ (the load-bearing case)
- Bullish symmetric. ✓
- Sweep-wick high (highest high is a down-close rejection wick) → run excludes
  the sweep candle; level anchored to the up-close leg (transcript @155–178s). ✓
- Continuation (no close beyond) does not fire; close exactly at level does not
  fire (strict); anchor at last bar cannot fire; caller-supplied anchor;
  unsorted input sorted. ✓

### Primitive 4 — SMT detection (`ict/smt.py`)

Cross-instrument divergence at a swing point (`q1NmxUTm4n4`). **Bullish SMT**
(lows): one instrument makes a lower low (takes its prior low) while another
makes a higher low (holds). **Bearish SMT** (highs): higher high vs lower high.
Present iff at least one took out and at least one strictly held (exact ties
count as neither — strict "higher/lower"). Reports `present`, `direction`,
per-instrument `took_out`, and `diverged_instruments` (the side that held — the
reversal signal). Works for 2 (MES-vs-MNQ) or 3 (MNQ/MES/MYM) instruments.

Validation (`test_smt.py`, 13 tests):
- Bullish (NQ lower low, ES higher low) and bearish (ES lower high, YM higher
  high) divergence present with correct diverging instrument. ✓
- Aligned cases (all lower lows / all higher highs) → no SMT. ✓
- Equal-low double bottom → not strict → no SMT. ✓
- Three-instrument: NQ takes lows, ES+YM hold → present, two diverging. ✓
- Frame-based extraction over prior/current windows; the **"8:35 NASDAQ takes
  the lows → SMT"** example (@312s) reproduced. ✓

### Primitive 5 — Liquidity sweep detection (`ict/liquidity_sweep.py`)

Price trades **through** a reference level (PDH/PDL or a swing) by `>= ` a
configurable tick threshold, then **closes back inside within N bars**. Sides:
`high` (buy-side liquidity above → bearish reversal) / `low` (sell-side below →
bullish). Anchored to the **first** penetration (a breakout that holds beyond
the level is not a sweep). Per Spec A, sweep depth has **no source value**: the
`penetration_ticks` (default 1) and `close_back_within_bars` (default 3) are
carried as **[MANUAL OBS]** parameters in `SweepConfig` — not hardcoded into
detection — so the strategy layer can sweep them and the choice is auditable.

Validation (`test_liquidity_sweep.py`, 15 tests):
- Single-bar high/low sweep + reversal (wick out, close back in). ✓
- Multi-bar close-back within N; window-edge inclusive; close-back *outside* the
  N-window does not flag (boundary on N). ✓
- Continuation (never closes back) does not flag. ✓
- Penetration must exceed the tick threshold (exact-touch and shallow pokes
  filtered; larger threshold filters a 2-tick poke). ✓
- `search_start_index` skips an earlier sweep; `recent_swing_level` helper;
  invalid config/side/columns raise; empty frame. ✓

---

## Stop conditions — none triggered

- MYM data quality: clean, additive, only the shared Apr-2023 gap → no surface.
- Every primitive validated against its source-cited worked examples.
- CISD (load-bearing) mechanic was unambiguous against the transcript examples.
- FVG counts on a real slice are plausible (no implausible many/few).

## Artifacts

- Code: `src/quant_research/ict/{pd_arrays,fvg,cisd,smt,liquidity_sweep}.py`,
  `src/quant_research/data/data_loader.py` (`MYM_CONTRACT_GLOB`).
- Tests: `tests/ict/test_{pd_arrays,fvg,cisd,smt,liquidity_sweep}.py` (58 tests).
- Data prep: `scripts/verify_mym_coverage.py`, `scripts/_mym_coverage_report.json`.
- Full suite at completion: **305 passed, 31 skipped** (skips are pre-existing
  real-data tests keyed on the flat `data/raw/MNQ 03-26.Last.txt` path).
