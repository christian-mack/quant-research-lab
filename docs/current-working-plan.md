# Current Working Plan: Phase 2 Research

**Plan type:** Batch-oriented research units (not week-by-week Phase 1 milestones)
**Phase:** **2 — Flux V2** — configuration and pattern discovery vs frozen **ORB+Opt3** baseline
**Status:** **H-W4-7** Session 3 complete (2026-08-18): clean-SHA repro + cells A–C; pulse not met. No kill/promote this session.
**Last updated:** August 18, 2026 — H-W4-7 Session 3 (N=15 ledger; family dead at fixed-bracket pulse; no verdict). Wave 0 / Wave 1 sections reconciled against `docs/research-log.md` during repo cleanup.
**Next review:** After each hypothesis batch / validation cycle (or at least weekly for parallel tracks)
**Related documents:** `docs/phase-2-kickoff.md`, `docs/orb_opt3_phase2_closeout.md`, `docs/research-log.md`, `docs/program-charter.md`, `docs/phase-1-detailed-plan.md`, `docs/ai-project-instructions.md`, `docs/lessons-log.md`

---

## Purpose of this document

Tactical plan for **Phase 2**: what research batch is active, what gates apply, and what runs in parallel with R&D. Phase 1 week-by-week tasks are **archived in git history**; this document is the single place for **current** Phase 2 scope.

Update when a batch completes, when hypotheses are pre-registered, or when parallel-track status materially changes.

---

## Phase 2 success criteria (reminder)

**Operational (post–Wave 0h):** At least **one** strategy configuration passes **joint gates** (**funded survival** + **block bootstrap ≥ 80%** + **eval ≥ 50%** on the pre-registered rolling-window spec) **and** **average funded P&L ≥ $36K/yr** (floor tier) at the sized quantity on the six-year MNQ protocol, under the relevant Apex PA class rules — see `docs/phase-2-kickoff.md`. **Target / stretch** tiers ($60K / $100K) and charter **$65K–$100K** net per account remain north-star goals.

**Reference floor:** **Wave 0** graded **ORB+Opt3** (**Waves 0c–0h**) clears **none** of the joint gates at meaningful economics, and the 2026-06-08 account-class survey found **no** class ($50K / $100K / $150K) clearing **$36K/yr net + eval ≥ 50%**. Replacement strategies should beat that implicit "do nothing new" outcome.

**Open doc conflict (operator):** `docs/program-charter.md` still frames Phase 2 exit as **≥ X% improvement vs ORB+Opt3**. That predates the Wave 0h reframe and should be aligned with the joint-gate definition above on the next charter edit (flagged in lessons log **2026-05-17**, Wave 0h). Not edited here — charter changes require operator sign-off.

---

## Active work: batch-oriented units

Research proceeds in **batches**, not calendar weeks. A typical batch includes:

| Unit | Description |
|------|-------------|
| **Hypothesis batch** | 3–10 related ideas pre-registered; shared data slice and protocol; single comparison-correction context where possible. |
| **Pattern discovery round** | Exploration allowed only within a **scoped question**; promotes survivors to named hypotheses for pre-registration. |
| **Validation cycle** | IS/OOS, deflated Sharpe, bootstrap CIs, walk-forward on candidates that clear the discovery bar; integration/displacement tests when multiple levers interact. |

**Batch / wave naming:** Use **`docs/research-log.md`** for hypothesis ids; reference waves in lessons log when needed (e.g. `P2-W01-wave0-baseline`).

---

## Wave 0 (complete): Graded ORB+Opt3 baseline + chapter close-out

**Goal:** Establish the **graded** ORB+Opt3 anchor under **tiered PA** rules and document **joint-gate** failure modes; **close** the Phase 2 repair thread.

**Tasks:**

- [x] Re-run **ORB+Opt3** at **computed max sustainable qty** using **R(q)** and default **linear DD(q) ≈ q × DD(1)**. Result: **q_max = 0** under the original R(q) ceiling (research-log 2026-05-14).
- [x] Re-baseline under **corrected** Apex $50K EOD rules — **$2,000** pre-lock trail, **$52K** lock, **$50K** post-lock floor, **$3K** target, **$1K** DLL (**Waves 0c–0d**; the earlier **$3K** trail figure is superseded per lessons log 2026-05-16).
- [x] **Waves 0e–0g:** tiered PA / DLL simulator, bootstrap diagnosis, failure profile, and 2020-exclusion re-grade — **no** funded survival at surveyed sizes; excluding 2020 does not restore it.
- [x] **Wave 0h (2026-05-17):** per-session loss tail vs TDD; **`docs/orb_opt3_phase2_closeout.md`**; kickoff + working-plan reframe to **new-strategy search**.

**Wave 0 exit:** **Complete.** ORB+Opt3 is a **frozen research reference** and the **live production** placeholder until a replacement clears gates — not the object of Phase 2 repair.

---

## Wave 1 (complete): First non-ORB hypothesis batch — Track 1 quant + Track 2 ICT

**Goal:** Establish operating rhythm and run a **first pre-registered set** of **non-ORB** investigations.

**Track 1 / 1b (quant) — RESULT-LOGGED:**

- [x] **Track 1** (N=7: H1, H2, H8–H12) pre-registered 2026-05-26 and screened — **0 survivors** of the five Stage-1 gates. **H11** is the best near-miss (passes G2–G5, dies on G1 session tail).
- [x] **Track 1b:** **H8b** MES–MNQ divergence screened 2026-05-29 — **KILLED** (strongly negative; fails G1, G3, G4, G5).
- [ ] **H9 / H10 — BLOCKED:** no `RTY *.Last.txt` or `ES *.Last.txt` under `data/raw/`. Unblocked only by an operator export.

**Track 2 (ICT) — RESULT-LOGGED:**

- [x] **Phase 1 (2026-06-04):** five unit-tested ICT primitives + MYM data prep; three-instrument SMT (MNQ/MES/MYM) confirmed viable.
- [x] **Phase 2 (2026-06-05):** daily **bias module** — **no-clear-bias 75.5%** of 1,561 sessions (stand-down on ~3/4 of days). Binding filters are CISD + EQ-respect; SMT requirement halves frequency.
- [x] **Phase 3a → step 3d (2026-06-06 → 06-07):** MSS primitive, standalone OTE assembly, entry-coherence forensic, coherent rebuilds, exit-structure test. **OTE closed definitively** — no persistent account-viable edge independent of exit structure; best combo still fails Apex tier-1 DLL.

**Cross-track infrastructure — RESULT-LOGGED:**

- [x] Geometry guard engine-wide; **V1–V6** harness mandatory (lessons log 2026-06-07), then **V7** engine-provenance guard (2026-06-08) closing the script-local fill bypass class.

**Wave 1 exit:** **Complete, no survivors.** Every Track 1/1b hypothesis and the entire OTE chain are closed negative on the trusted M4 path. Remaining live threads are the **RTY/ES data block** (H9/H10) and the **MES parallel discovery surface** (running MNQ N tracked in `docs/research-log.md`; MES N started at 0).

---

## Parallel tracks (ongoing)

These run **alongside** Phase 2 research unless charter stop-conditions trigger:

| Track | Owner | Notes |
|-------|--------|--------|
| **PT1 — Live Flux V1** | Operator | ORB+Opt3 production monitoring; integrity; journaling anomalies vs backtest. |
| **PT2 — Eval sampling** | Operator | Continue building pass-rate sample toward statistical usefulness (charter parallel track). |
| **PT3 — Documentation / methodology** | Implementation agent | Keep NT8 methodology and Python parity docs current when protocol changes. |
| **PT4 — Phase 1b readiness** | Operator / future | Sierra (or alternative) **starts only after** Phase 1b entry criteria; no port work required for Phase 2 R&D. |
| **PT5 — Research tooling** | Implementation agent | Bugfixes and small enhancements to stats/backtest stack as Phase 2 exposes needs. |

---

## Near-future waves (placeholders)

Executed naming in `docs/research-log.md` supersedes these labels where they conflict:

- **P2-W2 / P2-W3:** RESULT-LOGGED 2026-06-08 on `main` (closed negative on M4).
- **Wave 4 (H-W4-7):** Session 3 (2026-08-18) — clean-clone primary **reproduced** Session 1 (6410 / 50.5% / $1,358.70 / DD $6,769.84). DSR at committed **N=15**. Cells A–C **fail** pre-specified pulse (PF ≥ 1.10 AND 4/7 years+). No R:R / ATR / block-subset follow-up this session. Kill/promote **not issued**.

Placeholders only for anything still TBD:

- Walk-forward / integration on a survivor — gated on an operator promote, none this session.

Rename or split as needed; document changes in **`docs/research-log.md`** and **`docs/lessons-log.md`**.

---

## Risks (Phase 2)

| Risk | Watch for | Response |
|------|-----------|----------|
| Overfitting across many ideas | Many “looks good” OOS without correction | Enforce pre-registration + DSR/deflated Sharpe across batch size; log all tries. |
| Ignoring trade count | Pretty equity, <80 trades/yr or prop-incompatible cadence | Explicit frequency constraints in kickoff; score candidates on trades/year and DD-window simulation where feasible. |
| Scope creep into execution | Rewriting live before research gates | Phase 1b sequencing per charter; Python remains spec until side-by-side validation. |
| Operator overload | Live + eval + research | Batch size caps; pause discovery if PT1 demands spike (charter operational principles). |

---

## Working plan discipline

- **Per wave:** Pre-register in **`docs/research-log.md`** → run → update status; deflated Sharpe with **N** = hypotheses in that wave.
- **Ad hoc:** Charter-level decisions and surprises → **`docs/lessons-log.md`** (append-only).
- **Agent sessions:** Follow **`docs/ai-project-instructions.md`**; new chats start with kickoff + charter + lessons log + **`docs/research-log.md`** (recent waves).
