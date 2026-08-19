# Project State & Open Threads Report

**Audit date:** 2026-08-11  
**Repo:** `quant-research-lab`  
**Auditor scope:** Evidence-only state audit (git + docs + tests). Not a research recommendation.  
**HEAD:** `ae2fa83edc6f1940a841b92e99caff381b9f8839`  
**Branch:** `main` (tracks `origin/main`, up to date)

---

## 1. Repo ground truth

### 1.1 Last commit

| Field | Value |
|-------|--------|
| SHA | `ae2fa83` |
| Date | **2026-07-29 13:53:38 -0400** |
| Message | `PCS Stage 3: remove deprecated flux-v2-module-search-starter from corpus.` |
| Author | christian-mack |

Recent history (abbrev.): PCS work (`ae2fa83`…`d23ead6`) sits on top of MES dual-instrument docs (`a715de6`), P2-W2/W3 M4 closure (`db21393`, `1fe521b`, `fb264ac`), then Wave 1 ICT Phase 1 primitives (`0db224f`) and Wave 0 graded baseline chain (`c98b3d7`…).

### 1.2 Branches

```
* main
  remotes/origin/main
```

No feature branches besides `main`.

### 1.3 Working tree (uncommitted / untracked)

`git status` shows a **large dirty tree** (≈83 short-status lines; ≈77 untracked).

**Modified (tracked, not staged):**

- `docs/current-working-plan.md` (material rewrite vs HEAD — see §2)
- `notebooks/validation/2026-05-13_wave0d_orb_opt3_account_class_survey.md`
- `src/quant_research/ict/__init__.py`
- `src/quant_research/statistics/apex_eod_trailing.py`
- `src/quant_research/utils/__init__.py`
- `tests/test_apex_eod_trailing.py`

**Untracked (selected; not exhaustive):**

| Category | Paths (evidence) |
|----------|------------------|
| Wave 0e–0h artifacts + runners | `notebooks/validation/2026-05-17_wave0{e,f,g,h}_*`, `scripts/run_wave0{e,f,g,h}_*`, `docs/orb_opt3_phase2_closeout.md` |
| Wave 1 Track 1/1b artifacts + runners | `2026-05-26_wave1_stage1_track1_*`, `2026-05-29_wave1_stage1_track1b_*`, matching `scripts/run_wave1_*` |
| Wave 1 Track 2 ICT (post–Phase 1) | `src/quant_research/ict/{bias_module,mss,ote_*,guard_analysis}.py`, matching `tests/ict/`, many `2026-06-0{5,6,7}_wave1_*` validation artifacts, runners |
| ORB account-class survey (2026-06-08) | `notebooks/validation/2026-06-08_orb_account_class_survey.*`, `scripts/run_orb_account_class_survey.py` |
| Backtest geometry/parity (local) | `src/quant_research/backtest/{parity,validation_spot_checks}.py`, `tests/backtest/test_{geometry,parity,fill_resolution_geometry,trade_ledger_geometry}.py` |
| Misc | `.coverage`, debug scripts `scripts/_d7_golden_score.py`, `_m6_*.py`, `_phase3_step0_extract.py` |

**Local data (gitignored, present on this machine):** `data/raw/mnq/` **26** `*.Last.txt`; `data/raw/mes/` **26**; `data/raw/mym/` **26**.

### 1.4 Docs → committed-tree mismatch (lessons-log 2026-04-28 failure mode)

Committed docs **name** artifacts that are **not** in `HEAD`:

| Referenced path | Cited by (committed) | In HEAD? | On disk? |
|-----------------|----------------------|----------|----------|
| `docs/orb_opt3_phase2_closeout.md` | `phase-2-kickoff.md`, `lessons-log.md`, `research-log.md` Wave 0h | **No** | Yes (untracked) |
| `notebooks/validation/2026-05-17_wave0e_orb_opt3_survey.{md,json}` | `research-log.md` Wave 0e | **No** | Yes |
| `…wave0f…`, `…wave0g…`, `…wave0h…` | `research-log.md` / lessons | **No** | Yes |
| `…wave1_stage1_track1_quant_screen.*` | `research-log.md` | **No** | Yes |
| `…wave1_stage1_track1b_h8b_screen.*` | `research-log.md` | **No** | Yes |
| `src/quant_research/ict/bias_module.py` (+ OTE suite) | `research-log.md` Track 2 Phase 2–3d | **No** | Yes |
| `notebooks/validation/2026-06-08_orb_account_class_survey.*` | `research-log.md` 2026-06-08 | **No** | Yes |
| `flux-v2-module-search-starter.md` | HEAD `current-working-plan.md`, `phase-2-kickoff.md` Related | **No** (removed `ae2fa83`) | **No** |

**Committed and present** (counterexamples): Wave 0 / 0b / 0c / 0d validation artifacts; Wave 1 Track 2 Phase 1 primitives note; P2-W2/W3 gate1 + forensic + M4 re-run artifacts; `docs/ict/bias_module_spec.md`; ICT Phase 1 primitives under `src/quant_research/ict/{cisd,fvg,smt,pd_arrays,liquidity_sweep}.py`.

---

## 2. Document reconciliation

`CLAUDE.md`: **not present** in repo.

### 2.1 Timeline of most recent entries (by document)

| Document | Newest substantive stamp | What it says “now” is |
|----------|--------------------------|------------------------|
| `docs/program-charter.md` | Empirical anchor **2026-05** (corrected ORB economics); living umbrella | Phase 2 = income-gap research; Flux V1 live ORB+Opt3; architecture as means |
| `docs/lessons-log.md` | **2026-07-29** PCS Windows hook; **2026-06-08** P2 W2/W3 M4 consolidation + V7 | P2 quant W2/W3 = clean negative on trusted rails; infra restored |
| `docs/phase-2-kickoff.md` | Wave **0h** reframe (**2026-05-17**); MES dual-instrument section (aligned with `a715de6`) | Active Phase 2 = **new-strategy search**; joint gates + ≥$36K/yr floor |
| `docs/research-log.md` | Last entry **2026-06-08** — MNQ+MES dual-instrument convention; prior same day closes P2-W2/W3 M4 re-run | Latest *logged research* ends at W2/W3 negative + MES N=0 convention |
| `docs/current-working-plan.md` (**HEAD**) | **Last updated: May 14, 2026** | **Wave 0 (current)**; Wave 1 tasks still open checkboxes |
| `docs/current-working-plan.md` (**working tree, uncommitted**) | Header still **May 29, 2026** Track 1b; body extends Track 2 through step 3c | Claims **Wave 1 (current)**; step 4 **BLOCKED**; **does not** mention P2-W2/W3 or OTE step 3d closure |

### 2.2 Contradictions (doc vs doc / doc vs HEAD)

1. **Active wave identity**
   - HEAD working plan: Wave 0 current.
   - Dirty working plan: Wave 1 current; Track 2 step 4 blocked.
   - Kickoff + lessons + research-log: Wave 0h closed; Wave 1 Track 1/2 and **P2-W2/W3** already RESULT-LOGGED; no open pre-registered wave after 2026-06-08.

2. **Near-future Wave 2/3/4 placeholders** in working plan (`Walk-forward…`) **do not match** executed ids **P2-W2** / **P2-W3** in `research-log.md` / lessons-log.

3. **Charter Phase 2 exit** still frames **≥X% vs ORB**; kickoff + dirty working plan reframe to **joint gates + $36K floor** (working plan explicitly flags charter realignment pending).

4. **TDD figure in early Wave 0 text** (`research-log` Wave 0 PRE used **$3,000** R(q) ceiling) vs corrected **$2,000** pre-lock trail (`lessons-log` 2026-05-16 Wave 0c; `ai-project-instructions.md` Apex section). Wave 0b caveat in research-log marks $3K path **superseded**.

5. **Starter doc:** kickoff/working-plan still list `flux-v2-module-search-starter.md`; commit `ae2fa83` removed it from corpus; file absent on disk.

---

## 3. Open threads inventory

Status key: **DONE** | **IN-PROGRESS** | **PRE-REGISTERED BUT NOT RUN** | **BLOCKED** | **STALE/AMBIGUOUS**

| Thread | Status | Evidence |
|--------|--------|----------|
| Wave 0 graded baseline (R(q), max sustainable qty) | **DONE** | `research-log.md` 2026-05-14 RESULT-LOGGED; artifacts in HEAD: `notebooks/validation/2026-05-14_wave0_orb_opt3_graded_baseline.{md,json}`; commit `c98b3d7`. Result: **q_max = 0** under then-$3K R(q) rule |
| Wave 0b R(q)/EOD methodology | **DONE** (superseded for firm rules) | HEAD artifacts `2026-05-16_wave0b_*`; research-log RESULT + caveat → use Wave 0c |
| Wave 0c two-gate re-baseline ($2K trail) | **DONE** (DLL terminal bug later corrected) | HEAD `2026-05-17_wave0c_*`; lessons 2026-05-16 |
| Wave 0d DLL pause + account-class survey | **DONE** (numerics obsolete → 0e) | HEAD `2026-05-13_wave0d_*`; research-log caveat |
| Wave 0e–0h ORB chapter | **DONE** in log; **IN-PROGRESS** as repo hygiene | RESULT-LOGGED in committed `research-log.md`; **artifacts/scripts/closeout doc untracked** (§1.4) |
| Wave 1 Track 1 quant (H1–H12) | **DONE** (0 survivors); artifacts untracked | `research-log.md` 2026-05-26; code `research_wave1/` in HEAD; screen md/json **untracked** |
| Wave 1 Track 1b H8b (MES–MNQ) | **DONE** (KILLED); artifacts untracked | `research-log.md` 2026-05-29; MES loader used successfully for screen |
| H9 / H10 (RTY / ES) | **BLOCKED** | No `RTY *.Last.txt` / `ES *.Last.txt` under `data/raw/` per research-log Track 1 RESULT; RTY still pending in dirty working plan |
| Wave 1 Track 2 Phase 1 ICT primitives + MYM | **DONE** | HEAD: `src/quant_research/ict/{cisd,fvg,smt,…}.py`, `2026-06-04_wave1_track2_phase1_ict_primitives.md`, commit `0db224f` |
| Wave 1 Track 2 Phase 2 bias module | **DONE** in log; **code/artifacts untracked** | Spec in HEAD `docs/ict/bias_module_spec.md`; impl `bias_module.py` + validation `2026-06-05_*` **untracked** |
| Wave 1 Track 2 Phase 3 OTE (steps 0–3d) | **DONE** (OTE closed, no account-viable edge); **impl/artifacts largely untracked** | `research-log.md` through 2026-06-07 step 3d + guard-clean OTE; `ote_*.py` / mss / notebooks **untracked** |
| Dirty working plan “Phase 3 step 4” | **STALE/AMBIGUOUS** | Checkbox still open/BLOCKED in dirty plan; research-log already closed OTE and pivoted (then ran P2-W2/W3) |
| ORB account-class survey 2026-06-08 | **DONE** in log; artifacts untracked | research-log RESULT: no class clears $36K + eval≥50%; files untracked |
| P2-W2 H-1…H-6 tight-loss-tail | **DONE** (wave FAIL on M4) | Committed artifacts `2026-06-08_p2w2_*`, `2026-06-08_p2_m4_gate1_rerun.*`, commits `307cecb`/`1fe521b`; lessons 2026-06-08 |
| P2-W3 H-7 OR-reclaim continuation | **DONE** (DEAD on M4; do not rerun) | Committed `2026-06-08_p2w3_*` + M4 re-run; research-log |
| **H-W4-1 … H-W4-6** | **STALE/AMBIGUOUS — IDs do not exist** | Repo-wide search: only example string in `context-system-implementation-spec.md` D-05. **No** research-log entries. Closest real set: **P2-W2 H-1…H-6** (Gate #1 + M4 full IS re-run done; OOS sealed; no full joint-gate harness promotion). Working-plan “Wave 4” is an unused placeholder |
| MES loader / MES as discovery surface | **IN-PROGRESS / gated** | `MES_CONTRACT_GLOB` in HEAD `data_loader.py`; local MES data present; H8b + ICT SMT used MES as **feature**. Dual-instrument convention (`research-log` 2026-06-08): **MES running N = 0**; hard-stop until both loaders resolve + **MES $5/pt / $1.25 tick verified in engine cost config** before trusting MES economics. Not the old “no MES files” block |
| TDD $2K vs $3K under Apex 4.0 | **DONE** (resolved) | lessons-log 2026-05-16 Wave 0c; `ai-project-instructions.md` ($2K pre-lock); kickoff table; Wave 0 / 0b $3K retained only as historical/superseded |
| V1–V7 harness | **DONE** (implemented + unit-tested) | `src/quant_research/backtest/validation.py` (V1–V7), `provenance.py`; `tests/backtest/test_validation.py`; research-log V7 RESULT; lessons 2026-06-07/08 |
| ATM-model artifacts | **STALE/AMBIGUOUS — none found** | No ATM strategy/module artifacts in repo. **Bias-module** exists (spec committed; implementation untracked) — distinct from ATM |
| PCS / context system | **DONE** (recent commits) | Last commits through `ae2fa83`; lessons 2026-07-29 |

### 3.1 Wave 0 graded baseline — completed and logged?

**Yes.** Pre-registered + RESULT-LOGGED in `docs/research-log.md` (2026-05-14); committed artifacts under `notebooks/validation/2026-05-14_wave0_orb_opt3_graded_baseline.*`. Headline: **q_max = 0** under original R(q)≤$3K rule. Later waves **0c–0h** supersede firm-rule grading; those later artifacts are logged but **not committed** (§1.4).

### 3.2 Wave 1–3 status (per research-log naming)

| Wave | Status |
|------|--------|
| Wave 1 Track 1 + 1b | RESULT-LOGGED — **0 Stage-1 survivors**; H9/H10 blocked on RTY/ES |
| Wave 1 Track 2 | RESULT-LOGGED through OTE step 3d — **OTE closed**; bias module built |
| P2-W2 (often called “Wave 2” informally) | RESULT-LOGGED — **FAIL** on M4; H-5 calendar **BLOCKED** |
| P2-W3 | RESULT-LOGGED — **H-7 DEAD** on M4; closed |
| Working-plan placeholder Wave 2/3/4 | Not the executed naming; Wave 4 walk-forward **not started** |

### 3.3 “Wave 4” / H-W4-1…H-W4-6

| ID | Frequency screen | Full harness / graded run | Notes |
|----|------------------|---------------------------|-------|
| H-W4-1 … H-W4-6 | **N/A — not in corpus** | **N/A** | Only PCS example id |
| P2-W2 H-1…H-6 (nearest real analogue) | Gate #1 IS mortality **run** (committed) | M4 Gate #1 re-run **V1–V7 PASS** (committed); **no** Gate #2–#4 / OOS / joint Apex battery (none cleared expectancy on trusted path except low-n H-1/H-4 voided as frequency artifacts) | research-log + `2026-06-08_p2_m4_gate1_rerun.md` |

### 3.4 MES data loader — still blocking MES backtests?

| Question | Finding |
|----------|---------|
| Loader code present? | **Yes** — `MES_CONTRACT_GLOB = "mes/MES *.Last.txt"` in committed `data_loader.py` |
| Local MES tape present? | **Yes** — 26 files under `data/raw/mes/` (this machine) |
| Used in completed work? | **Yes** — H8b screen; ICT SMT / bias (as cross-feature) |
| MES **execution** hypothesis search? | **Not started** — research-log: **MES N = 0** |
| Remaining hard-stop for MES **economics**? | **Yes** — dual-instrument preconditions: real dual load + verify MES **$5/pt** / **$1.25/tick** in engine cost config (`research-log` 2026-06-08; `phase-2-kickoff.md`) |
| MNQ “silent fallback” gate? | Called out as precondition for P2-W2/W3; those runs logged **PASS** on real `data/raw/mnq/` (26 files) |

### 3.5 TDD $2K vs $3K

**Resolved** for current research: Apex $50K EOD research class uses **$2,000** pre-lock trailing (lessons-log 2026-05-16; `docs/ai-project-instructions.md`; `phase-2-kickoff.md`). Early Wave 0 / 0b **$3,000** trail is **superseded**.

### 3.6 V1–V7 harness — implemented and passing?

| Item | Evidence |
|------|----------|
| Implementation | `validation.py` docstring + checks V1…V7; V7 provenance in `provenance.py` |
| Unit tests | `tests/backtest/test_validation.py` |
| Suite run (this audit, working tree) | `uv run pytest -q`: **444 passed**, **43 skipped**, **0 failed** (≈21.8s). Skips: no flat `data/raw/MNQ 03-26.Last.txt` (data lives under `mnq/`), PCS Postgres unreachable |
| Targeted | `tests/backtest/test_validation.py` + `tests/test_apex_eod_trailing.py`: **37 passed** |

Note: suite includes **untracked** ICT/geometry tests from the dirty tree. Committed-only checkout would omit those modules/tests.

### 3.7 ATM-model / bias-module artifacts

| Artifact | Status |
|----------|--------|
| ATM model | **None** found in repo |
| Bias module spec | **Committed:** `docs/ict/bias_module_spec.md` |
| Bias module code + Phase 2 run | **Untracked:** `src/quant_research/ict/bias_module.py`, `tests/ict/test_bias_module.py`, `scripts/run_wave1_track2_phase2_bias_module.py`, `notebooks/validation/2026-06-05_wave1_track2_phase2_bias_module.*` |
| Concept maps / manifests | **Committed:** `docs/ict_bias_concept_maps/*`, `data/raw/ict_sources/bias_manifest.csv` |

### 3.8 Code/notebooks without research-log pairing (potential unregistered work)

| Item | Research-log? | Notes |
|------|---------------|-------|
| Untracked exploration notebooks `2026-05-31_ict_phase_a_*`, `2026-06-02_ict_cisd_smt_*` | CISD/SMT ingestion **is** logged; Phase A notebook may be local orchestration | Low risk if maps committed |
| Untracked `parity.py`, geometry tests, `_m6_debug` / `_d7_golden_score` | No dedicated RESULT entries | Tooling / WIP |
| Dirty edits to `apex_eod_trailing.py` | Wave 0e+ logged against prior commits | Verify before trusting new sims |
| PCS commits after 2026-06-08 | Lessons 2026-07-29; not a strategy wave | OK |

Primary integrity issue is the inverse: **logged results whose artifacts never landed in git** (§1.4), not a large set of unlogged edge claims.

---

## 4. Verdict

### (a) Single active wave/task (per docs)

**Ambiguous — documents disagree; chronologically latest research close is idle.**

- **Authoritative research chronology** (`research-log.md` + lessons-log): last strategy waves closed **2026-06-08** (P2-W2/W3 negative on M4; MES dual-instrument convention with **MES N=0**). Subsequent commits through **2026-07-29** are **PCS**, not a new hypothesis wave.
- **Kickoff:** active work = Phase 2 **new-strategy search** (no named open wave).
- **HEAD working plan:** incorrectly still **Wave 0 current** (stale May 14).
- **Dirty working plan:** claims **Wave 1 current** with Track 2 step 4 blocked — **behind** research-log (OTE already closed; W2/W3 already run).

There is **no** clean single “current wave” checkbox that matches HEAD + research-log simultaneously. Operationally, the program is in a **post–W2/W3 / post-OTE gap**: waiting for the next **pre-registered** hypothesis batch (and/or MES surface), after a large **uncommitted** artifact backlog.

### (b) Top 3 highest-priority incomplete items (dependency order)

1. **Repo/doc integrity gate** — Commit or deliberately drop the untracked Wave 0e–0h, Wave 1 screens, Track 2 ICT (bias/OTE), and ORB account-class survey artifacts; update **HEAD** `current-working-plan.md` to match `research-log.md` / lessons. Unblocks trust in any “current” pointer (lessons-log **2026-04-28**).
2. **Operator pre-registration of the next hypothesis wave** — Prior MNQ quant (Track 1, P2-W2/W3) and ICT OTE paths are RESULT-LOGGED closed/negative; dirty “step 4” is stale. No PRE-REGISTERED open wave exists after 2026-06-08.
3. **MES parallel discovery preconditions (if MES is next)** — Confirm engine **$/pt** and **tick** for MES, dual-loader hard-stop prints, then first MES-registered hypotheses (MES N still **0**). **Or**, if resuming Track 1 cross-instrument: obtain **RTY** (and ES if needed) to unblock H9/H10 — still blocked per research-log.

### (c) Integrity concerns

| Concern | Severity | Evidence |
|---------|----------|----------|
| Docs reference uncommitted artifacts (classic 2026-04-28 mode) | **High** | Wave 0e–0h, Wave 1 screens, bias/OTE impl, closeout md, orb survey — logged in HEAD `research-log.md` but absent from `git ls-tree HEAD` |
| `current-working-plan.md` HEAD vs reality | **High** | HEAD still Wave 0 current; dirty file partial/stale vs P2-W2/W3 |
| `flux-v2-module-search-starter.md` dangling references | **Medium** | Removed `ae2fa83`; still linked from kickoff / working plan |
| Working-tree test suite green does not imply clean-clone green | **Medium** | 444 passed includes untracked ICT/geometry tests; many real-data tests skipped on path layout |
| ORB account-class survey harness FAIL V1 noted in research-log | **Low–Medium** (logged) | Economics matched Wave 0; V1 geometry fail on ORB brackets explicitly noted 2026-06-08 entry |
| H-W4-* phantom ids | **Low** (audit clarity) | Only in PCS example text; do not treat as a pre-registered wave |

---

## Appendix A — Test suite snapshot (2026-08-11)

```
uv run pytest -q --tb=line
→ 444 passed, 43 skipped, 5 warnings in 21.79s
→ exit_code 0
```

Notable skips: MNQ real-data tests looking for `data/raw/MNQ 03-26.Last.txt` (exports live under `data/raw/mnq/`); PCS Postgres indexer/retriever tests.

## Appendix B — git log --oneline -50 (as of audit)

```
ae2fa83 PCS Stage 3: remove deprecated flux-v2-module-search-starter from corpus.
0195024 PCS D8: decision records, manifest entries, identifier regression tests.
47eb6c6 fix(pcs): D7 lexical query normalization for compound identifiers
b96fefd docs(pcs): close D6 on rule-primary integration and Windows hook fix
d23ead6 fix(pcs): repair sessionStart hook injection with venv bootstrap and hook-test
a715de6 docs: MES parallel discovery surface — methodology + per-instrument N convention
db21393 docs(research-log): P2-W2/W3 RESULT-LOGGED closure on M4 rails
abf39b1 docs(lessons): W2/W3 closed on M4 rails — zero deployable edge
bbc7996 chore(p2): stamp M4 gate1 re-run artifacts (git 1fe521b)
1fe521b feat(p2): migrate W2/W3 strategies onto M4 engine; retire simulate_p2_trade
fb264ac feat(backtest): V7 harness guard — M4 engine provenance stamp
ebf833e docs(lessons): P2-W2/W3 closure — bespoke walker bypass inflated H-7
955dcbb chore(p2w3): stamp H-7 exit-integrity forensic artifacts with commit sha
021d430 docs(p2w3): H-7 exit-integrity forensic — result CONTAMINATED
0383f84 chore(p2w3): stamp H-7 gate1 artifacts with commit sha
86bd753 feat(p2w3): H-7 Gate #1 IS mortality screen — SURVIVOR +$20.85/trade
0c18775 docs(research-log): pre-register P2-W3 H-7 OR-extreme reclaim continuation
719fb57 chore(p2w2): stamp forensic artifacts with commit sha
b833904 docs(p2w2): forensic verdict validity check — sign audit + frequency funnel
800c5cc chore(p2w2): stamp gate1 artifacts with implementation commit sha
307cecb feat(p2w2): Gate #1 IS mortality screen — 0/5 survivors
0585f9e docs(research-log): pre-register P2-W2 tight-loss-tail wave (N=6)
0db224f feat(ict): Wave 1 Track 2 Phase 1 — five ICT primitives + MYM data prep
90d8375 feat(data): instrument globs + research_wave1 pipeline; flush pending research-log
… (Wave 0 / bias / CISD chain continues through c98b3d7)
```

---

*End of audit report.*
