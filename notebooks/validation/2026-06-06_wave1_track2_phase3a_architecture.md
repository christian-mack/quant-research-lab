# Wave 1 Track 2 — Phase 3a: Bias / Entry Architecture Diagnostic

**Date:** 2026-06-06  
**Wave:** Wave 1, Track 2 — Phase 3a (source-material diagnostic only; **no strategy code**)  
**Purpose:** Resolve the structural ambiguity between the Phase 2 daily bias module
(TTrades corpus: sweep → CISD → EQ-respect → optional SMT) and Spec A (2022
mentorship corpus: sweep → MSS → displacement/FVG → OTE entry) **before** Phase 3
strategy assembly.

**Sources read:**
- `docs/ict/spec_a_liquidity_sweep_reversal.md`, `docs/ict/bias_module_spec.md`
- Phase 2 implementation: `src/quant_research/ict/bias_module.py`, `cisd.py`
- **TTrades corpus:** processed transcripts
  `data/processed/transcripts/cisd_smt/CHIK5oBRKiw.json` (CISD),
  `data/processed/transcripts/bias/-KKuZb5Z5aU.json` (daily bias);
  concept maps `docs/ict_bias_concept_maps/ttrades_{cisd,supplement}.json`
- **2022 mentorship corpus:** processed transcripts for Ep 6 (`Bkt8B3kLATQ`),
  Ep 12 (`8GkQfdAXZP0`), Ep 25 (`CnTXwAuDi9Y`), Ep 38 (`36184dDAqtM`),
  Ep 41 (`2XhDi5GoNUI`); manifest `data/raw/ict_sources/manifest.csv`

**Method:** Passages extracted from auto-generated YouTube captions at cited
timestamps (±15–25 s window). Term cross-search: the 2022 Ep 6/12/25/38/41
transcripts contain **zero** hits for “change in state of delivery” / “state of
delivery”; the TTrades bias supplement contains **zero** hits for “market
structure shift” / “MSS”.

---

## Executive summary

| Question | Answer (short) | Confidence |
|---|---|---|
| **Q1 — MSS vs CISD** | **Distinct mechanics**, same narrative role (post-sweep directional confirmation). Often co-locate; **not interchangeable** as detection rules. | **High** |
| **Q2 — Bias/entry relationship** | **Corpora disagree in emphasis.** 2022 Spec A ≈ **Architecture A** (one manipulation leg → MSS → FVG → OTE). TTrades daily bias ≈ **Architecture C** (HTF bias confirmed on pairing TF; entry timed lower via candle 2/3 or 5m CISD). **Not fully resolved to a single architecture** for Phase 3 without an operator decision on scope. | **Medium** (split by corpus) |
| **Q3 — Timeframes** | TTrades: **explicit pairing ladder** (hourly/30m early → 15m/5m into NY for CISD; 5m for entry timing). 2022: **multi-TF stack** (15m/50m FVG context, 5m for flagship OTE execution). Bias confirmation TF ≠ entry execution TF in both teachings. | **High** (TTrades); **Medium** (2022 — less prescriptive ladder) |
| **Q4 — Corpora differ?** | **Yes.** Different confirmation vocabulary (MSS vs CISD), different entry mechanics (FVG/OTE vs CISD/candle-2/3/OB), different bias framing (2022 discretionary HTF vs TTrades mechanical daily). This is **not purely a two-corpus artifact** — the methods differ — but our build **did conflate the plug-in point** by implying one chain serves both roles. | **High** |

**Recommended Phase 3 architecture (pending operator sign-off):**

Treat Phase 2 bias as a **session-level directional gate only** (long / short /
no-clear-bias). Build Spec A entry as a **separate intraday setup detector** using
**MSS + FVG + OTE per the 2022 corpus**, not by re-firing CISD from the bias
module. Default working model: **Architecture C with optional same-leg overlap**
— bias confirmed on the pre-registered pairing TF (5m primary); entry sought on
the **same session** in the bias direction using **MSS → FVG → OTE**, allowing
entry on a **later sub-leg** of the session (TTrades @622) or the **same
manipulation leg** when timestamps align (2022 Ep 25/38). Pre-register whether
entry must occur **after** bias emission time (conservative) vs **any same-session
setup in bias direction** (permissive).

**Stop-condition check:** Source does **not** invalidate Phase 2’s CISD-based bias
module for its stated purpose (TTrades mechanical daily bias). It **does**
contradict treating CISD as Spec A’s MSS substitute — **surface immediately**;
Phase 3 must add MSS detection, not relabel CISD.

---

## Q1 — MSS vs CISD: same, overlapping, or distinct?

### Verdict: **Distinct mechanics; overlapping narrative role**

Both mark a directional change after a liquidity event, but the **computable
triggers differ**. They may fire near each other in live price, but one can
 occur without the other under our operational definitions.

### 2022 mentorship — Market Structure Shift (MSS)

**Ep 6 @1110s (bearish MSS, conceptual):**

> “the bearish market structure shift … the market trading higher … trades above
> an old high or the initial short-term high … and then it **breaks down** — once
> **that low is broken** that's when the new trade idea is now being birthed”

**Ep 6 @1416s (bullish MSS, pattern criteria):**

> “a market [trades] below … old low … run into sell stops … then you're looking
> for a run higher that **takes out a short term high** and it **closes above it**
> with an energetic displacement higher — once you see that then you have a trade
> idea being birthed”

**Ep 12 @2247s (MSS + imbalance, Spec A anchor):**

> “you have to look for what the **short-term low being broken** — that's your
> **Market structure shift** — then you see price go up into that **imbalance**
> and then you can go short”

**Ep 25 @2006s (judas → pattern chain):**

> “it creates the pattern that's in the mentorship — **fair value gap**, **market
> structure shift**, then starts to show **displacement** … attacking a discount
> array”

**Operational Spec A definition (from spec + Ep 6/12):** break of the most recent
opposing **short-term swing** (Spec A default: 3-bar fractal). Trigger = **price
structure break** (swing high/low taken out).

**Note (Ep 12 nuance):** In the same passage ICT discusses an alternate read where
an FVG breakdown forms and “I don't need a swing low broken” on *that* sub-model —
showing MSS is not the only imbalance-based narrative in 2022, but MSS remains
explicitly defined as **short-term swing break**.

### TTrades — Change in State of Delivery (CISD)

**CHIK5oBRKiw @41–49s (core definition):**

> “this up close candle here gets **closed below** here and that is when the change
> in state of delivery occurs when the **opening price** of this up closed candle
> or series of up closed candles gets closed below”

**@80s (series rule — load-bearing):**

> “when there is more than one up closed candle … I use the **opening price of the
> first candle** … I will look for this price to be closed below”

**@133–151s (sweep + displacement context):**

> “the series or single up close candle that made the new high **before
> displacing** and closing below … I'd want to see a **close below** here”

**Operational CISD definition (Phase 1/2):** close **strictly beyond the opening
price of the first opposing-close candle** in the run that made the swing extreme
— not a generic swing fractal break.

### Comparison

| Dimension | MSS (2022) | CISD (TTrades) |
|---|---|---|
| **Trigger type** | Swing **high/low broken** (structure) | Close beyond **first opposing candle open** (delivery change) |
| **Anchor** | Short-term swing (Spec A: 3-bar fractal) | Opposing-close **series** at manipulation extreme |
| **Terminology in other corpus** | Absent from TTrades bias/CISD transcripts | Absent from 2022 Ep 6/12/25/38/41 transcripts |
| **Typical sequence position** | After sweep → before/at displacement FVG | After sweep → before continuation; **forms order block** |
| **Co-occurrence** | Often near CISD in real bars | Often near MSS, but **not guaranteed** by either rule |

**Can one fire without the other?** **Yes, in principle.** A close beyond the
first up-close open (CISD) may occur before or without a clean 3-bar fractal
break (MSS), and vice versa. Phase 2 diagnostics (75% no-clear-bias) show CISD+EQ
is already a strict filter; swapping in MSS would change frequencies independently.

**Stop-condition:** We did **not** build the “wrong” confirmation for Phase 2 —
CISD is what TTrades prescribes for **daily bias**. The error would be **using
CISD as Spec A’s MSS** in Phase 3. That requires a **new MSS primitive**, not
revisiting Phase 2 unless operator chooses TTrades-only entry (CISD/OB) instead
of Spec A (MSS/FVG/OTE).

---

## Q2 — Bias / entry relationship: Architecture A, B, or C?

### Architecture definitions (for this diagnostic)

- **A — Single sequence:** The sweep → shift → displacement that confirms bias is
  **the same** leg used for OTE entry (retrace into **that** FVG).
- **B — Bias then fresh setup:** Bias locks direction; a **later, separate**
  sweep → MSS → FVG → OTE provides the trade.
- **C — Nested timeframes:** Bias confirmed on **higher pairing TF**; entry timed
  on **lower TF** within the same directional move (may share the same sweep or a
  sub-leg).

### 2022 mentorship → supports **Architecture A** for the **trade setup chain**

The flagship pattern is one continuous narrative: manipulation → MSS → FVG → OTE.

**Ep 38 @2587s (sweep → FVG → buy — same leg):**

> “turtle suit … lower low … **find the fair value gap below 50 level** which is a
> discount — as soon as it trades at the **top level of it**, buy it there — stop
> below the lower low”

**Ep 41 @985s / @1110s (gold standard — MSS + FVG + OB + OTE on lower TF):**

> “**fair value gap** with an **order block** and **optimal trade entry** is the
> gold standard of the ICT pattern” … “does it show willingness to go higher …
> **short term shift in market structure** … is there a **gap** … **bullish order
> block optimal trade entry** … **62 to 70 retracement**”

**Ep 25 @2006s:** judas rally → “**fair value gap market structure shift** then
**displacement**” inside the same power-3 session narrative.

**2022 on HTF bias:** Ep 38/41 do **not** teach a mechanical daily bias module
comparable to Phase 2. Bias is **discretionary** (midnight open, power-3, dealing
range — Spec A open item). Phase 2 supplies the missing gate **from TTrades**, not
from 2022.

**Implication for Spec A:** Entry chain is **MSS → FVG → OTE**, entered on retrace
into the displacement gap from **that** manipulation leg — classic **Architecture A**
for the setup itself.

### TTrades daily bias → supports **Architecture C** (bias vs entry separated by TF)

**`-KKuZb5Z5aU` @134s (CISD confirms HTF wick — bias, not OTE):**

> “I will be using a **change in the state of delivery intraday** to **confirm the
> wick** of that higher time frame candle, and then we can **trade the body**”

**@420–433s (pairing TF for CISD; targets are EQ/FVG, not OTE band):**

> “change in the state of delivery on the **hourly** … or … **15-minute or
> 5-minute** … SMT at the previous day low with a change in the state of delivery
> … trade back into the range … towards the **EQ or this fair value gap**”

**@622s (explicit TF split — bias context → lower TF entry):**

> “change in the state of delivery with an ideal **candle two closure**. This is
> where I could take an entry on the **open of candle three** … or … **hourly
> candle two closure**. I could look to the **five-minute** to trade a five-minute
> continuation in candle three. But … **if you do have a bias** you do want to …
> **keep that with that bias**”

**@706s (hourly frame → 5m CISD for execution):**

> “here we are on the **five-minute** … what confirms that? … wait for … **change
> in the state of delivery** … which then **protects this high**”

**TTrades CISD video (`CHIK5oBRKiw` @532s) — Architecture A *for the CISD entry
model* (not the daily-bias video):**

> “enter **here at the change of state of delivery** or when it **retests the order
> block** — stop on the **manipulation High which swept**”

So TTrades actually teaches **two layers**:
1. **Daily bias:** sweep → CISD → EQ (+ SMT) on pairing TF — confirms direction /
   session bias (Phase 2 scope).
2. **Entry:** candle 2/3 model and/or **lower-TF CISD**, or CISD/OB retest per the
   CISD video — **not** 2022-style MSS→FVG→OTE 62–79% band.

**@622 also shows sub-leg behavior (B/C hybrid):** After a bias-aligned context,
price **sweeps again** in consolidation before a **second** CISD + candle-2 entry
— evidence that entry can be a **later refinement**, not only the first bias CISD.

### Cross-corpus synthesis for Q2

| Layer | 2022 Spec A | TTrades (Phase 2 bias + entry refs) |
|---|---|---|
| **Direction filter** | Discretionary HTF (Phase 2 replaces with TTrades gate) | sweep → CISD → EQ (+ SMT) |
| **Setup confirmation** | **MSS** (swing break) | **CISD** (close beyond first opposing open) |
| **Entry mechanics** | **FVG retrace + OTE 62–79%** | **CISD/OB retest** or **candle 2/3** on lower TF |
| **Architecture** | **A** on the manipulation leg | **C** (bias TF ≠ entry TF); **B-like** sub-legs possible (@622) |

**What the source cannot fully resolve:** Whether Phase 3 should require Spec A’s
**MSS→FVG→OTE** on the **exact same sweep** that produced Phase 2 bias CISD, or
any **same-session** MSS→FVG→OTE **after** bias time in the gated direction. Neither
corpus states this plug-in explicitly because **they were not written as one
integrated spec**.

**Confidence:** **Medium overall.** High that **2022 entry ≠ TTrades bias chain**;
medium on single vs multiple setup legs when forced together.

---

## Q3 — Timeframe structure: bias confirmation vs entry timing

### TTrades (explicit)

**`-KKuZb5Z5aU` @100s / @420s:**

> “**hourly / 30-min early** in the session, **15- / 5-min into New York**” for
> change in the state of delivery

**@622 / @706:** Bias/framing on **hourly**; execution confirmation on **5-minute**

**Phase 2 pre-registration:** pairing TF **5m primary**, 15m variant — aligned with
“into New York” guidance, not hourly (modeling choice documented in Phase 2).

**Entry timing relative to bias TF:** **Lower** (5m continuation inside hourly
candle 3 — @622). CISD video uses **5m** “just before New York open” (@133).

### 2022 mentorship (multi-TF stack; less rigid ladder)

| Episode | Timestamp | TF cited | Role |
|---|---|---|---|
| Ep 38 | @645s | **5-minute** | Session execution after 9:30 open |
| Ep 41 | @151s, @810s, @985s | **15-minute**, **50-minute** | FVG / context |
| Ep 41 | @1110s | **5-minute** | Flagship OTE + MSS + FVG execution |
| Ep 25 | @2259s | **5m → 4m** | Judas leg drill-down |
| Ep 6 | @1599–1723s | **15m → 5m → 1m** | Pattern illustration |

**Spec A pre-registration:** NY AM 08:30–11:00 ET; displacement = FVG on MSS leg;
OTE limit into that FVG. Source supports **entry on lower TF than the FVG context
TF** (15m gap, 5m execution — Ep 41).

### Answer

- **Bias confirmation (Phase 2):** daily levels + **5m/15m CISD** (TTrades pairing).
- **Spec A entry (2022):** typically **15m (or higher) for FVG formation**, **5m**
  for OTE execution (Ep 41); not necessarily the same bar series as bias CISD.
- **Same TF for both?** **No** — both teachings use **nested TFs**; Phase 2’s 5m
  bias pairing is not automatically the Spec A OTE execution TF, though 5m appears
  in both.

---

## Q4 — Do TTrades and 2022 teach the same bias/entry relationship?

### Verdict: **They differ — not merely vocabulary**

| Aspect | TTrades (bias + supplement + CISD) | 2022 mentorship (Spec A) |
|---|---|---|
| Daily bias | Mechanical: PDH/PDL/EQ + sweep + **CISD** + EQ-respect + SMT | No mechanical daily bias in scanned episodes; midnight / power-3 / dealing range |
| Confirmation term | **CISD** only | **MSS** only (in sampled transcripts) |
| Entry | CISD/OB retest; candle 2/3; EQ/FVG as **targets** | **MSS → FVG → OTE 62–79%** as **entry** |
| Bias vs entry | Separated by **timeframe and purpose** (confirm wick vs execute body/OTE) | Setup chain is **one trade pattern**; bias is **external filter** |
| Stop anchor | Manipulation sweep extreme (@532) | Swept extreme or FVG candle (Spec A decided) |

**Conclusion:** Building bias from TTrades and setup from 2022 is **legitimate**
(per operator 2026-06-02 mechanization precedence), but the **plug-in is not
source-isomorphic**. The ambiguity is **partly a two-corpus artifact** and **partly
real**: TTrades does not teach Spec A’s OTE flagship; 2022 does not teach TTrades’
CISD bias machine.

**Operator decision required:** Phase 3 flagship remains **Spec A (2022 MSS/FVG/OTE)**
gated by **Phase 2 (TTrades bias)**, accepting two confirmation layers — **not** a
single unified CISD chain for both.

---

## Phase 2 implementation vs findings

Current `bias_module.py` (correct for **Phase 2 scope**):

- Emits bias on **sweep → CISD → EQ-respect → (optional SMT)** on **pairing TF**
  (5m default).
- Does **not** detect MSS, FVG, or OTE.
- Does **not** produce entry signals.

**Would need to change for Phase 3 depending on operator architecture choice:**

| Finding | Phase 2 change needed? |
|---|---|
| MSS ≠ CISD | **No** for bias module. **Yes** for Phase 3 — add **MSS primitive** (swing break), do not relabel CISD. |
| Entry ≠ bias CISD | **No** — bias stays gate. Strategy must **not** treat `cisd_index` as Spec A entry confirmation. |
| Architecture C (nested TF) | **Optional** — bias module TF may stay 5m; Spec A entry may use **5m MSS/FVG/OTE** or **1m** execution variant; pre-register. |
| Same vs separate sweep leg | **Operator decision** — may require strategy parameter `entry_after_bias_only: bool` and/or minimum time separation; **not** a Phase 2 code change. |
| TTrades entry = CISD/OB not OTE | If operator chooses **TTrades-native entry** instead of Spec A, Phase 3 scope **changes** (different hypothesis — not current Spec A). |

**Stop-condition (partial):** Source **does contradict** assuming one confirmation
chain serves both bias and Spec A entry. It **does not** require reopening Phase 2
CISD validation — it requires **not conflating** Phase 2 output with Spec A’s MSS
leg.

---

## Recommended architecture for Phase 3 (for operator sign-off)

**Primary recommendation:** **Gated two-layer model (Architecture C + Spec A entry)**

1. **Layer 1 — Bias gate (Phase 2, frozen):** Emit long / short / no-clear-bias
   once per session from sweep → CISD → EQ (+ SMT tier). No entry logic.
2. **Layer 2 — Spec A setup (Phase 3, 2022 rules):** On gated sessions only, detect
   **sweep → MSS (3-bar fractal) → FVG → OTE 62–79%** in the **bias direction**,
   NY AM window, per Spec A.
3. **Same-leg vs later-leg (pre-register):**
   - **Conservative (recommended default):** Entry setup must **begin at or after**
     bias emission timestamp (bias CISD fire + EQ reclaim complete). Allows @622-style
     sub-legs without using pre-bias counter moves.
   - **Permissive variant:** Any same-session Spec A setup in bias direction — higher
     frequency; risk of pairing unrelated legs.

4. **Do not:** Use Phase 2 `cisd_fired` as MSS; use prior-day EQ-respect as OTE
   equilibrium (different constructs — dealing range EQ in Spec A is **local** to
   the displacement leg).

**Alternative (operator only):** **TTrades-unified entry** — bias CISD + OB retest /
candle 2/3 instead of Spec A OTE. That is a **different strategy** from the
pre-registered Spec A flagship; would abandon MSS/FVG/OTE pre-registration.

**Confidence in recommendation:** **Medium-high** for “two layers + MSS for entry”;
**medium** for same-leg timing default (source gap).

---

## Questions the source material cannot resolve

1. **Exact same sweep vs later sweep** when combining Phase 2 bias with Spec A entry
   — no explicit cross-reference in either corpus.
2. **Whether MSS and CISD must both fire** for a “canonical ICT” trade when merging
   teachings — not stated.
3. **2022 mechanical daily bias** — source does not provide one; Phase 2 is already
   an operator-approved TTrades proxy.
4. **Which FVG is the one** (Ep 38 @2557) when multiple gaps exist — Spec A known
   ambiguity; separate from architecture but affects Phase 3 labeling.

---

## Stop conditions — outcome

| Condition | Result |
|---|---|
| MSS and CISD distinct and we built wrong one for **Spec A entry** | **SURFACED** — Spec A needs MSS, not CISD relabel. Phase 2 bias CISD remains correct for TTrades gate. **Does not block Phase 3** if two-layer model adopted. |
| Q2 genuinely ambiguous | **SURFACED** — operator decision on same-leg vs later-leg + confirm two-layer model. |
| Phase 2 requires rework | **No** — unless operator pivots to TTrades-only entry and drops Spec A MSS/FVG/OTE. |

---

## Artifacts

- This report: `notebooks/validation/2026-06-06_wave1_track2_phase3a_architecture.md`
- Research log: Wave 1 Track 2 Phase 3a entry in `docs/research-log.md`
- Transcript evidence: `data/processed/transcripts/{8GkQfdAXZP0,Bkt8B3kLATQ,CnTXwAuDi9Y,36184dDAqtM,2XhDi5GoNUI}.json`,
  `data/processed/transcripts/cisd_smt/CHIK5oBRKiw.json`,
  `data/processed/transcripts/bias/-KKuZb5Z5aU.json`

**Reproduce excerpt pulls:** timestamp windows were extracted with ad-hoc Python
over the processed transcript JSON (same method as Phase 1 validation).
