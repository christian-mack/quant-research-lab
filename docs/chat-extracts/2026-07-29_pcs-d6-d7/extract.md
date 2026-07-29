---
chat_date: 2026-07-29
topic: PCS D6–D7 build decisions
decisions: structured decision records (Q-02)
status: mixed  # per-entry classification in context-manifest.yml
source_chat: cursor:2026-07-29-d6-hook-diagnosis; cursor:2026-07-29-d7-golden-scoring
---

# PCS D6–D7 decision records

Structured decision records extracted from Cursor PCS build sessions. Not free-form fact summaries.

## 2026-07-29 — q02-decision-records-not-facts

**Decision:** D8 chat extraction target is structured decision records, not important-fact prose summaries.

**Alternatives considered:** Hand-curated markdown summaries; raw transcript indexing as current; Anthropic bulk export to `data/context/chats/`.

**Rationale:** Facts get overturned; a misread can live in chat for weeks. Decision records with rationale stay accurate when reversed and match manifest discipline.

**Type:** committed | **Status:** current

## 2026-07-18 — pcs-d6-hook-primary-load-bearing

**Decision:** PCS sessionStart hook deterministically injects the compact pinned index; alwaysApply rule is supplement and cloud fallback.

**Alternatives considered:** Rule-only bootstrap; MCP-only with no session injection.

**Rationale:** Original D6 integration design (context-system-implementation-spec §6.1, verified 2026-07-18).

**Type:** committed | **Status:** superseded → 2026-07-29 pcs-d6-rule-primary-not-hook

## 2026-07-29 — pcs-d6-rule-primary-not-hook

**Decision:** PCS primary pinned-load path is alwaysApply rule + `get_pinned_context()`; sessionStart hook is best-effort only.

**Supersedes:** pcs-d6-hook-primary-load-bearing (2026-07-18 hook-primary framing).

**Alternatives considered:** sessionStart hook as deterministic primary; MCP-only with no rule.

**Rationale:** Hook stdout not captured on Windows (Cursor 3.13.25); rule+tool works in every fresh session tested and ports to Claude Code/app.

**Type:** committed | **Status:** current

## 2026-07-29 — pcs-hook-venv-direct-windows

**Decision:** `hooks.json` invokes `.\.venv\Scripts\python.exe` directly (repo-root-relative); not bare `python` or `uv run`.

**Rationale:** Cursor hook subprocess captures empty stdout when script re-execs; `uv` unreliable in hook PATH.

**Type:** committed | **Status:** current

## 2026-07-29 — pcs-hook-test-not-capture-acceptance

**Decision:** `pcs hook-test` is not acceptance for sessionStart delivery; operator verifies Hooks Execution Log merge line.

**Rationale:** hook-test runs in a normal shell and is blind to Cursor stdout capture failures (Case D).

**Type:** committed | **Status:** current

## 2026-07-29 — pcs-d7-lexical-normalize-identifiers

**Decision:** Retriever applies uniform `_normalize_lexical_query()` for compound identifiers before tsquery — not a Q1 special case.

**Rationale:** `websearch_to_tsquery` treats `+` and hyphens as operators; corpus-absent question words zero out lexical arm.

**Type:** committed | **Status:** current

## 2026-07-29 — pcs-tier1-via-pinned-not-search

**Decision:** Golden queries for Tier-1 docs use `get_pinned_context()`, not `search()`.

**Rationale:** Spec §4.1 / D-06: Tier-1 pinned docs are never chunk-retrieved.

**Type:** committed | **Status:** current

## 2026-07-18 — pcs-d1-d7-single-commit-batch

**Decision:** D1–D7 landed as a single commit (`d23ead6`); milestone-split was intended per ai-project-instructions §1 but not executed.

**Rationale:** Process deviation — commits batched during the build, then pushed for durability; not a deliberate architectural choice.

**Type:** committed | **Status:** historical (process record, not current guidance)

## 2026-07-29 — pcs-workspaceopen-considered-not-adopted

**Decision:** workspaceOpen hook considered for pinned index injection; not adopted.

**Rationale:** workspaceOpen surfaced during diagnosis as a separate Cursor lifecycle event — not a path we chose.

**Type:** tentative | **Status:** historical
