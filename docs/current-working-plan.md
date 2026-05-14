# Current Working Plan: Phase 2 Research

**Plan type:** Batch-oriented research units (not week-by-week Phase 1 milestones)
**Phase:** **2 — Flux V2** — configuration and pattern discovery vs frozen **ORB+Opt3** baseline
**Status:** Phase 1 milestone gate cleared; Phase 2 execution begins after **`docs/phase-2-kickoff.md`** commit
**Last updated:** May 14, 2026 — transition from Phase 1 weekly checklist to Phase 2 batch plan
**Next review:** After each hypothesis batch / validation cycle (or at least weekly for parallel tracks)
**Related documents:** `docs/phase-2-kickoff.md`, `docs/program-charter.md`, `flux-v2-module-search-starter.md`, `docs/phase-1-detailed-plan.md`, `docs/ai-project-instructions.md`, `docs/lessons-log.md`

---

## Purpose of this document

Tactical plan for **Phase 2**: what research batch is active, what gates apply, and what runs in parallel with R&D. Phase 1 week-by-week tasks are **archived in git history**; this document is the single place for **current** Phase 2 scope.

Update when a batch completes, when hypotheses are pre-registered, or when parallel-track status materially changes.

---

## Phase 2 success criteria (reminder)

Charter-level Phase 2 exit is **≥ X% improvement vs ORB+Opt3 baseline** on agreed KPIs over the **6-year** protocol, plus statistical and (where applicable) **minimum viable edge** gates for new modules — see `docs/program-charter.md`. **Program north star** remains **per-account income** toward **$65K–$100K/yr**; see `docs/phase-2-kickoff.md` for gap framing and trade-frequency constraints.

---

## Active work: batch-oriented units

Research proceeds in **batches**, not calendar weeks. A typical batch includes:

| Unit | Description |
|------|-------------|
| **Hypothesis batch** | 3–10 related ideas pre-registered; shared data slice and protocol; single comparison-correction context where possible. |
| **Pattern discovery round** | Exploration allowed only within a **scoped question**; promotes survivors to named hypotheses for pre-registration. |
| **Validation cycle** | IS/OOS, deflated Sharpe, bootstrap CIs, walk-forward on candidates that clear the discovery bar; integration/displacement tests when multiple levers interact. |

**Batch naming:** Use a short id in lessons log entries (e.g. `P2-B001-hypothesis-batch`).

---

## Batch 1 (current): Phase 2 kickoff and initial hypothesis selection

**Goal:** Establish Phase 2 operating rhythm and a **first pre-registered set** of investigations.

**Tasks:**

- [ ] Read **`docs/phase-2-kickoff.md`** end-to-end; align operator + strategy partner on gap, methodology, and roles.
- [ ] Read **`flux-v2-module-search-starter.md`** and charter Phase 2; scrub any remaining stale “replace module X” framing in favor of **income-gap discovery**.
- [ ] Confirm **pre-registration** format and storage (hypothesis statement, primary metrics, IS/OOS rule, expected artifact paths).
- [ ] Produce **5–10** first hypotheses; **pre-register all** before running backtests that inform go/no-go.
- [ ] Define how **results** are summarized and signed off (pass/pause/kill, links to trade logs / reports).

**Batch 1 exit:** First hypothesis batch documented and pre-registered; at least one analysis **ready to execute** in the implementation agent with frozen protocol references (`docs/m6-nt8-reproduction.md`, `docs/nt8-backtest-methodology.md`).

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

## Near-future batches (placeholders)

Placeholders only — dates and scope TBD by operator after Batch 1:

- **Batch 2:** Execute first pre-registered hypothesis set; record deflated Sharpe / CI outputs; kill or promote.
- **Batch 3:** Second discovery round or deep-dive on surviving families (e.g. frequency vs magnitude tradeoffs).
- **Batch 4:** Walk-forward and integration tests on top candidate(s).

Rename or split as needed; document changes in **`docs/lessons-log.md`**.

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

- **Per batch:** Pre-register → run → document outcome in lessons log or agreed research log; link artifacts.
- **Ad hoc:** Charter-level decisions and surprises → **`docs/lessons-log.md`** (append-only).
- **Agent sessions:** Follow **`docs/ai-project-instructions.md`**; new chats start with kickoff + charter + lessons log.
