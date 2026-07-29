"""PCS MCP server (D6) — read-only tools over stdio (spec D-11, D-12, §6.1).

Exposes three read-only tools to a Cursor (or any MCP client) session:

* ``get_pinned_context`` — the five Tier-1 docs whole, with git SHA (no vectors).
* ``search`` — hybrid semantic+lexical retrieval, RRF-fused, status-filtered
  before fusion, with inline provenance and ``[SUPERSEDED by …]`` labels.
* ``status`` — latest index run + working-tree staleness.

Every tool wraps existing code (``pinned``/``retriever``/``indexer``); no
retrieval or ranking logic is duplicated here. Nothing writes to the repo or DB
(D-12). Launched by Cursor via ``.cursor/mcp.json`` as::

    uv run python -m quant_research.context.mcp_server

Run modes: as a module (``python -m``) it starts the stdio server. The tool
*functions* are importable and unit-tested without a transport.
"""

from __future__ import annotations

import psycopg
from mcp.server.fastmcp import FastMCP

from quant_research.context import pinned as pinned_mod
from quant_research.context import retriever as retriever_mod
from quant_research.context.indexer import IndexStatus, index_status

mcp = FastMCP("pcs")


# --------------------------------------------------------------------------- #
# Renderers (pure; unit-tested)
# --------------------------------------------------------------------------- #
def _render_pinned(ctx: pinned_mod.PinnedContext) -> str:
    parts: list[str] = []
    for doc in ctx.docs:
        dirty = " (dirty)" if doc.git_dirty else ""
        parts.append(
            f"===== PINNED: {doc.file_path} (git {doc.git_sha[:12]}{dirty}) =====\n\n{doc.text}"
        )
    out = "\n\n".join(parts)
    if ctx.missing:
        out += "\n\n[WARNING] pinned docs listed in §4.1 but missing: " + ", ".join(ctx.missing)
    return out or "no pinned documents found"


def _render_results(results: list[retriever_mod.SearchResult]) -> str:
    if not results:
        return "no results"
    blocks: list[str] = []
    for i, r in enumerate(results, start=1):
        entry = r.entry_date.isoformat() if r.entry_date else "-"
        header = (
            f"[{i}] score={r.score:.4f}  status={r.status}  file={r.file_path}  "
            f"date={entry}  git={r.git_sha[:12]}"
        )
        blocks.append(f"{header}\n{r.text}")
    return "\n\n---\n\n".join(blocks)


def _render_status(st: IndexStatus) -> str:
    if st.latest_run is None:
        return "no index runs yet; run 'pcs reindex --all'"
    run = st.latest_run
    dirty = " (dirty)" if run["git_dirty"] else ""
    lines = [
        f"latest run: {run['id']}  completed={run['completed_at']}  "
        f"git={run['git_sha'][:12]}{dirty}",
        f"  files_indexed={run['files_indexed']}  chunks_written={run['chunks_written']}",
        f"  chunk rows in index: {st.total_chunks}",
    ]
    if st.stale_files:
        lines.append(f"  STALE ({len(st.stale_files)} file(s) changed since index; run reindex):")
        lines.extend(f"    - {rel}" for rel in st.stale_files)
    else:
        lines.append("  index is up to date with the working tree")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Tools (read-only)
# --------------------------------------------------------------------------- #
@mcp.tool()
def get_pinned_context() -> str:
    """Return the Tier-1 pinned program docs in FULL, each with its git SHA.

    These are the current-state authorities (charter, phase-2 kickoff, working
    plan, agent instructions, response style). Loaded whole — never chunked or
    ranked. Call this whenever a task touches program state, direction, or
    constraints; the session-start index is only a table of contents.
    """
    return _render_pinned(pinned_mod.get_pinned_context())


@mcp.tool()
def search(query: str, top_k: int = 8, include_superseded: bool = False) -> str:
    """Search the Tier-2 corpus (lessons/research logs + method docs).

    Hybrid semantic + lexical retrieval, RRF-fused. By default only CURRENT
    content is returned. Set ``include_superseded=true`` to also see superseded
    versions (e.g. a corrected figure's original) — these arrive prefixed
    ``[SUPERSEDED by …]``. Each result carries breadcrumb, file, date, status,
    git SHA, and score inline. Historical/deprecated archive content is not
    returned.
    """
    try:
        results = retriever_mod.search(
            query, top_k=top_k, include_superseded=include_superseded
        )
    except psycopg.OperationalError as exc:
        return f"search unavailable - database: {str(exc).strip().splitlines()[0]}"
    return _render_results(results)


@mcp.tool()
def status() -> str:
    """Report the latest index run and whether any source file has drifted.

    Use this to check the index is fresh (git SHA + timestamp) before trusting
    search results, and to see which files need a reindex.
    """
    try:
        return _render_status(index_status())
    except psycopg.OperationalError as exc:
        return f"status unavailable - database: {str(exc).strip().splitlines()[0]}"


def main() -> None:
    """Start the stdio MCP server (entry point for ``python -m``)."""
    mcp.run()


if __name__ == "__main__":
    main()
