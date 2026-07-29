"""Structural markdown chunker (spec §4.3) — pure functions, no I/O.

The chunker turns a classified corpus unit (a whole-file doc, or one dated
lessons/research-log entry) into a list of :class:`Chunk` records ready for the
embedder and indexer. It performs **no** database, filesystem, or network access:
callers pass the text and the manifest classification in, and get chunks out.

Locked rules (spec §4.3):

1. Split on the nearest enclosing markdown heading.
2. If a chunk exceeds ``max_tokens`` (1200), split on sub-headings, then paragraph
   boundaries — never mid-sentence, never mid-table, never mid-code-fence.
3. If a chunk is under ``min_tokens`` (80), merge it forward into the next sibling.
4. Prepend a breadcrumb (``{file_path} > {heading} [> {subheading}]``) to every
   chunk's ``embed_text``; dated entries carry the date in the heading.
5. Tables and fenced code blocks are atomic — never split, even if oversized.
6. No overlap.

Superseded-content splitting (spec §4.4): a manifest entry flagged
``split_required`` carries one or more verbatim ``split_anchor`` spans that must be
carved out of the ``current`` narrative into their own ``superseded`` chunk. This is
the mechanism that keeps golden-query #1 (the ~$10,885/contract misread must NOT
surface as current) from breaking golden-query #2/#8 (the live displacement /
bracket-re-arm narrative must still retrieve). The carve is deterministic: the
anchor is a literal substring; if it is not found the chunker fails loudly.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

MAX_TOKENS = 1200
MIN_TOKENS = 80

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_DATE_PREFIX_RE = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\b")
# Approximate BPE tokens with word + standalone-punctuation counting. Deterministic
# and dependency-free; the indexer may inject the real bge tokenizer for exactness.
_TOKEN_RE = re.compile(r"\w+|[^\w\s]")


class ChunkerError(ValueError):
    """Raised on a structural precondition the chunker refuses to paper over."""


def approx_token_count(text: str) -> int:
    """Return a deterministic, dependency-free approximate token count."""
    return len(_TOKEN_RE.findall(text))


@dataclass(frozen=True)
class SplitSpec:
    """Verbatim spans to carve into a ``superseded`` chunk (spec §4.4)."""

    anchors: tuple[str, ...]
    superseded_by: str


@dataclass(frozen=True)
class ChunkConfig:
    """Chunker knobs. ``token_counter`` is injectable for exact tokenisation."""

    max_tokens: int = MAX_TOKENS
    min_tokens: int = MIN_TOKENS
    token_counter: Callable[[str], int] = field(default=approx_token_count)

    def count(self, text: str) -> int:
        return self.token_counter(text)


@dataclass(frozen=True)
class Chunk:
    """One indexable unit. Mirrors the ``pcs_chunk`` columns (spec §5.1)."""

    chunk_index: int
    breadcrumb: str
    entry_date: date | None
    chunk_text: str
    embed_text: str
    token_count: int
    status: str
    superseded_by: str | None


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def extract_entry_date(heading: str) -> date | None:
    """Return the leading ``YYYY-MM-DD`` of a dated heading, or None."""
    m = _DATE_PREFIX_RE.match(heading)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _make_embed_text(breadcrumb: str, chunk_text: str) -> str:
    """Breadcrumb-prefixed text that is actually embedded (rule 4)."""
    return f"{breadcrumb}\n\n{chunk_text}"


_DATED_ENTRY_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2}\b.*)$")


def iter_log_entries(text: str) -> list[tuple[str, str]]:
    """Split an append-only log into ``(heading, body)`` per dated ``##`` entry.

    Entries run from one dated ``## YYYY-MM-DD`` heading to the next level-2
    heading (dated or not). Deeper (``###``) headings stay inside the body. A
    trailing ``---`` separator is stripped. Pure; the indexer feeds each body to
    :func:`chunk_entry`.
    """
    lines = text.split("\n")
    entries: list[tuple[str, str]] = []
    heading: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if heading is None:
            return
        body = "\n".join(buf).strip()
        if body.endswith("---"):
            body = body[:-3].strip()
        entries.append((heading, body))

    for line in lines:
        m = _DATED_ENTRY_RE.match(line)
        if m:
            flush()
            heading = m.group(1).strip()
            buf = []
            continue
        hm = _HEADING_RE.match(line)
        if hm and len(hm.group(1)) == 2 and heading is not None:
            flush()  # a non-dated ## ends the current entry
            heading = None
            buf = []
            continue
        if heading is not None:
            buf.append(line)
    flush()
    return entries


@dataclass
class _Block:
    kind: str  # "heading" | "table" | "code" | "para"
    text: str
    atomic: bool
    level: int = 0  # heading level, else 0


def _segment_blocks(text: str) -> list[_Block]:
    """Segment markdown into structural blocks, keeping tables/code atomic."""
    lines = text.split("\n")
    blocks: list[_Block] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            start = i
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                i += 1
            if i < n:
                i += 1  # include closing fence
            blocks.append(_Block("code", "\n".join(lines[start:i]), atomic=True))
            continue
        if line.lstrip().startswith("|"):
            start = i
            while i < n and lines[i].lstrip().startswith("|"):
                i += 1
            blocks.append(_Block("table", "\n".join(lines[start:i]), atomic=True))
            continue
        hm = _HEADING_RE.match(line)
        if hm:
            blocks.append(_Block("heading", line, atomic=False, level=len(hm.group(1))))
            i += 1
            continue
        if stripped == "":
            i += 1
            continue
        start = i
        while i < n:
            nxt = lines[i]
            if (
                nxt.strip() == ""
                or _HEADING_RE.match(nxt)
                or nxt.lstrip().startswith("|")
                or nxt.strip().startswith("```")
            ):
                break
            i += 1
        blocks.append(_Block("para", "\n".join(lines[start:i]), atomic=False))
    return blocks


def _pack_blocks(blocks: list[_Block], config: ChunkConfig) -> list[str]:
    """Greedy-pack blocks under max_tokens; atomic blocks never split (rules 2,5)."""
    packed: list[str] = []
    current: list[str] = []
    current_tokens = 0

    def flush() -> None:
        nonlocal current, current_tokens
        if current:
            packed.append("\n\n".join(current))
            current = []
            current_tokens = 0

    for block in blocks:
        btok = config.count(block.text)
        if block.atomic and btok > config.max_tokens:
            flush()
            packed.append(block.text)  # atomic, stands alone even if oversized
            continue
        if current and current_tokens + btok > config.max_tokens:
            flush()
        current.append(block.text)
        current_tokens += btok
    flush()
    return _merge_small_forward(packed, config)


def _merge_small_forward(chunks: list[str], config: ChunkConfig) -> list[str]:
    """Merge a sub-min chunk forward into its next sibling (rule 3)."""
    if len(chunks) <= 1:
        return chunks
    out: list[str] = []
    carry: str | None = None
    for text in chunks:
        merged = text if carry is None else f"{carry}\n\n{text}"
        if config.count(merged) < config.min_tokens:
            carry = merged
        else:
            out.append(merged)
            carry = None
    if carry is not None:  # trailing tiny chunk: append to last, or stand alone
        if out:
            out[-1] = f"{out[-1]}\n\n{carry}"
        else:
            out.append(carry)
    return out


def _split_text(text: str, config: ChunkConfig) -> list[str]:
    """Return one verbatim chunk when small enough, else structurally split."""
    body = text.strip("\n")
    if not body.strip():
        return []
    if config.count(body) <= config.max_tokens:
        return [body]
    return _pack_blocks(_segment_blocks(body), config)


def _carve_anchors(text: str, anchors: tuple[str, ...]) -> tuple[str, str]:
    """Remove each verbatim anchor span from ``text``.

    Returns ``(kept_text, stale_text)``. Fails loudly if any anchor is absent —
    a missing anchor means the source changed and the split spec is stale (§4.4:
    unclassified/mis-specified content must not silently enter the index).
    """
    kept = text
    stale_parts: list[str] = []
    for anchor in anchors:
        idx = kept.find(anchor)
        if idx == -1:
            raise ChunkerError(f"split_anchor not found in source text: {anchor!r}")
        # The anchor may include surrounding whitespace so the *kept* remainder joins
        # cleanly (e.g. a sub-sentence carve of " (figure)" leaves "word word"); the
        # *superseded* fragment stores the anchor stripped so it stands on its own.
        stale_parts.append(anchor.strip())
        kept = kept[:idx] + kept[idx + len(anchor) :]
    # Collapse whitespace artifacts left by carving; do not alter words.
    kept = re.sub(r"[ \t]{2,}", " ", kept)
    kept = re.sub(r"[ \t]+\n", "\n", kept)
    kept = re.sub(r"\n{3,}", "\n\n", kept)
    return kept, "\n\n".join(p for p in stale_parts if p)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def chunk_unit(
    breadcrumb: str,
    text: str,
    status: str,
    *,
    entry_date: date | None = None,
    superseded_by: str | None = None,
    split: SplitSpec | None = None,
    config: ChunkConfig | None = None,
    start_index: int = 0,
) -> list[Chunk]:
    """Chunk one classified unit into :class:`Chunk` records.

    When ``split`` is given, the anchor spans are carved into their own
    ``superseded`` chunk (pointing at ``split.superseded_by``) and the remaining
    text keeps ``status``. This is the §4.4 contradiction-trap mechanism.
    """
    config = config or ChunkConfig()
    pieces: list[tuple[str, str, str | None]] = []  # (text, status, superseded_by)

    if split is not None:
        kept, stale = _carve_anchors(text, split.anchors)
        for body in _split_text(kept, config):
            pieces.append((body, status, superseded_by))
        if stale.strip():
            pieces.append((stale, "superseded", split.superseded_by))
    else:
        for body in _split_text(text, config):
            pieces.append((body, status, superseded_by))

    chunks: list[Chunk] = []
    for offset, (body, piece_status, piece_super) in enumerate(pieces):
        embed_text = _make_embed_text(breadcrumb, body)
        chunks.append(
            Chunk(
                chunk_index=start_index + offset,
                breadcrumb=breadcrumb,
                entry_date=entry_date,
                chunk_text=body,
                embed_text=embed_text,
                token_count=config.count(body),
                status=piece_status,
                superseded_by=piece_super,
            )
        )
    return chunks


def chunk_entry(
    file_path: str,
    heading: str,
    entry_text: str,
    status: str,
    *,
    superseded_by: str | None = None,
    split: SplitSpec | None = None,
    config: ChunkConfig | None = None,
    start_index: int = 0,
) -> list[Chunk]:
    """Chunk one dated log entry (``## YYYY-MM-DD — ...`` + body)."""
    breadcrumb = f"{file_path} > {heading}"
    return chunk_unit(
        breadcrumb,
        entry_text,
        status,
        entry_date=extract_entry_date(heading),
        superseded_by=superseded_by,
        split=split,
        config=config,
        start_index=start_index,
    )


def chunk_whole_file(
    file_path: str,
    text: str,
    status: str,
    *,
    superseded_by: str | None = None,
    config: ChunkConfig | None = None,
) -> list[Chunk]:
    """Chunk a whole-file Tier-2 doc, splitting on its headings (rule 1)."""
    config = config or ChunkConfig()
    sections = _iter_heading_sections(text)
    chunks: list[Chunk] = []
    for title_path, body in sections:
        crumb = file_path if not title_path else f"{file_path} > {' > '.join(title_path)}"
        chunks.extend(
            chunk_unit(
                crumb,
                body,
                status,
                superseded_by=superseded_by,
                config=config,
                start_index=len(chunks),
            )
        )
    return chunks


def _iter_heading_sections(text: str) -> list[tuple[tuple[str, ...], str]]:
    """Yield ``(heading_path, section_text)`` splitting on ## / ### headings.

    Content before the first ## (title/preamble) is attached to the file-level
    breadcrumb (empty heading path). Deeper headings extend the path.
    """
    lines = text.split("\n")
    sections: list[tuple[tuple[str, ...], str]] = []
    path: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip("\n")
        if body.strip():
            sections.append((tuple(path), body))
        buf.clear()

    for line in lines:
        hm = _HEADING_RE.match(line)
        if hm and len(hm.group(1)) >= 2:  # split on ## and deeper, keep # as title text
            flush()
            level = len(hm.group(1))
            title = hm.group(2).strip()
            path = path[: level - 2]
            path.append(title)
        else:
            buf.append(line)
    flush()
    return sections
