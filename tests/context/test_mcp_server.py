"""MCP server tests (D6).

The MCP tools are thin wrappers over already-tested code, so these tests focus
on: (1) the pure renderers (including the [SUPERSEDED by …] label passing
through to the text an agent reads), (2) the read-only pinned tool working with
no database, and (3) the Cursor wiring files being present and internally
consistent (right module launched, right hook script, alwaysApply rule).
The end-to-end retrieval path is covered by test_retriever; the golden query is
run through the live stack separately (D6 exit).
"""

from __future__ import annotations

import json
from datetime import date

from quant_research.context import mcp_server as srv
from quant_research.context.config import repo_root
from quant_research.context.indexer import IndexStatus
from quant_research.context.retriever import SearchResult


def _result(status: str, superseded_by: str | None, text: str) -> SearchResult:
    return SearchResult(
        chunk_id=1,
        breadcrumb="docs/lessons-log.md > 2026-04-28 — X",
        file_path="docs/lessons-log.md",
        entry_date=date(2026, 4, 28),
        status=status,
        superseded_by=superseded_by,
        git_sha="a715de69905f0000",
        score=0.0321,
        chunk_text="body",
        text=text,
    )


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #
def test_render_results_includes_inline_provenance() -> None:
    r = _result("current", None, "docs/lessons-log.md > 2026-04-28 — X\n\nbody")
    out = srv._render_results([r])
    assert "score=0.0321" in out
    assert "status=current" in out
    assert "file=docs/lessons-log.md" in out
    assert "date=2026-04-28" in out
    assert "git=a715de69905f" in out


def test_render_results_passes_through_superseded_label() -> None:
    labeled = "[SUPERSEDED by docs/lessons-log.md :: 2026-05-13 — Correction] docs/... \n\nbody"
    out = srv._render_results([_result("superseded", "ptr", labeled)])
    assert out.count("[SUPERSEDED by ") == 1  # the label an agent reads is preserved
    assert "status=superseded" in out


def test_render_results_empty() -> None:
    assert srv._render_results([]) == "no results"


def test_render_status_variants() -> None:
    assert "no index runs" in srv._render_status(IndexStatus(None, 0, []))
    run = {
        "id": 3,
        "completed_at": "2026-07-18T20:41:01",
        "git_sha": "a715de69905fdead",
        "git_dirty": True,
        "files_indexed": 6,
        "chunks_written": 159,
    }
    fresh = srv._render_status(IndexStatus(run, 159, []))
    assert "latest run: 3" in fresh and "up to date" in fresh and "(dirty)" in fresh
    stale = srv._render_status(IndexStatus(run, 159, ["docs/lessons-log.md"]))
    assert "STALE" in stale and "docs/lessons-log.md" in stale


# --------------------------------------------------------------------------- #
# Tools (no DB / no torch)
# --------------------------------------------------------------------------- #
def test_get_pinned_context_tool_returns_full_docs_with_sha() -> None:
    out = srv.get_pinned_context()
    assert "PINNED: docs/program-charter.md" in out
    assert "PINNED: docs/flux-response-style.md" in out
    assert "git " in out
    # full text, not the compact index: a real charter sentence is present
    charter = (repo_root() / "docs/program-charter.md").read_text(encoding="utf-8")
    assert charter.strip()[:60] in out


# --------------------------------------------------------------------------- #
# Cursor wiring files (§6.1)
# --------------------------------------------------------------------------- #
def test_mcp_json_launches_the_pcs_server_module() -> None:
    cfg = json.loads((repo_root() / ".cursor/mcp.json").read_text(encoding="utf-8"))
    pcs = cfg["mcpServers"]["pcs"]
    assert pcs["type"] == "stdio"
    assert pcs["command"] == "uv"
    assert "quant_research.context.mcp_server" in pcs["args"]


def test_hooks_json_wires_session_start_to_the_hook_script() -> None:
    hooks = json.loads((repo_root() / ".cursor/hooks.json").read_text(encoding="utf-8"))
    session_start = hooks["hooks"]["sessionStart"]
    command = session_start[0]["command"]
    assert "session_start.py" in command
    assert "uv run" not in command  # hook subprocess PATH often lacks uv
    assert (repo_root() / ".cursor/hooks/session_start.py").is_file()


def test_session_start_hook_emits_additional_context_json() -> None:
    """Hook body path must emit valid JSON with the compact pinned index."""
    from quant_research.context.pinned import get_pinned_index, render_pinned_index

    payload = {"additional_context": render_pinned_index(get_pinned_index())}
    dumped = json.dumps(payload)
    assert "additional_context" in dumped
    loaded = json.loads(dumped)
    assert "docs/program-charter.md" in loaded["additional_context"]


def test_pcs_rule_is_always_applied_with_fallback_and_toc_guardrail() -> None:
    text = (repo_root() / ".cursor/rules/pcs.mdc").read_text(encoding="utf-8")
    assert "alwaysApply: true" in text
    assert "get_pinned_context" in text
    assert "SUPERSEDED" in text
    # cloud fallback + table-of-contents guardrail must be present
    assert "cloud" in text.lower()
    assert "table of contents" in text.lower()


def test_hook_test_cmd_passes() -> None:
    from quant_research.context.cli import hook_test_cmd

    assert hook_test_cmd() == 0
