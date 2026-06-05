# Spec A — 2022 Liquidity-Sweep Reversal (flagship)

**Status:** REVIEW-READY for strategy chat. Canonical fields cite real episode
timestamps; transcript scan (Ep 6/12/17/25/38/41) resolved stop, session, entry,
and displacement. Decisions made: OTE band, stop A/B, session, target (no cap).
One load-bearing open item remains — **bias mechanization** (strategy-chat
decision) — plus Phase C `[MANUAL OBS]` placeholders before Cursor implementation.

**Absorbs:** old H4 (liquidity sweep), H13 (judas), H5-OTE. Session window is a
*parameter* of this one setup, not a separate hypothesis.

---

**Concept name:** Liquidity-sweep reversal (sweep → MSS → displacement → PD array → OTE)

**ICT terminology:** liquidity raid / stop run / judas swing (manipulation,
"protraction"); market structure shift (MSS); displacement; fair value gap (FVG);
order block (OB); optimal trade entry (OTE); dealing range; premium/discount;
equilibrium. Ep 41 names FVG + OB + OTE "the gold standard of the ICT pattern."

**Source citations (2022 mentorship):**
- Judas / manipulation: Ep 17 @489s ("attack the liquidity below… rally first,
  that's the judas swing… mark of protraction"); Ep 25 @1971s, @2259s
  ("9:30 is this candle… judas swing, at 8:30 it starts its run"); Ep 30 @34s.
- MSS: Ep 12 @2247s ("short-term low being broken, that's your market structure
  shift, then price goes up into that imbalance, then go short or vice versa");
  Ep 6 @1110s, @1416s; Ep 25 @2006s.
- Sweep / stop run (session-anchored): Ep 38 @846s, @1231s, @1346s
  ("sweep to sell stops below some short-term low… then rally"); Ep 41 @447s
  ("stop run in the lunch hour").
- OTE: Ep 41 @1000s, @1120s ("62 to 70 retracement, less than equilibrium");
  Ep 38 @1982s, @2557s.
- Dealing range / equilibrium: Ep 32 @341s ("from this high down to that low…
  measure those"); Ep 38 @1310s, @2743s ("fib across it, 50%"); Ep 33 @873s.

**Underlying market behavior (plain language):** Early in a session, price makes a
false move that raids an obvious liquidity pool (stops beyond a recent swing
high/low), then reverses in the direction of the higher-timeframe bias. The
reversal is confirmed by a break of short-term structure (MSS) with a strong
displacement leg that leaves an imbalance (FVG). Entry is on the retrace into that
FVG/order block, in the discount (for longs) or premium (for shorts) half of the
local dealing range.

**Trigger condition (setup forms when):**
1. HTF directional bias established. `[DEFAULT]` daily/4H bias = price's position
   relative to prior-day range + most recent HTF dealing-range equilibrium.
   `[MANUAL OBS]` ICT's bias call is discretionary; needs a mechanical proxy.
2. Within the session window, price sweeps a reference liquidity level *against*
   bias (the judas/protraction leg). `[DEFAULT]` sweep = trade through prior
   session high/low OR most recent short-term swing by ≥ `[MANUAL OBS]` ticks,
   then close back inside within N bars.
3. MSS in bias direction: break of the most recent opposing short-term swing.
   `[DEFAULT]` short-term swing = 3-bar fractal; `[DECIDE]` lookback for "recent."

**Entry condition:** SPECIFIED. Limit into the FVG left by the displacement leg,
taken when that gap sits in discount (longs) / premium (shorts): "find the fair
value gap below 50 level which is a discount, as soon as it trades at the top
level of it, buy it there" (Ep 38 @2587s, @2616s; Ep 41 @985s, @1110s "down-close
candle… bullish order block… optimal trade entry — the flagship pattern").
- **OTE band — DECIDED: 62–79%, limit at 70.5%** (classic optimal). Source was
  inconsistent (62–70 / 62–79 / 40–70); operator canonicalized 62–79%. One
  pre-registered variant only: entry-within-band — 70.5% limit (primary, deeper
  fill / higher R) vs 62% first-touch (more fills / lower R). Do NOT sweep band
  width; that inflates deflated-Sharpe N for no structural reason.
- Array must sit on the correct side of equilibrium: longs discount (<50% of
  dealing range), shorts premium (>50%). Ep 41/38.

**Stop placement:** DECIDED — A/B, **swept extreme primary, FVG-creating candle as
the tightening arm.** Swept extreme = wider stop ("stop below the lower low",
Ep 38 @2587s); FVG candle = tighter ("one tick, two ticks" above/below it, Ep 25
@2612s/@2533s, Ep 6 @1048s). Structural, not fixed; observed ~5–9 NQ points (Ep 41
@2554s/@2567s). **Grading note:** the wider swept-extreme stop yields a *smaller*
max sustainable qty under `R(q)` than the FVG-candle arm — grade each arm at its
own sustainable qty, not a shared one. Pre-register accordingly.

**Target:** `[DECIDE]` ICT canonical = opposing liquidity pool (often >1.5R). This
**conflicts with your Stage-1 R:R ceiling of 1.5** — ICT's far target will blow
past it. Options: (a) cap at a nearer target (opposing short-term swing / FVG fill)
to fit the screen, or (b) raise/remove the R:R ceiling for this candidate.
Flagging for your decision — this is a real tension between ICT's taught exit and
your screening gate.

**Time window:** SPECIFIED by source — NY AM is well-supported. Midnight ET = daily
bias reference / "it's on New York time" (Ep 25 @1574s, Ep 17 @491s); 8:30 ET =
liquidity-run trigger, "very specific element of time," news-driven (Ep 6 @1554s,
Ep 25 @1951s "look for relative equal highs at 8:30… highs to run"); 9:30 ET =
cash-open judas/execution (Ep 38 @645s). `[DEFAULT]` canonicalize **NY AM,
08:30–11:00 ET**, midnight open as the bias anchor. NY lunch/PM (Ep 38, Ep 41) is
a separate parameter setting to test later, not a blend. All times ET; convert at
the engine boundary.

**Filter conditions (setup does NOT apply):** `[DEFAULT]` no setup if no clean
liquidity pool was swept; if MSS lacks displacement (no FVG); if the array is on
the wrong side of equilibrium. `[MANUAL OBS]` "clean" displacement vs weak — needs
labeling.

**Confirmation requirements:** sweep + close back inside; MSS; displacement.
Displacement is operationalized as **binary FVG-presence on the MSS leg** — ICT
checks "is there a gap, yes" rather than a magnitude threshold (Ep 41 @1110s). So
displacement is not a separate tunable; it = "the break left an FVG."

**Common failure modes (ICT-stated):** sweep with no reversal (continuation, not
manipulation); MSS that fails to displace; entry array overlapping the swept level
(no room for stop). Ep 38 @2557s flags the "which FVG is the one" ambiguity.

**Areas where rules are underspecified (remaining after transcript scan):**
- **Bias mechanization — OPEN INPUT for strategy chat (operator decision).** ICT's
  bias is discretionary (midnight-open reference + Power 3 narrative, no mechanical
  rule). Implementation cannot run without *some* mechanical proxy; defining it is
  a strategy-chat decision, not Phase C labeling. This is the load-bearing open
  item — flag it explicitly when sending for review.
- **Sweep depth** — confirmed *no numeric rule*; ICT teaches "just above/below" by
  example ("how far can it go" left open: Ep 25 @1951s, Ep 17 @227s). `[MANUAL OBS]`.
- **"Close back inside within N bars"** and **short-term-swing lookback** — not
  quantified by source. `[MANUAL OBS]`.
- **OTE band** and **stop convention** — `[DECIDE]` (see Entry, Stop above).

Resolved by this scan (previously open): stop placement, session window, entry
mechanics, displacement definition.

**Concrete examples:** `[MANUAL OBS]` — pending Phase C labeling (50–100 instances
on MNQ). Not fabricated here.
