"""Tier-1 pinned-context loader (spec §4.1, D-06).

The pinned corpus is the program's *current-state* set. An agent session loads
these documents **whole, every time** — no chunking, no embedding, no ranking.

This module is deliberately isolated from the retrieval stack: it imports only
:mod:`quant_research.context.config` (filesystem + git) and the Tier-1 list from
:mod:`quant_research.context.manifest` (YAML/config only — no DB, no vectors),
never the chunker, embedder, indexer, or any DB/pgvector code. Routing pinned
retrieval through the vector path would be a regression against the tier design
(§4.1 / D-06), so the separation is structural, not conventional.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quant_research.context.config import git_sha_and_dirty, repo_root
from quant_research.context.manifest import (
    MANIFEST_PATH_REL,
    TIER1_PINNED_DOCS,
    load_manifest,
)

# Tier-1 pinned documents (spec §4.1) — single source of truth in the manifest
# module, which also validates their classification and tier exclusivity.
PINNED_DOCS: tuple[str, ...] = TIER1_PINNED_DOCS


@dataclass(frozen=True)
class PinnedDoc:
    """One Tier-1 document returned whole, with commit provenance."""

    file_path: str
    git_sha: str
    git_dirty: bool
    text: str


@dataclass(frozen=True)
class PinnedContext:
    """Full pinned corpus plus any configured-but-missing files (surfaced, not hidden)."""

    docs: list[PinnedDoc]
    missing: list[str]


@dataclass(frozen=True)
class PinnedIndexEntry:
    """One line of the compact pinned index (table of contents, not full text)."""

    file_path: str
    title: str
    purpose: str
    git_sha: str


def _first_heading(text: str) -> str:
    """Return the document's first heading/non-empty line as a title."""
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").lstrip(">").strip()
        if stripped:
            return stripped
    return ""


def get_pinned_index(root: Path | None = None) -> list[PinnedIndexEntry]:
    """Return a compact index of the Tier-1 docs (title + one-line purpose + SHA).

    This is what the ``sessionStart`` hook injects — a table of contents, NOT the
    full text. The one-line purpose is the manifest ``justification`` for each
    pinned doc; the agent pulls the whole document on demand via
    :func:`get_pinned_context` when a task actually touches program state.
    """
    root = root or repo_root()
    sha, _ = git_sha_and_dirty(root)
    manifest = load_manifest(root / MANIFEST_PATH_REL)
    pinned_blocks = manifest.get("pinned") or {}
    entries: list[PinnedIndexEntry] = []
    for rel in PINNED_DOCS:
        path = root / rel
        if not path.is_file():
            continue
        block = pinned_blocks.get(rel) or {}
        purpose = str(block.get("justification") or "").strip()
        entries.append(
            PinnedIndexEntry(
                file_path=rel,
                title=_first_heading(path.read_text(encoding="utf-8")),
                purpose=purpose,
                git_sha=sha,
            )
        )
    return entries


def render_pinned_index(entries: list[PinnedIndexEntry]) -> str:
    """Render the compact index as the text a ``sessionStart`` hook injects."""
    lines = [
        "# PCS pinned context — INDEX ONLY (table of contents, not the full docs).",
        "# These Tier-1 docs define current program state. This is a summary; for any",
        "# decision touching program state, load the full doc via the PCS",
        "# get_pinned_context() tool. (Cursor MCP server: pcs)",
        "",
    ]
    for e in entries:
        lines.append(f"- {e.file_path}  (git {e.git_sha[:12]}) — {e.title}")
        if e.purpose:
            lines.append(f"    purpose: {e.purpose}")
    return "\n".join(lines)


def get_pinned_context(root: Path | None = None) -> PinnedContext:
    """Return the Tier-1 docs whole, with the current git SHA.

    Missing files are reported in :attr:`PinnedContext.missing` rather than
    silently dropped or crashing the whole call — a pinned doc listed in §4.1 but
    absent from the repo is an operator-facing discrepancy (a Q-01 decision:
    create it, or amend the pinned list), not something to paper over.
    """
    root = root or repo_root()
    sha, dirty = git_sha_and_dirty(root)
    docs: list[PinnedDoc] = []
    missing: list[str] = []
    for rel in PINNED_DOCS:
        path = root / rel
        if not path.is_file():
            missing.append(rel)
            continue
        docs.append(PinnedDoc(rel, sha, dirty, path.read_text(encoding="utf-8")))
    return PinnedContext(docs=docs, missing=missing)
