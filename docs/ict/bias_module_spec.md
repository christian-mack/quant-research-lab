# Bias Module Spec — Daily Bias Mechanization (Spec A prerequisite)

**Status:** COMPLETE — ready for strategy chat. TTrades mechanical spine; CISD and
SMT computable definitions folded in (commit 9ad932e). One modeling decision and
two operator confirmations remain (see end). JadeCap supplements.

**Source-precedence note:** artifact role flags are unchanged (jadecap=primary,
ttrades=supplement by *extraction provenance*); for *mechanization* TTrades leads
per operator decision (research-log 2026-06-02).

---

## What the corpus actually teaches

**TTrades — mechanical framework.** Every day is framed as a **continuation** or
**reversal** of the prior daily candle, anchored on three marked levels: prior-day
**EQ** (50% of prior-day range), **PDH**, **PDL**. The bias is *confirmed*, not
guessed, through a lower-timeframe trigger.
- Day-type framing: Ep @27s, @45s, @64s, @193s, @258s.
- Continuation (bullish): open → trade lower first (sweep / form lower wick) →
  **respect EQ** → expand through PDH (@193s, @258s).
- Reversal (bullish→bearish): open → trade into PDH (sweep buyside) → shallow-wick
  reversal → back toward EQ/PDL (@45s, @64s).

**JadeCap — supplement.** Two discretionary steps: premium/discount on a
hand-plotted daily fib (swing high→low; >50% premium = favor short, <50% discount
= favor long; @79s, @133s) + Power of Three timing. Override = **time alignment**:
sit out when PO3 timing doesn't mesh with bias (@603s, @762s, @839s). Used here
only to corroborate the premium/discount read and the no-trade default.

---

## The five questions

**1. Mechanical bias rule (long / short / no-clear-bias).** COMPUTABLE from TTrades:
- Inputs at decision time: prior daily candle (close position, range, wick size),
  PDH, PDL, prior-day EQ.
- State machine: prior close near high → bullish prior context; mark levels →
  classify continuation vs reversal → emit bias *only* once the confirmation chain
  fires (below). Output ∈ {long, short, no-clear-bias}.
- `[DISCRETIONARY SEED]` the ex-ante continuation-vs-reversal call. TTrades reduces
  it to two concrete proxies — prior-day **close position** and **wick size** — but
  the final classification often resolves intrabar (which level sweeps first), so
  the *seed* retains judgment. This is the narrowed irreducible boundary (see #5).

**2. Reference timeframe(s).** Daily for bias + levels. Intraday confirmation on
**hourly / 30-min early in the session**, **15- / 5-min into New York** (@100s,
@130s, @420s, @433s). Concrete, mechanizable.

**3. No-clear-bias handling → NO TRADE.** Explicit and mechanizable. Stand aside on:
consolidation/range (16 no_clear_bias hits; @616s), no CISD confirmation, or an
opposing EQ closure. JadeCap corroborates ("sit on my hands", @717s). **Frequency
implication is real** — bias gate will zero out trading days; size the eval
expectation accordingly.

**4. Midpoint validation — RESOLVED, with a relabel.** TTrades' real rule is
**EQ-respect**: "I don't want to see a closure below that EQ level… less probable"
(@227s). That *is* your A+ logic — trades-to/slightly-past acceptable, **closes
past = invalidation** — but anchored on the **prior-day EQ (50% of the daily
range)**, not an FVG midpoint. So:
- Corpus-derived: closure-past-50%-of-the-daily-range against bias = invalidation.
- `[OPERATOR-SUPPLIED]` the **FVG-midpoint** framing specifically is your rule, not
  TTrades'. Recommend implementing the EQ-closure rule as canonical (sourced) and
  carrying the FVG-midpoint version as your labeled extension, tested separately.

**5. Nested override — MOSTLY MECHANIZABLE (better than first assessed).** The
override mechanic is concrete: a lower-TF move against the daily bias is treated as
**retracement, not reversal, unless** it produces its own **CISD** + sweep and
**respects/violates EQ** (@577s "this can still be part of a retracement, not
[the move]"; @227s EQ-closure). That logic codes cleanly. The honest residue: it
all seeds off the daily day-type/draw call in #1 — *override-given-bias* is
mechanical; *establishing the seed bias* retains discretion. So #5 is not the
irreducible boundary; #1's seed is.

---

## Confirmation chain (the load-bearing mechanic)

The bias does not fire on a level or closure alone — it requires **Change in State
of Delivery (CISD)** on the pairing timeframe, ideally with **SMT** (cross-
instrument divergence at PDH/PDL):
- CISD as the trust gate: @134s, @420s, @706s, @850s ("am I going to trust this
  yet? No, I need… a change in the state of delivery").
- SMT preferred with the candle-2 closure: @433s, @878s ("I do prefer to have SMT
  paired with it").
- Entry reference / "T-spot" = the EQ / point of interest (@371s); candle-2 closure
  model (@174s, @622s).

## CISD — computable definition (from ttrades_cisd.json, commit 9ad932e)

CISD = price shifting bullish↔bearish, marked by a **close beyond the opening
price of the candle (or series) that made the extreme before displacement**:
- **Bearish CISD:** identify the up-close candle(s) that made the new high before
  price displaced down; mark the **opening price of the FIRST** up-close candle in
  that series; CISD fires when a subsequent candle **closes below** that opening
  price (@47s, @49s, @80s, @163s).
- **Bullish CISD:** symmetric — down-close candle(s) making the low; close **above**
  the first candle's opening price (@61s).
- Context: confirmed on a lower timeframe **after** price engages an HTF PD array
  (daily FVG) and ideally **after a liquidity sweep** of an old high/low (@246s,
  @295s–@303s). The CISD candle/zone **forms the order block** used for entry; stop
  on the manipulation high/low that swept (@532s). This is a precise structural
  rule — fully mechanizable.

## SMT — computable definition (from ttrades_smt.json, commit 9ad932e)

SMT = a **divergence between correlated instruments** at a swing point: normally
ES/NQ/YM share structure (@11s, @17s); SMT is when one breaks a level and the
correlated one does **not**.
- **Bullish SMT (at lows):** one instrument makes a lower low, the correlated one
  makes a **higher low** (fails to take out its prior low) → possible bullish
  reversal (@27s, @41s, @163s).
- **Bearish SMT (at highs):** one makes a higher high, the correlated one makes a
  **lower high** (@62s, @93s–@104s).
- For MNQ: correlated instrument = **ES/MES and/or YM** (he uses Nasdaq vs S&P vs
  Dow, @78s, @155s). Used as confluence with CISD + FVG + session timing (the
  "8:35 NASDAQ takes the lows → SMT" example, @312s). Detection is mechanical;
  the only soft step is picking the "cleaner" instrument to trade (@446s) — a
  display choice, not a detection ambiguity.

Both confirm the bias state: bias fires on sweep → CISD (lower-TF) → ideally SMT,
with EQ respected.

## Target-distance modulation (bonus, mechanizable)

Wick size sets expansion expectation: **small/shallow wick → expansion** (target
beyond PDH/PDL); **large wick → limited** (target ~daily open / the level, not
beyond) — @74s, @90s, @243s. Useful later for Spec A's target selection, not for
bias direction itself.

---

## How this plugs into Spec A

Spec A's open item was "bias must be top-down, operator would skip a clean setup
when HTF disagrees." This module supplies that gate: Spec A only seeks its
sweep→MSS→FVG→OTE setup **in the direction of the emitted daily bias**, and treats
a setup against bias as no-trade (mirrors TTrades' retracement-vs-reversal rule).
No-clear-bias day → Spec A stands down.

## Remaining open items before Cursor implementation

- `[DISCRETIONARY SEED]` continuation-vs-reversal classification (#1) — needs a
  mechanical proxy decision OR Phase-C labeling. Proposed proxy: prior-day close
  position (upper/lower third → directional context) + wick-size threshold; flag
  as approximation. **This is now the only true open modeling decision.**
- `[RESOLVED]` CISD mechanical definition — see CISD section above.
- `[RESOLVED]` SMT — correlated instrument (ES/MES, YM) + divergence rule above.
- `[OPERATOR-SUPPLIED]` confirm EQ-closure as canonical midpoint rule vs your
  FVG-midpoint extension.
