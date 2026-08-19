# Wave 1 Track 2 — Phase 3 Step 0: Spec A Precise Definitions

**Date:** 2026-06-06  
**Wave:** Wave 1, Track 2 — Phase 3 step 0 (source extraction only; no strategy code)  
**Purpose:** Resolve six load-bearing underspecifications in Spec A before standalone OTE
strategy assembly (Phase 3 step 2). Operator context: test OTE entry **standalone**
(self-contained sweep → MSS → FVG → OTE) and bias module standalone, then analyze overlap.

**Sources:** 2022 mentorship processed transcripts — Ep 6 (`Bkt8B3kLATQ`), Ep 12
(`8GkQfdAXZP0`), Ep 25 (`CnTXwAuDi9Y`), Ep 38 (`36184dDAqtM`), Ep 41 (`2XhDi5GoNUI`);
`docs/ict/spec_a_liquidity_sweep_reversal.md`; Phase 3a architecture diagnostic.

**Method:** Passages extracted from auto-generated YouTube captions at cited timestamps
(±25 s window). Mechanical defaults proposed where source is silent (`[MANUAL OBS]`).

**Stop-condition check (D0.1, D0.3, D0.6):** All three received **provisional mechanical
defaults** grounded in transcript geometry. **Proceed to Phase 3 step 1 (MSS primitive).**

---

## Summary table

| ID | Topic | Source clarity | Provisional default | Flag |
|---|---|---|---|---|
| **D0.1** | OTE reference leg | **Moderate** — Ep 38/41 anchor fib to displacement leg low→high | Displacement leg endpoints (manipulation extreme → MSS-leg extreme) | — |
| **D0.2** | Entry FVG selection | **Low** — Ep 38 flags ambiguity explicitly | First FVG in displacement leg on correct PD side; tie-break nearest 70.5% OTE | `[MANUAL OBS]` tie-break |
| **D0.3** | Displacement extreme | **Moderate** — Ep 6/25 define leg ends at MSS confirmation | Running leg extreme at MSS bar close, sweep-anchored window | — |
| **D0.4** | MSS swing lookback | **Silent** — no numeric bound in corpus | Manipulation-leg bounded: sweep close-back → MSS bar | `[MANUAL OBS]` |
| **D0.5** | Stop tick buffer | **Moderate** — Ep 25 gives 1–2 ticks; Ep 38 swept extreme | 1 tick beyond reference (2-tick variant pre-registered) | `[MANUAL OBS]` swept arm |
| **D0.6** | Target rule | **Moderate** — opposing liquidity pools named; hierarchy implicit | Nearest unbroken opposing liquidity pool (fractal swing + PDH/PDL) | `[MANUAL OBS]` pool ranking |

---

## D0.1 — OTE reference leg (62–79% retracement of what?)

### Source passages

**Ep 38 @2566–2573s (OTE fib anchor, worked example):**

> "a lot of you know how to use optimal trade entry — you'll use **the low here to the
> high** pull your fib up **62 to 79** level if it goes down to that then you'll buy it"

**Ep 38 @2588–2592s (alternate flagship entry, same leg):**

> "or you can just do this — **low high** find the fair value gap below 50 level which is
> a discount"

**Ep 41 @1120–1127s (flagship OTE, equilibrium framing):**

> "optimal trade entry in other words that would be a **62 to 70 retracement** level less
> than equilibrium **relative to the high and the low respectively**"

**Ep 25 @2189–2191s (displacement leg fib):**

> "showing you how you're going to put your **fib on the high and the low of that**
> [displacement price swing]"

**Ep 6 @1207–1215s (bearish displacement leg endpoints):**

> "when we create that high … **high down to the low that breaks the short-term low** …
> **that is the displacement low** … **this is your displacement high**"

**Ep 38 @1307–1310s (dealing range = MSS swing low → swing high):**

> "market structure **swing low here to swing high** that's my **dealing range**"

### Interpretation

The OTE fib is **not** anchored sweep-extreme → displacement-extreme as two independent
candidate legs. The source consistently anchors to the **displacement / dealing-range leg**
formed by the post-sweep MSS move:

- **Bullish:** manipulation **low** (swept area low) → displacement **high** (MSS-leg high).
- **Bearish:** displacement **high** (run above liquidity) → displacement **low** (MSS break low).

The sweep extreme is typically the manipulation-endpoint of that same leg, not a separate
fib anchor.

### Proposed mechanical default

**OTE reference leg = displacement leg endpoints (D0.3), direction-aware:**

| Direction | Fib 0% (start) | Fib 100% (end) |
|---|---|---|
| Long (bullish MSS) | `displacement_low` | `displacement_high` |
| Short (bearish MSS) | `displacement_high` | `displacement_low` |

Limit entry at **70.5%** retracement into that leg (operator-canonicalized band 62–79%).

**Confidence:** Moderate. Multiple episodes converge on low→high of the MSS displacement
leg; not sweep-extreme → displacement-extreme as separate anchors.

---

## D0.2 — Which FVG is the entry array?

### Source passages

**Ep 38 @2557–2561s (explicit ambiguity):**

> "these fair value gaps are all over the place **how do i know which one is the one i
> want to use**"

**Ep 38 @2590–2593s (discount FVG selection rule):**

> "find the **fair value gap below 50 level** which is a discount as soon as it trades at
> the **top level of it**, buy it there"

**Ep 41 @1097–1099s (single FVG in worked example):**

> "that's the **fair value gap we're going to be using** here"

**Ep 6 @1230–1232s (FVG forms inside displacement range):**

> "what you have in between that range … you're gonna be hunting your **fair value gaps**
> because that's exactly where it's going to form"

**Ep 38 @2566–2573s (OTE pattern coexists with FVG pattern — two entry styles):**

> OTE fib entry and FVG-top touch entry presented as **alternatives** on the same setup.

### Interpretation

Source acknowledges ambiguity when multiple FVGs exist. Actionable rules:

1. FVG must lie on the **correct PD side** of the displacement dealing range (discount for
   longs, premium for shorts) — Ep 38 @2590.
2. FVG must fall **within the displacement leg** (Ep 6 @1230).
3. No mechanical rule for choosing among multiple qualifying FVGs.

### Proposed mechanical default

**`[MANUAL OBS]`** — provisional two-step filter:

1. **Eligible set:** bullish/bearish FVGs with `c2_index` in
   `[displacement.start_index, displacement.end_index]` whose midpoint lies on the correct
   side of dealing-range equilibrium (50% of D0.1 leg).
2. **Selection:** take the **earliest** eligible FVG (first formed after MSS, causal). If
   multiple share the same `c2_index` window, take the one whose **top** (long) or **bottom**
   (short) is **nearest the 70.5% OTE price** on the D0.1 leg.

Pre-register sensitivity: earliest-FVG vs nearest-OTE tie-break.

**Confidence:** Low on tie-break; moderate on PD-side + in-leg filter.

---

## D0.3 — Displacement extreme (100% retracement anchor)

### Source passages

**Ep 6 @1213–1215s (bearish, at MSS break):**

> "below that low — **that is the displacement low** … **this is your displacement high**"

**Ep 6 @1267–1272s (bearish, leg definition):**

> "**that short term low being broken** … that's your **displacement low** and **the high is
> your displacement height** … that range between here and here that's **displacement**"

**Ep 25 @2235–2236s (judas swing = displacement price leg):**

> "nonetheless this is the **displacement price leg** … this price swing here you shade that"

**Ep 25 @2171–2173s:**

> "that … is your **displacement** price swing"

**Ep 6 @1156–1159s (energetic close required):**

> "the term **displacement** … it's got to be **energetic** … preferably **close** below"

### Interpretation

Displacement leg endpoints are defined **at MSS confirmation**:

- Bearish: high of the run above liquidity → low of the MSS break (close below opposing
  swing).
- Bullish: low of the sweep/manipulation → high of the MSS break (close above opposing swing).

The leg is the **shaded price swing** from manipulation through MSS; extremes are the
running max high / min low over that window, finalized at MSS bar close (no future bars).

### Proposed mechanical default

At MSS fire bar `t` (close confirms swing break), with sweep penetration at `p` and sweep
close-back at `c` ( `p ≤ c < t` ):

| Field | Bullish MSS | Bearish MSS |
|---|---|---|
| Window | `[p, t]` inclusive | `[p, t]` inclusive |
| `displacement_low` | `min(low[p:t+1])` | `min(low[p:t+1])` — equals MSS break low |
| `displacement_high` | `max(high[p:t+1])` | `max(high[p:t+1])` — equals pre-break run high |
| `start_index` | `p` (sweep penetration bar) | `p` |
| `end_index` | `t` | `t` |

Known in real time at bar `t` close; no look-ahead.

**Confidence:** Moderate. Matches Ep 6/25 leg shading and Phase 3a causal requirement.

---

## D0.4 — MSS swing lookback ("most recent opposing short-term swing")

### Source passages

**Ep 6 @1401–1432s (bullish MSS criteria):**

> "takes out a **short term high** … and it **closes above it** with an energetic
> displacement higher"

**Ep 12 @2244–2247s (MSS = short-term low broken):**

> "you have to look for what the **short-term low being broken** — that's your Market
> structure shift"

**Ep 6 @1569–1571s (8:30 example — discretionary swing pick):**

> "what's the **first swing** … how you come to right there — was that complicated? **no**
> very simple"

**Ep 6 @1258–1263s (bearish — swing low *prior to* run above):**

> "takes out a **short term low** **prior to that run above**"

**Spec A default:** 3-bar fractal for short-term swing. **No bar-count or session bound**
stated in 2022 corpus.

### Interpretation

"MSS swing" is a **3-bar fractal** (per Spec A), but lookback depth is **not quantified**.
Ep 6 ties the broken swing to the **manipulation leg** ("prior to that run above"), not an
unbounded session history.

### Proposed mechanical default

**`[MANUAL OBS]`**

- **Swing type:** 3-bar fractal (center bar strictly higher/lower than neighbors).
- **Lookback window:** `[max(0, sweep_penetration_index − max_fallback_bars),
  mss_candidate_index)` — includes swings **prior to** the manipulation run (Ep 6 @1261
  "prior to that run above") through the MSS candidate bar.
- **"Most recent":** highest-index confirmed fractal center in that window.
- **Fallback** if no fractal in window: extend backward to session start, then cap at
  **100 bars** (≈8.3 h on 5m) to prevent unbounded search.

Used by `mss.py` step 1 implementation.

**Confidence:** Low on numeric fallback; moderate on manipulation-leg bounding (Ep 6
"narrative anchoring").

---

## D0.5 — Stop tick buffer (A/B arms)

### Source passages

**Ep 25 @2617–2623s (FVG-creating candle arm):**

> "you want to use the candle that **creates the fair value gap** … **just above that** okay
> **one tick two ticks above that** that's sufficient enough"

**Ep 6 @1054–1059s (FVG 3-candle pattern arm):**

> "place your stop … **right above candle number one** or you can put it **above candle
> number two**"

**Ep 38 @2596–2599s (swept-extreme / manipulation low arm):**

> "buy it there **stop below the lower low** or level here"

**Ep 6 @2152s (generic buffer):**

> "**one tick maybe two ticks** whatever"

**Ep 38 @2621–2626s (buy-stop entry variant — post-touch low):**

> "whatever the **lowest low is after it hits** that … that's where your stop loss would be
> **just right below that**"

### Interpretation

Two structural stop arms per Spec A:

| Arm | Reference | Source buffer |
|---|---|---|
| **A — Swept extreme** | Manipulation/swept swing extreme | "below the lower low" — no tick count; structural |
| **B — FVG candle** | High/low of middle (c2) FVG candle | **1–2 ticks** beyond c2 extreme (Ep 25 explicit) |

Ep 6 allows c1 or c2 for the FVG pattern; Spec A already decided **c2 (FVG-creating
candle)** as tightening arm.

### Proposed mechanical default

**`[MANUAL OBS]`** on swept arm tick precision.

| Arm | Long stop (below) | Short stop (above) |
|---|---|---|
| **A — Swept extreme** | `swept_low − 1 tick` | `swept_high + 1 tick` |
| **B — FVG c2** | `c2_low − 1 tick` (default) or `− 2 ticks` (pre-reg variant) | `c2_high + 1 tick` |

Primary backtest arm: **A (swept extreme)** per Spec A; grade **B** separately at its own
sustainable qty.

**Confidence:** Moderate on FVG arm (1–2 ticks); low on exact swept-arm tick (source says
"below the lower low" without tick math).

---

## D0.6 — Target rule (opposing liquidity pool)

### Source passages

**Ep 41 @1011–1026s (flagship long — multiple draw objectives):**

> "expect price to reach for **here and here** … objectives … **this imbalance here** …
> **buy side liquidity here** … **sell side liquidity here**"

**Ep 41 @1163–1195s (worked trade — draw on liquidity):**

> "what would be the **draw on liquidity** … we want to get to a **premium level** … the
> **first low hanging fruit objective** would be **this candle's high** … risking nine
> points to make **25 and a half**"

**Ep 41 @1034–1039s (far target):**

> "run from here **to the short term high** … runs here up into the **3805 level**"

**Ep 6 @2308–2316s (layered targets, short):**

> "there's your **first target** … equal lows … **sell stops** … taking profits **here
> and or here**"

**Ep 6 @2506–2508s (full target = intermediate swing taken out):**

> "it's taken out here but it's also a **full target** for selling short up here"

**Ep 6 @2729–2749s (internal vs external range liquidity):**

> "that's your **target** going short … **internal range liquidity** … **stops below these
> lows** … **external range liquidity**"

**Ep 38 @1328–1330s (session-external pool):**

> "consolidate and then **run for previous days high**"

**Ep 12 @2788–2791s (far target vs risk):**

> "expanding lower for a **Target that's many times over** what your risk is"

### Interpretation

ICT targets are **opposing liquidity pools** — resting stops beyond swings, imbalances, and
session reference levels — not a fixed R:R cap. Hierarchy in worked examples:

1. **Nearest internal** pool (imbalance fill, short-term swing, candle high/low).
2. **External** pool (equal highs/lows, PDH/PDL, larger swing).

For backtest **full-target** simulation (operator removed R:R ceiling), need one mechanical
rule.

### Proposed mechanical default

**`[MANUAL OBS]`** pool-ranking — provisional:

**Full exit target = nearest unbroken opposing liquidity pool** in trade direction, selected
from (in priority order for tie-breaking):

1. **Opposing 3-bar fractal swing** (buy-side above entry for longs; sell-side below for
   shorts) formed before entry, not yet traded through.
2. **PDH** (long target) or **PDL** (short target) if not yet swept this session.
3. **Next fractal swing** on higher lookback (up to session start).

**Nearest** = minimum price distance from entry. Partial targets (Ep 6 "here and or here")
are **not** simulated in Stage-1 standalone OTE — full target only for primary metric;
flag partials for Phase 4 labeling.

**Confidence:** Moderate on "opposing liquidity" concept; low on strict pool-ranking order.

---

## Step 0 exit decision

| Load-bearing item | Resolvable? | Action |
|---|---|---|
| D0.1 OTE leg | **Yes** — displacement leg endpoints | Proceed |
| D0.3 Displacement extreme | **Yes** — sweep-anchored running extreme at MSS | Proceed |
| D0.6 Target | **Yes** — nearest opposing pool (fractal + PDH/PDL) | Proceed |
| D0.2, D0.4, D0.5 | Provisional `[MANUAL OBS]` | Proceed with flags |

**Operator review:** Defaults are reasonable for step 1 MSS build. D0.2 FVG tie-break and
D0.6 pool-ranking are the weakest links — pre-register variants if sensitivity matters.

---

## Artifacts

- This report: `notebooks/validation/2026-06-06_wave1_track2_phase3_step0_definitions.md`
- Phase 3a context: `notebooks/validation/2026-06-06_wave1_track2_phase3a_architecture.md`
- Spec A: `docs/ict/spec_a_liquidity_sweep_reversal.md`
