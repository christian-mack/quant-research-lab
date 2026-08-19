# ORB+Opt3 — Phase 2 repair chapter close-out

**Date:** 2026-05-17  
**Scope:** Documentation wave (**Wave 0h**). No strategy or simulator changes.  
**Artifacts:** `notebooks/validation/2026-05-17_wave0h_orb_opt3_chapter_closeout.{md,json}`, `docs/research-log.md` (Wave 0h), `docs/lessons-log.md`.

---

## One-paragraph arc (Waves 0a–0h)

**0a–0c** moved research onto the two-phase Apex EOD rule set (pre-lock trailing, lock, post-lock floor, DLL semantics) and separated **funded survival** from **eval** rolling-window behavior. **0d** corrected PA tier caps and DLL modeling. **0e** showed **no funded survival** on the tier-ceiling-and-above MNQ sweep under those rules. **0f** profiled failures: **single-session, pre-lock** breaches concentrated in **2020** on the high-qty grid, while a **low-qty sweep** restored **funded** survival in some classes but **never** cleared the **joint** gate (bootstrap bound). **0g** confirmed **2020** bar integrity for this protocol, characterized the **two** early-Jan-2020 breach sessions, and proved that **dropping 2020 trades** still yields **zero funded survival** across the combined grid — fragility is **not** “only COVID.” **0h** (this document) quantifies the **per-session loss tail at MNQ = 1** vs class **TDD**, records the **operator decision** to **close ORB+Opt3 repair** inside Phase 2, and reframes **Phase 2** work as **new-strategy search** under `docs/program-charter.md` (acceptable outcomes include other approaches discovered during research).

---

## Final answer

**ORB+Opt3 is not a viable Phase 2 *repair* candidate under Apex EOD pre-lock dynamics at the configurations tested** (tiered PA, joint gates: funded + block-bootstrap ≥ 80% + eval ≥ 50%, economics floor per kickoff). **Fragility is structural** in the sense that **no tested sizing/account-class path** clears the **joint** bar, and **excluding 2020** does not restore **funded** survival. The live production strategy may still be **ORB+Opt3** on a funded account; **research** on fixing that specific footprint **within Phase 2** is **closed** by operator decision.

---

## Structural reason (tail vs buffer) — with numbers

Diagnostics use the **six-year** ORB+Opt3 trade log at **qty = 1 MNQ**, **aggregated by `exit_ny_date`** (sum of `net_pnl`; **15** NY dates have **>1** closed trade in-window, max **6** trades on one NY day).

| Metric (losing sessions, MNQ=1) | Value |
|---------------------------------|------:|
| Losing session count | 272 |
| Median session P&amp;L | −$136.50 |
| Median \|loss\| | $136.50 |
| 75th / 90th / 95th percentile \|loss\| | $160 / $160 / $160 |
| 99th percentile \|loss\| | **~$520** |
| Worst single session | **−$789.50** |
| Tail multiple (99th \|loss\| / median \|loss\|) | ~**3.8×** |

**Pre-lock margin vs class TDD (Wave 0e–0g convention):** trailing margin to the **moving** floor equals **TDD** whenever equity and high-water are equal (including at open and just below the lock threshold). **Eval profit target** (`profit_target_usd`) is a **separate** dollar objective, not the trailing cushion.

At **MNQ = 1**, the **99th percentile** absolute session loss (~**$520**) is **~26%** of **$50K** TDD ($2,000) and **~52%** of **$25K** TDD ($1,000) — i.e. **mild relative to $50K TDD** but **not** relative to the smallest class. **Linear scaling** with qty implies, for example, **~$5,198** p99 session loss at **10 MNQ**, i.e. **~260%** of **$50K** TDD — consistent with **pre-lock breach** narratives at production-scale quantities without requiring an extreme p99 at unit scale.

**Back-of-envelope stop narrowing (linear model,** does **not** model WR **):** To force p99 \|loss\| ≤ **50% TDD** at MNQ=1, **$25K** needs only a **~3.8%** proportional tightening (p99 slightly above $500 today); **$50K+** classes need **no** tightening on that percentile cap at qty=1. This **does not** override the joint-gate evidence: **stop distance** changes were **not** explored as a full research branch; operator closed **ORB+Opt3 repair** regardless.

---

## What was ruled out (within tested scope)

| Lever | Outcome |
|--------|---------|
| **Sizing alone** | Low qty can **fund** in places (**Wave 0f**) but **bootstrap / eval** still fail joint thresholds; **high qty** fails **funded** first (**0e**). |
| **2020 exclusion** | **0/40** funded on remainder of path (**0g**). |
| **Account class change** | Sweep across **25k / 50k / 100k / 150k** in **0e/0f** did not produce a **joint** pass at economics of interest. |

---

## Not explored in Phase 2 ORB repair (available later)

Still **in charter Phase 2 scope** but **out of this closed repair thread**: **stop distance / risk clamp** redesign, **entry–exit logic** changes, other **filters** or **modules**. **Regime overlay** remains **Phase 3–oriented** per prior discipline. **Adaptive pre-lock sizing** is technically in scope; operator deemed it **operationally non-viable** in discussion referenced by **Wave 0g**. None of these are pre-committed; they are **candidate levers for *new* strategies** or future revisits.

---

## Production status

**ORB+Opt3 remains the live Flux V1 strategy** on the current funded Apex account until a **replacement** is validated and migrated. **Phase 2 research** no longer treats **“fix ORB+Opt3”** as the primary objective; it treats **ORB+Opt3** as a **graded reference** (implicit **$0** joint-pass economics vs floor **tiers**) while **searching for a new approach** that can meet **Phase 2 success criteria** (see updated `docs/phase-2-kickoff.md`).

---

## Pre-registered STOP surface (Wave 0h)

If the **99th percentile** absolute session loss at **MNQ=1** were **≤ half of $50K TDD** ($1,000), the wave flags that **unit-scale tail percentiles** are **not** extreme vs that buffer — **repair might deserve another look on stop distance alone** before a hard close-out. **This run:** p99 ~**$520** **< $1,000** → condition **fires** for the **$50K** reference. **Reconciliation:** unit tail is **moderate**; **failure at scale** is driven by **qty × session loss**, **path sequencing**, and **robustness gates**, not by p99 MNQ=1 loss alone. **Operator still closes** ORB repair; this nuance is **for the record** and for **Wave 1** screening on **new** ideas.

---

## Wave 1 operator agenda

Open questions for the next strategy session (not answered here) are listed under `deliverable_4_wave1_operator_agenda` in  
`notebooks/validation/2026-05-17_wave0h_orb_opt3_chapter_closeout.json`.
