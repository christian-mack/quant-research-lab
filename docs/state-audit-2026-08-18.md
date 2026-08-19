# Project State & Open Threads Report — 2026-08-18

**Type:** Repo state audit (post-cleanup snapshot)
**Supersedes:** `docs/state-audit-2026-08-11.md` for *current* state. That document is retained
as the dated snapshot that identified the artifact backlog; its findings are historical.
**Scope:** Ground truth only. No strategy recommendations.

---

## 1. Repo ground truth

| Item | Value |
|---|---|
| Branch | `main` (only working branch) |
| HEAD | `ac95213` (before this doc's own commit) |
| Working tree | **Clean** |
| Other branches | `wip/wave0e-ict-backlog` @ `61c0a1a` — **retained deliberately**, see §5 |
| Worktrees | One (repo root). The redundant `session3/hw4-7` worktree and branch were removed. |
| Tests | **455 passed, 43 skipped, 0 failed** |
| Ruff format | Clean (176 files) |
| Ruff lint | **53 residual findings**, all deliberate — see §4 |
| Repo object count | 1,326 objects |

### Commits added in the 2026-08-18 cleanup session

| SHA | Purpose |
|---|---|
| `33cb321` | Ignore rule for bulk OTE per-trade JSON logs |
| `3bde4d5` | Land Wave 0e–0h: tiered Apex simulator, surveys, ORB closeout |
| `2d851ab` | Land Wave 1 Track 1 / 1b quant screens |
| `6a96829` | Land Wave 1 Track 2 ICT: bias module, MSS, OTE chain |
| `9813688` | Land geometry/parity guard + engine integrity artifacts |
| `1ccd3f9` | Land ORB account-class survey, repro scripts, Aug-11 audit |
| `e03e521` | Ruff import/format pass; hoist latent `polars` import |
| `f68a33f` | Reconcile working plan; drop dangling starter-doc links |
| `ac95213` | Research-log artifact-availability note |

**Unpushed:** `main` was 12 commits ahead of `origin/main` at audit time (3 pre-existing
H-W4-7 commits + 9 above). `origin/main` still points at `ae2fa83`.

---

## 2. The doc→repo divergence is closed

The Aug-11 audit's top finding was that committed docs cited artifacts absent from the
committed tree — the failure mode recorded in **lessons-log 2026-04-28**. That backlog had
since been parked on `wip/wave0e-ict-backlog`, which moved the problem rather than fixing it:
`main` still could not resolve its own citations, and 57 tests existed only on that branch.

All 16 spot-checked previously-dangling references now resolve from `HEAD`, including
`docs/orb_opt3_phase2_closeout.md`, the Wave 0e–0h validation artifacts, the Wave 1 Track 1/1b
screens, `src/quant_research/ict/{bias_module,mss,ote_strategy}.py`, and the 2026-06-08 ORB
survey. Every `` `docs/*.md` `` cross-link in `docs/` resolves to an existing file.

**Verification of the test-count gap:** 387 → **455** passed. The delta is the previously
unlanded ICT and geometry/parity/ledger test modules.

---

## 3. Open threads inventory

| Thread | Status | Evidence |
|---|---|---|
| Wave 0 graded baseline (0c–0h) | **DONE — closed negative** | `docs/orb_opt3_phase2_closeout.md`; research-log 2026-05-14 → 05-17. `q_max = 0` under original R(q); no funded survival at surveyed sizes; 2020 exclusion does not restore it |
| Wave 1 Track 1 (N=7: H1, H2, H8–H12) | **DONE — 0 survivors** | research-log 2026-05-26; `notebooks/validation/2026-05-26_wave1_stage1_track1_quant_screen.md`. H11 best near-miss (dies on G1 session tail) |
| Wave 1 Track 1b (H8b MES–MNQ) | **DONE — KILLED** | research-log 2026-05-29; fails G1/G3/G4/G5 |
| Wave 1 Track 2 ICT primitives | **DONE** | research-log 2026-06-04; five unit-tested primitives; three-instrument SMT viable |
| Wave 1 Track 2 bias module | **DONE** | research-log 2026-06-05; no-clear-bias **75.5%** of 1,561 sessions |
| Wave 1 Track 2 OTE chain (3a → 3d) | **DONE — closed definitively** | research-log 2026-06-06 → 06-07 step 3d; no account-viable edge independent of exit structure |
| P2-W2 (N=6 tight-loss-tail) | **DONE — closed negative on M4** | research-log 2026-06-08; two apparent survivors were frequency artifacts |
| P2-W3 (H-7 OR-extreme reclaim) | **DONE — closed negative on M4** | research-log 2026-06-08; entry-bar look-ahead had inflated it pre-M4 |
| V1–V7 validation harness | **DONE — implemented, tested, enforced** | `src/quant_research/backtest/validation.py`, `provenance.py`; `tests/backtest/test_validation.py`. V7 engine-provenance guard per lessons-log 2026-06-08 |
| Geometry / parity guards | **DONE — landed this session** | `9813688`; `tests/backtest/test_{geometry,parity,fill_resolution_geometry,trade_ledger_geometry}.py` |
| **H-W4-7 quarterly close-location** | **IN PROGRESS — no verdict issued** | research-log 2026-08-18 Session 3. Primary reproduced at clean SHA (6410 trades, 50.5% WR, $1,358.70, DD $6,769.84), V1–V7 PASS. Cells A–C **all fail** the pre-specified pulse (PF ≥ 1.10 AND 4/7 years+). Kill/promote **not issued** |
| H9 / H10 | **BLOCKED — data** | No `RTY *.Last.txt` / `ES *.Last.txt` under `data/raw/`. Needs operator export |
| MES as discovery surface | **PRE-REGISTERED CONVENTION, N=0 run** | research-log 2026-06-08 dual-instrument methodology entry. Loader supports MES (`MES_CONTRACT_GLOB`); no MES hypothesis has been run |
| H-W4-1 … H-W4-6 | **DO NOT EXIST — phantom IDs** | research-log 2026-08-18 ledger correction: discussed in chat, never registered, never run; exerted no selection pressure. Committed MNQ running **N = 15** |
| ATM-model artifacts | **NONE IN REPO** | No matching module or artifact found |
| Unregistered work | **NONE FOUND** | Every landed script/notebook maps to a research-log entry. The four `scripts/_*.py` scratch helpers support registered runs (`_phase3_step0_extract` → Phase 3 step 0) |
| TDD $2K vs $3K | **RESOLVED — $2K** | `docs/ai-project-instructions.md` §7; lessons-log 2026-05-16 supersedes the $3K reading. Stale $3K reference in the working plan was corrected in `f68a33f` |

---

## 4. Residual lint findings (53) — deliberate, not oversight

The formatter is clean and all mechanically safe rules are applied. What remains was left
unfixed **on purpose** because the fixes are not behavior-neutral in code that produced
RESULT-LOGGED verdicts:

| Rule | Count | Why deferred |
|---|---|---|
| `E501` line-too-long | 30 | Long strings/comments the formatter cannot split |
| `F841` unused-variable | 10 | Ruff's fix leaves a bare expression statement rather than deleting the line |
| `B905` zip-without-strict | 6 | Adding `strict=` changes runtime behavior on length mismatch |
| `SIM114` if-with-same-arms | 3 | **Would collapse the branches in `iter_h3_h7_reclaim_signals`** — the signal generator behind the logged P2-W2 H-3 and P2-W3 H-7 verdicts |
| `SIM108` / `SIM102` | 4 | Cosmetic restructuring inside strategy sims |

`SIM114` is the load-bearing one: rewriting that generator is a methodology change under
`docs/ai-project-instructions.md` §2 and needs operator sign-off, not a lint autofix. An
attempted autofix pass during this session was reviewed and **reverted** for exactly this
reason.

One genuine finding was fixed: `F821` undefined-name in `run_wave1_guard_verification.py`,
where `import polars as pl` sat inside a function while the signature annotated `pl.DataFrame`.
It was **latent, not live** — `from __future__ import annotations` leaves the annotation
unevaluated — so the logged 2026-06-07 artifact was validly produced.

---

## 5. Integrity concerns

1. **`data/raw/` holds no market data.** Zero `*.Last.txt` contract files. **43 tests skip**
   for this reason, and no backtest in the repo can currently be re-run or reproduced on this
   machine. This is **pre-existing** — the same 43 skips appear in the first test run of this
   session, before any change. This is the single largest practical blocker to further
   development and is not fixable from git; it needs an operator data restore.

2. **`wip/wave0e-ict-backlog` must not be deleted casually.** It is the **only surviving copy**
   of the five excluded OTE per-trade JSON logs (~88 MB); those files are no longer on local
   disk. Export them before ever deleting the branch. Its other content is superseded by `main`.

3. **Charter vs kickoff conflict, unresolved.** `docs/program-charter.md` still frames Phase 2
   exit as **≥ X% improvement vs ORB+Opt3**, which predates the Wave 0h reframe to
   new-strategy search under joint gates + $36K floor economics. Flagged in the working plan
   rather than silently edited — charter changes require operator sign-off.

4. **Stale starter-doc references remain in two protected files.**
   `docs/phase-1-detailed-plan.md:402` (stable doc, needs sign-off) and
   `context-system-implementation-spec.md:99,116` (historical design narrative). All
   navigational references were repaired in `f68a33f`.

5. **Operator-caused data deletion during this session, fully recovered.** Removing the
   redundant `session3/hw4-7` worktree failed on Windows path length, and the follow-up
   `robocopy /MIR` cleanup followed a junction into the main repo's `data/raw`, deleting two
   tracked manifests (`bias_manifest.csv`, `cisd_smt_manifest.csv`). Both were restored from
   git **byte-identical**; `git diff HEAD -- data/` is empty. `/XJ` should have been passed to
   exclude junctions.

6. **Not an integrity issue but worth stating:** no result, verdict, N count, or DSR figure was
   altered by this cleanup. The only research-log content changes were two **append-only**
   additions (an artifact-availability note and a backlog-disposition correction).

---

## 6. Verdict

**(a) Single active thread.** **H-W4-7 — quarterly close-location continuation (MNQ)**, at
Session 3 with **no kill/promote issued**. The family is dead at the fixed-bracket pulse level;
no R:R sweep, ATR variant, or block subset has been run. Everything else in Phase 2 is closed
negative.

**(b) Top 3 incomplete items, dependency order.**

1. **Restore `data/raw/` market data.** Nothing can be re-run, reproduced, or newly screened
   without it — this gates every item below.
2. **Issue the H-W4-7 kill/promote decision.** The pre-specified pulse failed on all three
   cells; the ledger has no verdict. Either kill the family explicitly or pre-register the
   named follow-ups (R:R sweep / ATR variant / block subset) as new hypotheses at the then-true
   N. Leaving it undecided is what allows phantom-ID drift of the H-W4-1…6 kind.
3. **Pre-register the next wave against a decided surface.** MES remains an untried discovery
   surface at N=0 (verify `$/pt` in engine config first); H9/H10 stay blocked pending an
   RTY/ES export.

**(c) Integrity posture.** Materially improved. The doc→repo divergence that dominated the
Aug-11 audit is closed, the suite is green at 455, formatting is uniform, and the artifact
ledger is honest about what is deliberately excluded and where it lives. The open concerns are
the missing market data (§5.1), the single-copy backlog branch (§5.2), and the charter/kickoff
success-criteria conflict (§5.3) — none of which are silent.
