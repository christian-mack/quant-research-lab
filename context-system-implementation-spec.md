# Implementation Spec — Program Context System (PCS)

**Status:** Handoff spec. Approved by operator before any code is written.
**Owner:** Christian (operator / conductor)
**Implementation agent:** Cursor
**Repo:** `quant-research-lab`
**Related:** `docs/program-charter.md`, `docs/ai-project-instructions.md`, `docs/phase-2-kickoff.md`, `docs/current-working-plan.md`, `docs/lessons-log.md`, `docs/research-log.md`

---

## 1. Purpose

Build a durable retrieval layer over the program's accumulated context so that any agent session (Cursor, Claude app, Claude Code) starts with the same authoritative state and can retrieve prior findings without manual re-explanation.

This is infrastructure for a program that will run for years across multiple strategy generations. It is graded on **stability, determinism, and auditability**, not on speed or novelty. It touches decisions that eventually route real capital; it inherits the same correctness bar as the backtest engine.

### 1.1 Non-goals (explicit)

- **Not a store of record.** Git is the store of record. The PCS is a rebuildable index over git-tracked content. If the database is lost, `pcs reindex --all` reconstructs it from the repo. Nothing lives only in the database.
- **Not a replacement for reading the canonical docs.** See §4.1 (pinned corpus).
- **Not a document editor.** The PCS reads. Doc updates are made by the operator or by Cursor under existing `ai-project-instructions.md` rules, then re-indexed.
- **Not a live trading component.** No PCS code path may be imported by anything that executes orders. This is a research/dev tool.
- **Not multi-user, not networked, not authenticated.** Localhost only in this phase.

---

## 2. Locked decisions (do not revisit; Cursor has no discretion here)

| # | Decision | Rationale |
|---|---|---|
| D-01 | **PostgreSQL 17 + pgvector**, run from the official `pgvector/pgvector:pg17` Docker image | Production-grade, ACID, auditable, already the target for eventual server deployment. Docker avoids a native-Windows pgvector build, which is the highest-risk install step on this machine. Docker Desktop is present (lessons log 2026-04-26). |
| D-02 | **Docker Compose** with a named volume for the data directory; container restarts do not lose the index | Reproducible, one command up/down |
| D-03 | Embedding model: **`BAAI/bge-base-en-v1.5`**, 768 dims, pinned to an exact revision SHA | Corpus is small; embedding cost is one-time and irrelevant. Quality is free here. Pinned revision = deterministic embeddings. |
| D-04 | **Exact search** (`ORDER BY embedding <=> query`), **no ANN index** | Corpus is <10k rows. Exact scan is faster than ivfflat at this size *and* returns identical results every run. ANN introduces approximation and index-training state for zero benefit. Revisit only above ~50k chunks, via lessons-log entry. |
| D-05 | **Hybrid retrieval**: cosine similarity + Postgres full-text search (`tsvector`), fused by Reciprocal Rank Fusion | Exact identifiers dominate this corpus (`ORB+Opt3`, `R(q)`, `H-W4-1`, `M6`, git SHAs). Pure semantic search misses these. Non-negotiable. |
| D-06 | **Pinned corpus loaded in full, never chunk-retrieved** (see §4.1) | Chunk fragments of the charter are worse than the charter |
| D-07 | Python 3.13, Windows-native, `uv` | Matches `ai-project-instructions.md` §3 |
| D-08 | Code lives at `src/quant_research/context/`; tests at `tests/context/` | Same repo, same discipline (`ai-project-instructions.md` §3 file organization) |
| D-09 | Every chunk row records: source path, git SHA at index time, content hash, chunk params, embedding model id + revision | Staleness detection and reproducibility. A retrieval result must be traceable to a commit. |
| D-10 | Incremental re-index by **content hash**, not mtime | mtime lies across checkouts, syncs, and editors |
| D-11 | Primary agent integration is an **MCP server** exposing read-only tools; a CLI is the fallback and the debugging surface. Cursor wiring (mcp.json + sessionStart hook + alwaysApply rule) is specified in §6.1 | MCP is documented and consumable by Cursor, Claude Code, and the Claude app. One interface, three consumers. |
| D-12 | PCS tools are **read-only**. No tool writes to the repo or the DB. | Prevents an agent from "helpfully" rewriting the charter |
| D-13 | Deletion of any repo artifact is **out of scope for this spec** and requires separate operator approval per `ai-project-instructions.md` §2/§5 | See §8 |

### 2.1 Dependencies requiring operator approval

`ai-project-instructions.md` §2 requires confirming each new dependency. This spec adds:

| Package | Purpose | Weight | Note |
|---|---|---|---|
| `sentence-transformers` | Embedding | Heavy — pulls `torch` (~2-3 GB with CUDA, ~200 MB CPU-only) | **Install CPU-only torch explicitly.** No GPU need at this corpus size. This is the single largest addition to the environment. |
| `psycopg[binary]` | Postgres driver | Light | v3, not psycopg2 |
| `pgvector` (python) | Vector type adapter | Light | |
| `mcp` | MCP server SDK | Light | |
| `pydantic` | Config/schema validation | Light | May already be present transitively |

`sqlalchemy` is **not** used. Raw `psycopg` with explicit SQL — the schema is five tables and the queries are hand-written; an ORM adds a dependency and hides the SQL that needs auditing.

**Operator: approve or reject this dependency list before D1 begins.**

---

## 3. Open decisions — operator sign-off required before any code

Cursor must **stop and ask** on each of these. Do not infer, do not pick a default, do not proceed with "reasonable assumptions."

| # | Question | Options | Why it can't be pre-decided |
|---|---|---|---|
| Q-01 | Does the pinned corpus list in §4.1 match your intent? | Add/remove files | Only the operator knows what's canonical |
| Q-02 | How are chat transcripts exported and where do they land? | Anthropic account data export (`conversations.json`) → `data/context/chats/` (gitignored, PII risk) **vs.** hand-curated per-chat markdown summaries committed to `docs/chat-extracts/` | Trade-off: raw export is complete but noisy and unreviewed; curated extracts are clean and reviewable but cost operator time. Affects §5.3 and the whole value of the system. |
| Q-03 | Is `data/context/` gitignored? | Yes (index rebuildable, transcripts may contain account details) / No | Interacts with `ai-project-instructions.md` §8 (no account numbers, no live trade logs in repo) |
| Q-04 | Is `src/` code indexed, or docs only, in D-phase? | Docs only first, code later / both now | Code chunking is a different problem (AST-aware vs. text). Recommend docs-only for v1. |
| Q-05 | Postgres port and whether the container is exposed beyond localhost | 5432 vs. non-default; localhost-bound | Localhost-bound strongly recommended |
| Q-06 | Does the golden query set (§7.2) reflect the questions you actually need answered? | Edit the list | This set *is* the acceptance test. If it's wrong, "verified" means nothing. |

---

## 4. Corpus design

### 4.1 Tier 1 — Pinned (loaded in full, never chunked, never retrieved by similarity)

These are the current-state documents. An agent session loads them **whole**, every time.

- `docs/program-charter.md`
- `docs/phase-2-kickoff.md`
- `docs/current-working-plan.md`
- `docs/ai-project-instructions.md`
- `docs/flux-response-style.md`

The PCS exposes these via a `get_pinned_context()` tool that returns full text plus the git SHA. No similarity search, no chunking, no ranking. If this set grows past roughly 60k tokens, that is a signal the docs need consolidation — not that the tier needs a retriever.

### 4.2 Tier 2 — Retrieved (chunked, embedded, hybrid-searched)

Append-only and historical content, where the corpus grows without bound and you want the *relevant* entry, not all of them:

- `docs/lessons-log.md` — chunk boundary = **one entry** (`## YYYY-MM-DD — ...` heading)
- `docs/research-log.md` — chunk boundary = **one hypothesis/wave record**
- `docs/m6-nt8-reproduction.md`, `docs/nt8-backtest-methodology.md`, `docs/phase-1-detailed-plan.md`
- `flux-v2-module-search-starter.md` (carries a deprecation header — see §4.4)
- Chat extracts (per Q-02)
- `src/` and `notebooks/` — deferred pending Q-04

### 4.3 Chunking rules (locked)

**Structural, not fixed-width.** Fixed-width character chunking is wrong for this corpus: it splits a lessons-log entry's Finding from its Implication, which is precisely the pairing that makes the entry useful.

1. Split on the nearest enclosing markdown heading (`##` for logs, `###` where sections are long).
2. If a resulting chunk exceeds **1200 tokens**, split on sub-headings, then on paragraph boundaries — never mid-sentence, never mid-table, never mid-code-fence.
3. If a chunk is under **80 tokens**, merge it forward into the next sibling.
4. **Prepend a breadcrumb header** to every chunk's embedded text: `{file_path} > {h1} > {h2}` plus, for dated entries, the entry date. A retrieved fragment must be self-identifying.
5. Tables and fenced code blocks are **atomic** — never split, even if oversized.
6. No overlap. Structural boundaries are semantic boundaries; overlap here duplicates content and corrupts ranking.

### 4.4 Superseded content (critical — this corpus actively contradicts itself)

This is the sharpest failure mode in the whole system, and it is specific to this repo. `lessons-log.md` is append-only and **contains corrections of its own earlier entries**: the 2026-04-27 UTC entry supersedes the 2026-04-26 DST entry's rationale; the 2026-05-13 correction supersedes the `~$10,885/yr per contract` reading in the 2026-04-28 entries. `flux-v2-module-search-starter.md` carries a deprecation header. `flux-system-dev-guide.md` and `flux-v1-development-roadmap.md` describe a tri/quad-module architecture that was cut from production in 2026-04-28.

Naive retrieval will surface `$10,885/yr per contract` and the quad-module economics as current fact. That is a wrong-number-into-a-decision failure, which is exactly the class of error the program's lessons log exists to prevent.

Required handling:

1. A **`status`** column per chunk: `current` | `superseded` | `deprecated` | `historical`.
2. A hand-maintained **`docs/context-manifest.yml`** mapping file paths and entry dates to status, plus a `superseded_by` pointer. The operator owns this file. It is the one piece of curation the system cannot infer.
3. Retrieval **defaults to `status = current`**. Superseded chunks are returned only when explicitly requested (`include_superseded=true`).
4. When a superseded chunk *is* returned, its breadcrumb is prefixed: `[SUPERSEDED by {pointer}]`.
5. Indexing **fails loudly** if a Tier-2 file or dated entry has no manifest entry. Unclassified content does not silently enter the index as `current`.

This preserves the append-only rule (nothing is edited or deleted) while making retrieval honest.

---

## 5. Architecture

```
quant-research-lab/
├── docker/
│   └── pcs-compose.yml            # pgvector/pgvector:pg17, named volume, localhost-bound
├── docs/
│   └── context-manifest.yml       # operator-owned status map (§4.4)
├── src/quant_research/context/
│   ├── __init__.py
│   ├── config.py                  # pydantic settings; model id + revision pinned here
│   ├── schema.sql                 # DDL, versioned, applied by migrate.py
│   ├── migrate.py                 # idempotent schema application
│   ├── manifest.py                # parse/validate context-manifest.yml
│   ├── chunker.py                 # §4.3 — pure functions, no I/O
│   ├── embedder.py                # bge-base-en-v1.5, pinned revision, batch encode
│   ├── indexer.py                 # walk → hash → chunk → embed → upsert
│   ├── retriever.py               # hybrid search + RRF + status filter
│   ├── pinned.py                  # Tier-1 full-text loader
│   ├── cli.py                     # pcs {reindex,search,pinned,status,doctor}
│   └── mcp_server.py              # read-only MCP tools
└── tests/context/
    ├── test_chunker.py
    ├── test_manifest.py
    ├── test_indexer.py
    ├── test_retriever.py
    └── test_golden_queries.py     # §7.2 — the acceptance test
```

### 5.1 Schema (authoritative)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE pcs_index_run (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    git_sha         TEXT NOT NULL,
    git_dirty       BOOLEAN NOT NULL,
    embed_model     TEXT NOT NULL,
    embed_revision  TEXT NOT NULL,
    chunker_version TEXT NOT NULL,
    files_indexed   INT,
    chunks_written  INT
);

CREATE TABLE pcs_document (
    id              BIGSERIAL PRIMARY KEY,
    file_path       TEXT NOT NULL UNIQUE,
    tier            SMALLINT NOT NULL,           -- 1 = pinned, 2 = retrieved
    content_hash    TEXT NOT NULL,               -- sha256 of file bytes
    git_sha         TEXT NOT NULL,
    indexed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_id          BIGINT NOT NULL REFERENCES pcs_index_run(id)
);

CREATE TABLE pcs_chunk (
    id              BIGSERIAL PRIMARY KEY,
    document_id     BIGINT NOT NULL REFERENCES pcs_document(id) ON DELETE CASCADE,
    chunk_index     INT NOT NULL,
    breadcrumb      TEXT NOT NULL,               -- "docs/lessons-log.md > 2026-05-13 — Correction: ..."
    entry_date      DATE,                        -- for dated log entries; NULL otherwise
    chunk_text      TEXT NOT NULL,               -- exact source text, unmodified
    embed_text      TEXT NOT NULL,               -- breadcrumb + chunk_text; what was embedded
    token_count     INT NOT NULL,
    status          TEXT NOT NULL
                    CHECK (status IN ('current','superseded','deprecated','historical')),
    superseded_by   TEXT,
    embedding       vector(768) NOT NULL,
    tsv             TSVECTOR
                    GENERATED ALWAYS AS (to_tsvector('english', embed_text)) STORED,
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX pcs_chunk_tsv_idx    ON pcs_chunk USING GIN (tsv);
CREATE INDEX pcs_chunk_status_idx ON pcs_chunk (status);
-- Deliberately NO vector index. See D-04.

CREATE TABLE pcs_schema_version (
    version     INT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5.2 Retrieval algorithm (locked)

```
input: query, top_k = 8, include_superseded = false

1. semantic:  SELECT ... ORDER BY embedding <=> embed(query) LIMIT 30
2. lexical:   SELECT ... WHERE tsv @@ websearch_to_tsquery('english', query)
              ORDER BY ts_rank_cd(tsv, ...) DESC LIMIT 30
3. fuse:      RRF, score = Σ 1 / (60 + rank_i) across both lists
4. filter:    status = 'current' unless include_superseded
5. return:    top_k chunks, each with breadcrumb, file_path, entry_date,
              status, git_sha, and score
```

Every returned chunk carries provenance. An agent must be able to answer "where did this come from and as of which commit" without a second call.

### 5.3 Chat extraction (pending Q-02)

Whichever option is chosen, the output contract is fixed: one markdown file per source chat under a single directory, each with YAML front-matter (`chat_date`, `topic`, `decisions`, `status`, `supersedes`), and each classified in `context-manifest.yml`. Raw unreviewed transcript dumps are **not** indexed as `current` — they enter as `historical` unless the operator promotes them.

This is the step with the most operator time in it and the most value. A chat transcript contains reasoning that never made it into a doc; that's the whole reason this system exists.

---

## 6. Milestones

Each milestone has an exit criterion. Cursor reports at each boundary and **waits for operator confirmation** before starting the next. No milestone is "done" until its tests pass (`ai-project-instructions.md` §4).

| ID | Scope | Exit criterion |
|---|---|---|
| **D0** | Operator sign-off on §2.1 dependencies and all of §3 | Written answers to Q-01…Q-06 recorded in the chat |
| **D1** | Docker compose + schema + `migrate.py` | `docker compose up` → `migrate.py` → `pcs doctor` reports healthy, extension present, schema v1 applied. Container restart preserves data. |
| **D2** | `manifest.py` + `docs/context-manifest.yml` populated by operator | Every Tier-2 file and dated entry classified. `pcs doctor` fails on any unclassified entry. Tests cover the failure path. |
| **D3** | `chunker.py` | Unit tests: heading splits, oversized-table atomicity, code-fence atomicity, tiny-chunk merge, breadcrumb construction, entry-date extraction. Boundary cases per `ai-project-instructions.md` §4 (first/last entry, malformed heading, empty file). Chunker is pure — no DB, no filesystem. **Every `split_required: true` manifest entry (see `pcs manifest-check`) is actually split into separate-status chunks (§4.3 rule 2): the stale number becomes its own `superseded` chunk per its `split_note`, the live finding stays `current`. This is a D3 exit gate, tested. Each split has TWO D7 acceptance checks, both required — a lazy split that supersedes the whole numeric section passes the trap but silently breaks preservation: (a) **trap** — golden query #1 must NOT surface the `$10,885`-per-contract misread as `current`; (b) **preservation** — golden query #8 (M6 bracket re-arm), #2 (tri-module displacement), and a "per-account income gap / research priority" query MUST still retrieve their honest `current` narrative (incl. the `~$1,014` bracket-re-arm figures and the "income trails the $65K-$100K target — now an explicit research priority" claim, neither of which is the misread). The `~$8K/yr` figure is carved sub-sentence so its surrounding income-gap claim survives on the `current` chunk. Both trap (#1) and all three preservation checks passing is the exit condition for these splits.** |
| **D4** | `embedder.py` + `indexer.py` | Full index of Tier-2 corpus. Re-running with no file changes writes **zero** rows (content-hash idempotence — this is an explicit test). Every row carries model id, revision, git SHA. |
| **D5** | `retriever.py` + `pinned.py` + `cli.py` | `pcs search "..."` returns provenance-carrying results. `pcs pinned` returns Tier-1 full text + SHA. Superseded chunks excluded by default — explicit test using the 2026-05-13 correction. |
| **D6** | MCP server + Cursor integration | **Closed (2026-07-29).** Verified mechanism in §6.1. **Exit met via the alwaysApply rule + `get_pinned_context()`** — fresh sessions answer golden queries using PCS tools when the agent calls `get_pinned_context()` (confirmed in multiple test sessions). The `sessionStart` hook is **best-effort belt-and-suspenders**, not load-bearing (see §6.1 — supersedes the original D6 framing that treated hook injection as deterministic and the rule as supplement). |
| **D7** | Golden query acceptance (§7.2) | All golden queries pass. Failures are diagnosed and fixed, not re-scored. |
| **D8** | Consolidation | Chat extracts produced per Q-02, classified, indexed. Conflicts surfaced during extraction are resolved into docs by the operator, with lessons-log entries proposed per `ai-project-instructions.md` §6 (proposed, not written silently). Re-index. Re-run D7. |

**Project cleanup is not a milestone here.** See §8.

### 6.1 Agent integration mechanism (verified 2026-07-18 — supersedes the `pre_chat.py` assumption)

An earlier draft of this spec assumed a `.cursor/hooks/pre_chat.py` file. **That is not a real Cursor mechanism** (there is no `pre_chat` event and hooks are not loose `.py` files discovered by name); it is superseded by the following, verified against current Cursor docs (MCP, Rules, Hooks). Integration uses three files, each with a distinct job:

**Primary vs best-effort (supersedes original D6 framing, 2026-07-29):** The **`alwaysApply` rule + `get_pinned_context()` MCP tool** is the **primary, portable pinned-load mechanism** — confirmed working in every fresh session tested (IDE and cloud). The **`sessionStart` hook is best-effort, not load-bearing**: on Windows (Cursor 3.13.25) bare-`python` hook commands can fire with exit 0 yet produce empty stdout when the script re-execs to venv python; `pcs hook-test` does not detect this capture-layer failure. Hook acceptance is operator-verified in Cursor's Hooks Execution Log (`Merged 1 valid response(s) for step sessionStart`), not `hook-test`. The rule+tool pattern ports to Claude Code and the Claude app; a Cursor-specific injection hook does not.

- **`.cursor/mcp.json`** (project-scoped) — registers the PCS as a local **stdio MCP server** (`command: uv`, `args: ["run", "python", "-m", "quant_research.context.mcp_server"]`). This exposes the three read-only tools (`get_pinned_context`, `search`, `status`; D-11, D-12). This is the on-demand retrieval path; the agent calls tools when relevant, approval-gated by Run Mode. **D-11 primary integration path.**
- **`.cursor/rules/pcs.mdc`** (`alwaysApply: true`) — **Primary session bootstrap.** Teaches on-demand tool selection and how to read `[SUPERSEDED by …]` labels. Instructs the agent to call `get_pinned_context()` when it does not already see a pinned index in-session (cloud fallback and IDE fallback when the hook fails). Guardrail against summary-leakage: any compact index is a table of contents, **not** a substitute — any decision touching program state must load the full doc via `get_pinned_context()`.
- **`.cursor/hooks.json`** (`sessionStart` event) — **Best-effort optimization.** When working, injects a **compact pinned index** (doc title + one-line purpose + git SHA per Tier-1 doc) via the hook script's `additional_context` output — the index, **not** the full text. Command: `.venv/Scripts/python.exe .cursor/hooks/session_start.py` (repo-root-relative; **Windows venv layout assumption** — revisit on Linux clone or server deployment). Does not fire in cloud agents. Do not use bare `python` (stdout capture failure on Windows with re-exec) or `uv run` (`uv` often absent from hook subprocess PATH).

---

## 7. Verification

### 7.1 Test discipline

Standard project rules apply (`ai-project-instructions.md` §4): unit tests ship with the code, happy path plus edge cases, boundary conditions covered, all tests pass before commit, 80%+ coverage on `chunker`, `manifest`, `retriever`.

Additional requirement specific to this system: **an idempotence test**. Index twice, assert zero writes on the second pass and byte-identical retrieval results. Non-determinism here would silently poison every downstream session.

### 7.2 Golden query set (the acceptance test — operator to confirm per Q-06)

Each query has an expected source. A query passes if the correct chunk is in the top 3 **and** no superseded chunk contradicting it is returned as `current`.

| # | Query | Must retrieve | Must NOT surface as current |
|---|---|---|---|
| 1 | What is the graded ORB+Opt3 per-contract figure? | lessons log 2026-05-13 correction (~$1,088.50/yr/contract) | the `$10,885/yr per contract` reading in the 2026-04-28 entries |
| 2 | Why was production cut to ORB+Opt3? | lessons log 2026-04-28 (displacement, tri-module net-negative) | `flux-v1-development-roadmap.md` quad-module economics |
| 3 | What is the max sustainable qty rule? | phase-2-kickoff R(q) | — |
| 4 | What timezone is the NT8 export in? | lessons log 2026-04-27 (UTC) | 2026-04-26 DST entry's "source IS America/Chicago" rationale |
| 5 | When does Phase 1b start? | charter / lessons log 2026-04-30 (after Phase 1 gate, not parallel) | earlier "parallel track" framing |
| 6 | What are the Apex EOD constraints? | ai-project-instructions §7 ($3K trailing, $1K DLL, consistency rule) | — |
| 7 | Is the +$500 in R(q) the DLL? | phase-2-kickoff DLL-vs-buffer note (no) | — |
| 8 | What happened with M6 bracket re-arm? | lessons log 2026-04-28 second escalation | — |
| 9 | Which engine is trusted for backtests? | M4 / engine-provenance material | any bespoke fill-walker result |
| 10 | What is Wave 0 and has it completed? | current-working-plan (pinned, full text) | — |
| 11 | What are the current pre-registered hypotheses? | research-log via retrieval + working plan | — |
| 12 | Why was volume-crossover roll methodology abandoned? | lessons log 2026-04-26 | — |

Queries 1, 2, 4, and 5 are the ones that matter. They are all cases where the corpus contains a confident, well-written, **wrong** answer that a naive index will happily serve. If those four pass, the superseded-content machinery works. If any fails, the system is worse than no system, because it launders stale numbers through an authoritative-looking interface.

---

## 8. On deleting things (scope boundary)

Not in this spec. Nothing is deleted because "the DB has it" — the DB is a rebuildable index (§1.1), and `ai-project-instructions.md` §2 and §5 require explicit approval for removing artifacts and retaining failed-hypothesis research.

A cleanup pass is still worth doing, on separate grounds: dead code, superseded doc versions, notebooks that no longer run. That is a distinct proposal with its own operator review, after D8, judged on whether each artifact still earns its place. Git history is not a licence to delete, but it does mean removal is reversible.

The one cleanup this system genuinely enables: once §4.4 classification is complete, you'll have an explicit, reviewed map of what in the corpus is stale — which is the input to that later decision, not the decision itself.

---

## 9. Rules for Cursor

1. **No unilateral choices.** Anything not locked in §2 goes back to the operator. If the spec is silent, the answer is "ask," not "pick something sensible."
2. **Report at every milestone boundary and wait.** D1 finishing does not authorize D2.
3. **Flag any conflict between this spec and `ai-project-instructions.md`.** Those instructions win; the spec gets amended.
4. **Do not modify** the charter, kickoff, working plan, or lessons log. Propose entries per §6 of the AI instructions; the operator approves and commits.
5. **Do not touch** `src/quant_research/backtest/`, `statistics/`, `data/`, `modules/`, or anything under `NinjaTrader/`. The PCS is additive and isolated.
6. **Do not add dependencies** beyond the approved §2.1 list without asking.
7. **Do not claim "done"** without passing tests. "Wrote some code" is not done (`ai-project-instructions.md` §10).
8. **Push back** if something in this spec is wrong. It was drafted without the repo in front of it; the repo wins on facts.

---

## 10. Definition of done

The PCS is complete when:

- `docker compose up` + `pcs reindex --all` reconstructs the full index from a clean checkout, with no manual steps
- All golden queries (§7.2) pass, including the four superseded-content traps
- A fresh Cursor session, given only PCS access, correctly answers "what is the current program state and what is the next action?"
- Re-indexing is idempotent and provenance-complete
- The system is documented in `docs/` and a lessons-log entry is proposed covering what the corpus-contradiction problem taught

At that point Cursor reports **"PCS verified — ready to resume Phase 2"** and this workstream closes.

---

## 11. What this does not solve

Worth stating plainly so it isn't discovered later as a disappointment.

Retrieval does not make the corpus consistent — it makes inconsistency *visible and filterable*. The manifest (§4.4) is hand-maintained; if it isn't kept current, the index will confidently serve stale answers with a `current` label, which is a worse failure than having no index at all, because it carries false authority. The discipline that keeps it honest is the same discipline that keeps the lessons log honest. The tool doesn't supply it.

The genuine wins are narrower and real: chat reasoning becomes searchable instead of lost; every retrieved claim carries a commit SHA; and the four known contradiction traps stop being landmines.
