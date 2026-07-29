"""Unit tests for the PCS structural chunker (D3, spec §4.3 + §4.4).

The load-bearing tests are the split_required ones: they prove the §4.4
contradiction trap is defused at chunk level — the ~$10,885/contract misread
lands in a ``superseded`` chunk while the live displacement / bracket-re-arm
narrative stays ``current`` (the D7 golden-query #1 trap and #2/#8 preservation
acceptance test operates on retrieval; this is its chunk-level precondition).
"""

from __future__ import annotations

from datetime import date

import pytest

from quant_research.context.chunker import (
    ChunkConfig,
    ChunkerError,
    SplitSpec,
    approx_token_count,
    chunk_entry,
    chunk_whole_file,
    extract_entry_date,
    iter_log_entries,
)
from quant_research.context.config import repo_root
from quant_research.context.manifest import (
    MANIFEST_PATH_REL,
    iter_split_required,
    load_manifest,
)


# --------------------------------------------------------------------------- #
# Primitives
# --------------------------------------------------------------------------- #
def test_extract_entry_date_parses_and_rejects() -> None:
    assert extract_entry_date("2026-04-28 — Production cut") == date(2026, 4, 28)
    assert extract_entry_date("No date here") is None
    assert extract_entry_date("2026-13-40 — impossible") is None


def test_approx_token_count_is_deterministic_and_nonzero() -> None:
    text = "ORB+Opt3: $10,885/yr per contract."
    assert approx_token_count(text) == approx_token_count(text)
    assert approx_token_count(text) > 0
    assert approx_token_count("") == 0


# --------------------------------------------------------------------------- #
# Structural splitting (rules 1-3, 5, 6)
# --------------------------------------------------------------------------- #
def test_small_entry_is_one_verbatim_chunk() -> None:
    body = "**Finding:** A short finding.\n\n**Implication:** Keep it together."
    chunks = chunk_entry("docs/lessons-log.md", "2026-01-01 — Small", body, "current")
    assert len(chunks) == 1
    assert chunks[0].chunk_text == body  # verbatim, unsplit
    assert chunks[0].entry_date == date(2026, 1, 1)
    assert chunks[0].status == "current"
    assert chunks[0].superseded_by is None


def test_breadcrumb_is_prepended_to_embed_text_only() -> None:
    body = "Body text."
    chunks = chunk_entry("docs/lessons-log.md", "2026-01-01 — X", body, "current")
    c = chunks[0]
    assert c.breadcrumb == "docs/lessons-log.md > 2026-01-01 — X"
    assert c.embed_text.startswith(c.breadcrumb)
    assert body in c.embed_text
    assert c.breadcrumb not in c.chunk_text  # chunk_text is source only


def test_oversized_entry_splits_on_headings_then_paragraphs() -> None:
    cfg = ChunkConfig(max_tokens=40, min_tokens=1)
    body = (
        "### Section A\n\n"
        + "alpha " * 40
        + "\n\n### Section B\n\n"
        + "beta " * 40
    )
    chunks = chunk_entry("docs/research-log.md", "2026-01-01 — Big", body, "current", config=cfg)
    assert len(chunks) >= 2
    # sequential, no gaps (rule 6: no overlap; indices contiguous)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_table_is_atomic_even_when_oversized() -> None:
    cfg = ChunkConfig(max_tokens=5, min_tokens=1)
    table = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |"
    chunks = chunk_entry("docs/research-log.md", "2026-01-01 — T", table, "current", config=cfg)
    # the whole table survives intact in exactly one chunk
    holding = [c for c in chunks if "| 1 | 2 |" in c.chunk_text]
    assert len(holding) == 1
    assert "| 5 | 6 |" in holding[0].chunk_text


def test_code_fence_is_atomic_even_when_oversized() -> None:
    cfg = ChunkConfig(max_tokens=5, min_tokens=1)
    code = "```python\nx = 1\ny = 2\nz = x + y + 1000000\n```"
    chunks = chunk_entry("docs/research-log.md", "2026-01-01 — C", code, "current", config=cfg)
    holding = [c for c in chunks if "x = 1" in c.chunk_text]
    assert len(holding) == 1
    assert "z = x + y" in holding[0].chunk_text  # not split mid-fence


def test_tiny_trailing_chunk_merges_forward() -> None:
    cfg = ChunkConfig(max_tokens=30, min_tokens=12)
    body = "alpha " * 30 + "\n\ntiny tail"
    chunks = chunk_entry("docs/research-log.md", "2026-01-01 — M", body, "current", config=cfg)
    # the tiny tail is not emitted as its own sub-min chunk
    assert all(c.token_count >= cfg.min_tokens or len(chunks) == 1 for c in chunks)
    assert any("tiny tail" in c.chunk_text for c in chunks)


# --------------------------------------------------------------------------- #
# Boundary cases (ai-project-instructions §4)
# --------------------------------------------------------------------------- #
def test_empty_body_yields_no_chunks() -> None:
    assert chunk_entry("docs/lessons-log.md", "2026-01-01 — Empty", "   \n\n", "current") == []


def test_whole_file_preamble_before_first_heading_is_kept() -> None:
    text = "# Title\n\nPreamble sentence.\n\n## First\n\nSection one body."
    chunks = chunk_whole_file("docs/doc.md", text, "historical")
    assert any("Preamble sentence." in c.chunk_text for c in chunks)
    assert any(c.breadcrumb.endswith("> First") for c in chunks)
    assert all(c.status == "historical" for c in chunks)


def test_iter_log_entries_delimits_on_dated_h2_only() -> None:
    text = (
        "# Lessons Log\n\n"
        "## 2026-02-02 — Second\n\nBody two.\n\n### sub stays inside\n\ntail.\n\n---\n\n"
        "## 2026-01-01 — First\n\nBody one.\n\n"
        "## Entry template (ignored)\n\nnope.\n"
    )
    entries = iter_log_entries(text)
    headings = [h for h, _ in entries]
    assert headings == ["2026-02-02 — Second", "2026-01-01 — First"]
    assert "### sub stays inside" in entries[0][1]
    assert not entries[0][1].endswith("---")  # trailing separator stripped


# --------------------------------------------------------------------------- #
# split_required carve (§4.4) — synthetic
# --------------------------------------------------------------------------- #
def test_split_carves_anchor_into_superseded_chunk() -> None:
    body = (
        "**Finding:** The live displacement narrative stays.\n"
        "- stale: $10,885/yr per contract\n"
        "**Implication:** Also live."
    )
    spec = SplitSpec(
        anchors=("- stale: $10,885/yr per contract",),
        superseded_by="docs/lessons-log.md :: 2026-05-13 — Correction",
    )
    chunks = chunk_entry(
        "docs/lessons-log.md", "2026-04-28 — Split me", body, "current", split=spec
    )
    current = [c for c in chunks if c.status == "current"]
    superseded = [c for c in chunks if c.status == "superseded"]
    assert len(superseded) == 1
    assert "$10,885/yr per contract" in superseded[0].chunk_text
    assert superseded[0].superseded_by == spec.superseded_by
    # the misread must NOT remain on any current chunk
    assert all("$10,885/yr per contract" not in c.chunk_text for c in current)
    # the live narrative is preserved on a current chunk
    assert any("displacement narrative" in c.chunk_text for c in current)
    assert any("Also live." in c.chunk_text for c in current)


def test_split_anchor_absent_fails_loudly() -> None:
    spec = SplitSpec(anchors=("not present in body",), superseded_by="x")
    with pytest.raises(ChunkerError, match="split_anchor not found"):
        chunk_entry("docs/lessons-log.md", "2026-01-01 — X", "some body", "current", split=spec)


def test_chunk_indices_contiguous_across_split() -> None:
    body = "keep A\n\n- drop this stale line\n\nkeep B"
    spec = SplitSpec(anchors=("- drop this stale line",), superseded_by="ptr")
    chunks = chunk_entry("docs/lessons-log.md", "2026-01-01 — X", body, "current", split=spec)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


# --------------------------------------------------------------------------- #
# split_required carve (§4.4) — REAL manifest + REAL lessons-log (D3 acceptance)
# --------------------------------------------------------------------------- #
def _real_split_entries() -> dict[str, tuple[str, str]]:
    """Return {heading: (entry_body, superseded_by)} for real split_required entries."""
    root = repo_root()
    manifest = load_manifest(root / MANIFEST_PATH_REL)
    specs = {
        sr.location.split(" :: ", 1)[1]: sr
        for sr in iter_split_required(manifest)
        if sr.location.startswith("docs/lessons-log.md")
    }
    log_text = (root / "docs/lessons-log.md").read_text(encoding="utf-8")
    bodies = dict(iter_log_entries(log_text))
    return {h: (bodies[h], specs[h]) for h in specs}


@pytest.mark.parametrize(
    "heading_key",
    [
        "2026-04-28 — Production cut to ORB+Opt3; tri-module economics invalidated on 6-year data",
        "2026-04-28 — M6 second escalation: defensive bracket re-arm, dollar gap widened (honest)",
    ],
)
def test_real_split_moves_misread_off_current_surface(heading_key: str) -> None:
    entries = _real_split_entries()
    body, sr = entries[heading_key]
    spec = SplitSpec(anchors=sr.anchors, superseded_by=sr.superseded_by)
    chunks = chunk_entry("docs/lessons-log.md", heading_key, body, "current", split=spec)

    current = [c for c in chunks if c.status == "current"]
    superseded = [c for c in chunks if c.status == "superseded"]
    assert superseded, "split must produce at least one superseded chunk"

    # Trap: the $10,885/contract misread must NOT appear on any current chunk.
    assert all("$10,885/yr per contract" not in c.chunk_text for c in current)
    assert all("NT8 ≈$10,885" not in c.chunk_text for c in current)
    # ...but it MUST be captured in the superseded chunk, pointing at the correction.
    assert any("10,885" in c.chunk_text for c in superseded)
    assert all(c.superseded_by and "2026-05-13" in c.superseded_by for c in superseded)


def test_real_m6_preserves_bracket_rearm_narrative_as_current() -> None:
    entries = _real_split_entries()
    body, sr = entries[
        "2026-04-28 — M6 second escalation: defensive bracket re-arm, dollar gap widened (honest)"
    ]
    spec = SplitSpec(anchors=sr.anchors, superseded_by=sr.superseded_by)
    chunks = chunk_entry(
        "docs/lessons-log.md", "2026-04-28 — M6 second escalation", body, "current", split=spec
    )
    current_text = "\n".join(c.chunk_text for c in chunks if c.status == "current")
    # Preservation (golden query #8): the honest re-arm narrative + ~$1,014 stay current.
    assert "defensive re-arm" in current_text
    assert "$1,014" in current_text
    assert "391" in current_text  # trade-count shift narrative


def test_real_production_cut_preserves_displacement_narrative_as_current() -> None:
    entries = _real_split_entries()
    body, sr = entries[
        "2026-04-28 — Production cut to ORB+Opt3; tri-module economics invalidated on 6-year data"
    ]
    spec = SplitSpec(anchors=sr.anchors, superseded_by=sr.superseded_by)
    chunks = chunk_entry(
        "docs/lessons-log.md", "2026-04-28 — Production cut", body, "current", split=spec
    )
    current_text = "\n".join(c.chunk_text for c in chunks if c.status == "current")
    superseded_text = "\n".join(c.chunk_text for c in chunks if c.status == "superseded")
    # Preservation (golden query #2): why production was cut (displacement) stays current.
    assert "displacement" in current_text
    assert "Momentum" in current_text
    # Preservation (income-gap query): the stale FIGURE is carved out...
    assert "~$8K/yr" not in current_text
    assert "$8K" in superseded_text  # ...to the superseded chunk, not deleted
    # ...but the load-bearing income-gap CLAIM built around it stays current.
    assert "significantly trails the program's $65K-$100K per-account target" in current_text
    assert "explicit research priority" in current_text
    # sub-sentence carve leaves a grammatical remainder (no doubled space, no empty parens)
    assert "projection significantly trails" in current_text
    assert "()" not in current_text
