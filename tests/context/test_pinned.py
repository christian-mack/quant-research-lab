"""Pinned Tier-1 loader tests (D5, spec §4.1 / D-06).

Two things matter here:

* **Round-trip** — each existing pinned doc is returned whole (byte-for-byte the
  file) with a git SHA, and any configured-but-missing file is surfaced (not
  silently dropped or crashed).
* **Structural separation** — the pinned path never imports the chunker, embedder,
  indexer, or any DB/pgvector code. Routing pinned retrieval through the vector
  path would be a tier-design regression (D-06); this test fails loudly if it ever
  does.
"""

from __future__ import annotations

import ast

from quant_research.context.config import repo_root
from quant_research.context.manifest import (
    TIER1_PINNED_DOCS,
    TIER2_ENTRY_LOGS,
    resolve_whole_file_docs,
)
from quant_research.context.pinned import (
    PINNED_DOCS,
    get_pinned_context,
    get_pinned_index,
    render_pinned_index,
)

FORBIDDEN_IMPORT_SUBSTRINGS = ("chunker", "embedder", "indexer", "retriever", "psycopg", "pgvector")


def test_pinned_docs_list_matches_spec_count() -> None:
    assert len(PINNED_DOCS) == 5  # spec §4.1
    assert "docs/flux-response-style.md" in PINNED_DOCS


def test_all_pinned_docs_round_trip_whole_with_sha_and_none_missing() -> None:
    root = repo_root()
    ctx = get_pinned_context()
    assert ctx.missing == []  # every §4.1 doc now exists; the warning must be quiet
    returned = {d.file_path for d in ctx.docs}
    assert returned == set(PINNED_DOCS)
    for doc in ctx.docs:
        assert doc.text == (root / doc.file_path).read_text(encoding="utf-8")  # whole, verbatim
        assert doc.git_sha  # provenance present


def test_flux_response_style_is_pinned_not_tier2() -> None:
    """flux-response-style.md is pinned-only; it must NOT be in any Tier-2 path."""
    rel = "docs/flux-response-style.md"
    assert rel in PINNED_DOCS
    tier2 = set(resolve_whole_file_docs(repo_root())) | set(TIER2_ENTRY_LOGS)
    assert rel not in tier2  # never chunked/embedded
    # And no pinned doc may leak into the Tier-2 corpus.
    assert not (set(TIER1_PINNED_DOCS) & tier2)


def test_pinned_works_without_a_database() -> None:
    # No DB fixture, no connection: pinned must resolve purely from files + git.
    ctx = get_pinned_context()
    assert ctx.docs  # the four real Tier-1 docs load with the container down


def test_pinned_index_is_compact_toc_with_title_purpose_and_sha() -> None:
    entries = get_pinned_index()
    assert {e.file_path for e in entries} == set(PINNED_DOCS)
    for e in entries:
        assert e.title  # first heading extracted
        assert e.purpose  # sourced from the manifest justification
        assert e.git_sha


def test_render_pinned_index_is_index_not_full_text() -> None:
    root = repo_root()
    text = render_pinned_index(get_pinned_index())
    # It names every pinned doc...
    for rel in PINNED_DOCS:
        assert rel in text
    # ...labels itself an index / table of contents (guardrail against summary-leakage)...
    assert "INDEX ONLY" in text or "table of contents" in text
    assert "get_pinned_context()" in text
    # ...and does NOT contain the full body of the largest pinned doc.
    charter = (root / "docs/program-charter.md").read_text(encoding="utf-8")
    assert len(text) < len(charter)  # the index is far smaller than one full doc


def test_pinned_module_does_not_import_vector_or_db_stack() -> None:
    """Static guarantee that pinned is a separate, non-vector code path."""
    src = (repo_root() / "src/quant_research/context/pinned.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for mod in imported:
        assert not any(bad in mod for bad in FORBIDDEN_IMPORT_SUBSTRINGS), (
            f"pinned.py must not import the vector/DB stack, found: {mod}"
        )
