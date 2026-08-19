"""Manifest parsing, validation, and scaffolding for the PCS.

``docs/context-manifest.yml`` is the operator-owned status map (spec section
4.4). It classifies every Tier-2 file and every dated log entry into exactly one
of the four valid chunk statuses::

    current | superseded | deprecated | historical

The sentinel value :data:`UNCLASSIFIED` exists **only** in the manifest YAML and
in this module. It is never a valid ``pcs_chunk.status`` (the schema CHECK
constraint forbids it). It marks an item on the worklist that the operator has
not yet cleared.

Validation **fails loudly** (raises :class:`ManifestError`) if any Tier-2 target
is missing, still ``UNCLASSIFIED``, carries an invalid status, or is
``superseded``/``deprecated`` without a ``superseded_by`` pointer. This is the D2
realisation of spec section 4.4 point 5.

Enforcement ordering (spec section 4.4): the indexer (D4) MUST call
:func:`assert_manifest_valid` **before** it chunks, embeds, or writes any row.
Nothing carrying ``UNCLASSIFIED`` ever reaches the embedder or the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from quant_research.context.config import repo_root as default_repo_root

# The four valid chunk statuses (mirror the schema CHECK constraint).
VALID_STATUSES: frozenset[str] = frozenset({"current", "superseded", "deprecated", "historical"})

# Sentinel — manifest/worklist only, never a chunk status.
UNCLASSIFIED = "UNCLASSIFIED"

# Statuses that MUST carry a superseded_by pointer.
NEEDS_POINTER: frozenset[str] = frozenset({"superseded", "deprecated"})

MANIFEST_PATH_REL = "docs/context-manifest.yml"

# Tier-1 pinned documents (spec §4.1). Loaded whole, never chunked/embedded/ranked.
# They are the program's *current-state* set, so their manifest status is always
# ``current``. Classified here (not under ``documents:``) precisely so they can
# never be swept into the Tier-2 chunk/embed path — the tiers are mutually
# exclusive and validation enforces it.
TIER1_PINNED_DOCS: tuple[str, ...] = (
    "docs/program-charter.md",
    "docs/phase-2-kickoff.md",
    "docs/current-working-plan.md",
    "docs/ai-project-instructions.md",
    "docs/flux-response-style.md",
)

# Tier-2 whole-file documents: one status classifies the entire file (Q-04:
# docs-only for v1; src/ and notebooks/ deferred).
TIER2_WHOLE_FILE_DOCS: tuple[str, ...] = (
    "docs/m6-nt8-reproduction.md",
    "docs/nt8-backtest-methodology.md",
    "docs/phase-1-detailed-plan.md",
)

# Tier-2 documents chunked one-status-per-dated-entry (spec section 4.2). The
# chunk boundary is the ``## YYYY-MM-DD ...`` heading.
TIER2_ENTRY_LOGS: tuple[str, ...] = (
    "docs/lessons-log.md",
    "docs/research-log.md",
    "docs/chat-extracts/2026-07-29_pcs-d6-d7/extract.md",
)

# A dated entry heading: "## 2026-05-13 — Correction: ...". Sub-headings ("### ")
# and undated headings ("## Entries") do not match and are correctly skipped.
_DATED_HEADING = re.compile(r"^##[ \t]+(\d{4}-\d{2}-\d{2})\b")


class ManifestError(RuntimeError):
    """Raised when the manifest is missing or fails validation."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors: list[str] = errors or []


@dataclass(frozen=True)
class DatedEntry:
    """A dated log entry discovered by scanning a Tier-2 log file."""

    log_path: str
    heading: str  # full heading text after the "## " marker (the unique key)
    entry_date: date
    excerpt: str  # first content line beneath the heading


# --------------------------------------------------------------------------- #
# Corpus enumeration
# --------------------------------------------------------------------------- #
def resolve_whole_file_docs(repo_root: Path) -> tuple[str, ...]:
    """Return whole-file Tier-2 docs, including any committed chat extracts.

    Chat extracts (Q-02) land in ``docs/chat-extracts/`` and must be classified
    like any other Tier-2 file once they exist. None exist in the D2 slice.
    """
    extracts_dir = repo_root / "docs" / "chat-extracts"
    extras = tuple(sorted(p.relative_to(repo_root).as_posix() for p in extracts_dir.glob("*.md")))
    return TIER2_WHOLE_FILE_DOCS + extras


def iter_dated_entries(log_path: Path, log_rel: str) -> list[DatedEntry]:
    """Enumerate dated ``##`` entries in a log file, in document order.

    Args:
        log_path: Absolute path to the log file.
        log_rel: Repo-relative path used as the entry's ``log_path``.

    Returns:
        Discovered entries. The heading text (date + summary) is the unique key.
    """
    text = log_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    entries: list[DatedEntry] = []
    for i, line in enumerate(lines):
        m = _DATED_HEADING.match(line)
        if not m:
            continue
        heading = re.sub(r"^#+[ \t]*", "", line).strip()
        entry_date = date.fromisoformat(m.group(1))
        excerpt = ""
        for j in range(i + 1, len(lines)):
            stripped = lines[j].strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                break
            excerpt = stripped
            break
        entries.append(
            DatedEntry(
                log_path=log_rel,
                heading=heading,
                entry_date=entry_date,
                excerpt=excerpt,
            )
        )
    return entries


# --------------------------------------------------------------------------- #
# Loading and validation
# --------------------------------------------------------------------------- #
def load_manifest(path: Path) -> dict:
    """Load the manifest YAML into a plain dict (``{}`` if empty)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def _validate_status_block(label: str, block: object) -> list[str]:
    """Validate a single status block (document or entry). Returns errors."""
    if not isinstance(block, dict):
        return [f"{label}: expected a mapping with a 'status' field"]
    status = block.get("status")
    if status is None:
        return [f"{label}: missing 'status'"]
    if status == UNCLASSIFIED:
        return [f"{label}: still UNCLASSIFIED"]
    if status not in VALID_STATUSES:
        return [f"{label}: invalid status '{status}' (must be one of {sorted(VALID_STATUSES)})"]
    errors: list[str] = []
    if status in NEEDS_POINTER and not block.get("superseded_by"):
        errors.append(f"{label}: status '{status}' requires a 'superseded_by' pointer")
    if block.get("split_required"):
        if not block.get("split_note"):
            errors.append(f"{label}: split_required is set but 'split_note' is missing")
        if not block.get("split_anchor"):
            errors.append(
                f"{label}: split_required needs machine-readable 'split_anchor' "
                "(verbatim span(s) the D3 chunker carves into the superseded chunk)"
            )
        if not block.get("split_superseded_by"):
            errors.append(f"{label}: split_required needs a 'split_superseded_by' pointer")
    if block.get("latent_split_note") and status == "current":
        errors.append(
            f"{label}: latent_split_note is for off-surface entries; a 'current' entry "
            "with a split defect must use split_required + split_note instead"
        )
    return errors


def _validate_pinned_block(rel: str, block: object, repo_root: Path) -> list[str]:
    """Validate a Tier-1 pinned entry: must exist and be ``current``."""
    label = f"pinned {rel}"
    if not isinstance(block, dict):
        return [f"{label}: expected a mapping with a 'status' field"]
    errors: list[str] = []
    status = block.get("status")
    if status != "current":
        errors.append(
            f"{label}: Tier-1 pinned docs are the current-state set and must be "
            f"'current' (got {status!r})"
        )
    tier = block.get("tier")
    if tier is not None and tier != 1:
        errors.append(f"{label}: pinned docs are Tier-1 (got tier={tier!r})")
    if not (repo_root / rel).is_file():
        errors.append(f"{label}: file listed in manifest but not found in repo")
    return errors


def validate_manifest(
    manifest: dict,
    repo_root: Path,
    *,
    whole_file_docs: tuple[str, ...] | None = None,
    entry_logs: tuple[str, ...] = TIER2_ENTRY_LOGS,
    pinned_docs: tuple[str, ...] = TIER1_PINNED_DOCS,
) -> list[str]:
    """Validate a loaded manifest against the actual corpus. Returns errors.

    Every Tier-1 pinned doc, every whole-file Tier-2 doc, and every dated log
    entry must be present and classified. Tier-1 must be ``current``;
    superseded/deprecated Tier-2 items need a pointer. Manifest keys that do not
    correspond to a real target are flagged as stale, and a doc may never be in
    both tiers (that is the guard against a pinned doc being silently chunked).
    """
    if whole_file_docs is None:
        whole_file_docs = resolve_whole_file_docs(repo_root)

    errors: list[str] = []
    pinned_section = manifest.get("pinned") or {}
    docs_section = manifest.get("documents") or {}
    entries_section = manifest.get("entries") or {}

    if not isinstance(pinned_section, dict):
        errors.append("'pinned' must be a mapping of file_path -> status block")
        pinned_section = {}
    if not isinstance(docs_section, dict):
        errors.append("'documents' must be a mapping of file_path -> status block")
        docs_section = {}
    if not isinstance(entries_section, dict):
        errors.append("'entries' must be a mapping of log_path -> list of entries")
        entries_section = {}

    # Tier-1 pinned documents.
    for rel in pinned_docs:
        if rel not in pinned_section:
            errors.append(f"pinned Tier-1 doc not classified in manifest: {rel}")
            continue
        errors += _validate_pinned_block(rel, pinned_section[rel], repo_root)
    for rel in pinned_section:
        if rel not in pinned_docs:
            errors.append(f"manifest lists unknown pinned doc (not Tier-1): {rel}")

    # Tier separation: a pinned doc must never also be a Tier-2 target, or it would
    # be chunked/embedded despite being pinned-only (§4.1).
    tier2_all = set(whole_file_docs) | set(entry_logs)
    for rel in pinned_docs:
        if rel in tier2_all:
            errors.append(f"Tier-1 pinned doc also listed as Tier-2 (must be one tier): {rel}")

    # Whole-file documents.
    for rel in whole_file_docs:
        if rel not in docs_section:
            errors.append(f"document not classified in manifest: {rel}")
            continue
        errors += _validate_status_block(f"document {rel}", docs_section[rel])
    for rel in docs_section:
        if rel not in whole_file_docs:
            errors.append(f"manifest lists unknown document (not a Tier-2 doc): {rel}")

    # Entry-chunked logs.
    for log_rel in entry_logs:
        actual = iter_dated_entries(repo_root / log_rel, log_rel)
        actual_by_heading = {e.heading: e for e in actual}

        raw_list = entries_section.get(log_rel) or []
        if not isinstance(raw_list, list):
            errors.append(f"{log_rel}: 'entries' value must be a list")
            raw_list = []

        manifest_by_heading: dict[str, dict] = {}
        for item in raw_list:
            if not isinstance(item, dict):
                errors.append(f"{log_rel}: each entry must be a mapping")
                continue
            heading = item.get("heading")
            if not heading:
                errors.append(f"{log_rel}: an entry is missing its 'heading'")
                continue
            if heading in manifest_by_heading:
                errors.append(f"{log_rel}: duplicate manifest heading: {heading}")
            manifest_by_heading[heading] = item

        for heading in actual_by_heading:
            if heading not in manifest_by_heading:
                errors.append(f"{log_rel}: entry not classified in manifest: {heading}")
        for heading in manifest_by_heading:
            if heading not in actual_by_heading:
                errors.append(f"{log_rel}: manifest entry not found in file (stale?): {heading}")

        for heading, item in manifest_by_heading.items():
            if heading not in actual_by_heading:
                continue
            label = f"{log_rel} :: {heading}"
            errors += _validate_status_block(label, item)
            declared = item.get("date")
            if declared is not None:
                declared_iso = declared.isoformat() if isinstance(declared, date) else str(declared)
                if declared_iso != actual_by_heading[heading].entry_date.isoformat():
                    errors.append(
                        f"{label}: manifest date {declared_iso} != heading date "
                        f"{actual_by_heading[heading].entry_date.isoformat()}"
                    )

    return errors


def assert_manifest_valid(repo_root: Path | None = None, manifest_path: Path | None = None) -> None:
    """Raise :class:`ManifestError` unless the manifest is fully classified.

    The indexer (D4) must call this before chunking/embedding/upsert so that no
    ``UNCLASSIFIED`` content ever reaches the embedder or the database.
    """
    root = repo_root or default_repo_root()
    path = manifest_path or (root / MANIFEST_PATH_REL)
    if not path.exists():
        raise ManifestError(f"manifest not found: {path}")
    errors = validate_manifest(load_manifest(path), root)
    if errors:
        raise ManifestError(
            f"manifest validation failed ({len(errors)} issue(s))",
            errors=errors,
        )


# --------------------------------------------------------------------------- #
# Classification lookup (for the D4 indexer)
# --------------------------------------------------------------------------- #
def classification_for_document(manifest: dict, file_path: str) -> tuple[str, str | None]:
    """Return ``(status, superseded_by)`` for a whole-file Tier-2 doc."""
    block = (manifest.get("documents") or {}).get(file_path)
    if not isinstance(block, dict):
        raise ManifestError(f"no manifest classification for document: {file_path}")
    return block.get("status"), block.get("superseded_by")


def classification_for_entry(manifest: dict, log_path: str, heading: str) -> tuple[str, str | None]:
    """Return ``(status, superseded_by)`` for a dated log entry by heading."""
    for item in (manifest.get("entries") or {}).get(log_path) or []:
        if isinstance(item, dict) and item.get("heading") == heading:
            return item.get("status"), item.get("superseded_by")
    raise ManifestError(f"no manifest classification for entry: {log_path} :: {heading}")


def _as_anchor_tuple(value: object) -> tuple[str, ...]:
    """Normalise split_anchor (a scalar or list) into a tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


@dataclass(frozen=True)
class SplitRequired:
    """A dual-purpose entry the D3 chunker must split (§4.3 rule 2 / §4.4).

    ``anchors`` are the verbatim spans the chunker carves into the ``superseded``
    chunk; ``superseded_by`` is that chunk's pointer.
    """

    location: str  # "file_path" or "log_path :: heading"
    split_note: str
    anchors: tuple[str, ...] = ()
    superseded_by: str | None = None


def _split_required_from(location: str, block: dict) -> SplitRequired:
    return SplitRequired(
        location,
        block.get("split_note", ""),
        _as_anchor_tuple(block.get("split_anchor")),
        block.get("split_superseded_by"),
    )


def split_for_entry(manifest: dict, log_path: str, heading: str) -> SplitRequired | None:
    """Return the :class:`SplitRequired` spec for a dated entry, or None."""
    for item in (manifest.get("entries") or {}).get(log_path) or []:
        if isinstance(item, dict) and item.get("heading") == heading and item.get("split_required"):
            return _split_required_from(f"{log_path} :: {heading}", item)
    return None


def iter_split_required(manifest: dict) -> list[SplitRequired]:
    """Return every entry flagged ``split_required``.

    D3's chunker must split each of these so the stale number becomes its own
    ``superseded`` chunk while the live finding stays ``current``. D3 is not done
    until this list is honoured (golden query #1 is the ORB+Opt3 acceptance test).
    """
    out: list[SplitRequired] = []
    for file_path, block in (manifest.get("documents") or {}).items():
        if isinstance(block, dict) and block.get("split_required"):
            out.append(_split_required_from(file_path, block))
    for log_path, items in (manifest.get("entries") or {}).items():
        for item in items or []:
            if isinstance(item, dict) and item.get("split_required"):
                out.append(_split_required_from(f"{log_path} :: {item.get('heading')}", item))
    return out


@dataclass(frozen=True)
class LatentSplit:
    """An off-surface (historical) entry carrying a recorded latent split defect.

    Unlike :class:`SplitRequired`, this is NOT a D3 obligation: the entry is off the
    default retrieval surface, so its stale-as-fact number is never served unless the
    entry is promoted to ``current`` or explicitly recalled. The note exists so the
    debt is visible at that moment rather than shipping the misread as fact.
    """

    location: str
    latent_split_note: str


def iter_latent_split(manifest: dict) -> list[LatentSplit]:
    """Return every entry carrying a ``latent_split_note`` (informational only)."""
    out: list[LatentSplit] = []
    for file_path, block in (manifest.get("documents") or {}).items():
        if isinstance(block, dict) and block.get("latent_split_note"):
            out.append(LatentSplit(file_path, block["latent_split_note"]))
    for log_path, items in (manifest.get("entries") or {}).items():
        for item in items or []:
            if isinstance(item, dict) and item.get("latent_split_note"):
                location = f"{log_path} :: {item.get('heading')}"
                out.append(LatentSplit(location, item["latent_split_note"]))
    return out


# --------------------------------------------------------------------------- #
# Draft scaffold generation
# --------------------------------------------------------------------------- #
@dataclass
class _Suggestion:
    """A suggested (not applied) supersession pre-fill, matched by predicate."""

    log_rel: str
    date_iso: str
    contains: str
    status: str
    superseded_by: str
    note: str

    def matches(self, entry: DatedEntry) -> bool:
        return (
            entry.log_path == self.log_rel
            and entry.entry_date.isoformat() == self.date_iso
            and self.contains in entry.heading
        )


# Pointers reference the target entry unambiguously by "file :: heading" because
# dates are NOT unique keys (e.g. seven entries share 2026-04-28).
_PTR_1088 = (
    "docs/lessons-log.md :: 2026-05-13 — Correction: ~$10,885/yr was qty=10 "
    "total, not per contract; M6 closes"
)
_PTR_UTC = (
    "docs/lessons-log.md :: 2026-04-27 — Source NT8 export timestamps are UTC, not CME local time"
)

# Only entries that announce their own supersession target are pre-filled, and
# only as SUGGESTIONS the operator confirms. Everything else stays UNCLASSIFIED.
_ENTRY_SUGGESTIONS: tuple[_Suggestion, ...] = (
    _Suggestion(
        "docs/lessons-log.md",
        "2026-04-28",
        "Production cut to ORB+Opt3",
        "superseded",
        _PTR_1088,
        "carries the ~$10,885/yr *per contract* misread (golden-query trap #1)",
    ),
    _Suggestion(
        "docs/lessons-log.md",
        "2026-04-28",
        "M6 second escalation",
        "superseded",
        _PTR_1088,
        "treats ~$10,885 as per-contract ($/yr/contract) (golden-query trap #1)",
    ),
    _Suggestion(
        "docs/lessons-log.md",
        "2026-04-26",
        "NT8 export contains DST-gap timestamps",
        "superseded",
        _PTR_UTC,
        "'source IS America/Chicago' rationale, corrected 2026-04-27 (trap #4)",
    ),
)

_DOC_SUGGESTIONS: dict[str, tuple[str, str, str]] = {}


def _dq(value: str) -> str:
    """Return a double-quoted YAML scalar with safe escaping (unicode literal)."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _comment(text: str, limit: int = 160) -> str:
    """Render a one-line YAML comment body, collapsed and truncated."""
    collapsed = " ".join(text.split())
    if len(collapsed) > limit:
        collapsed = collapsed[: limit - 1].rstrip() + "…"
    return collapsed


def render_scaffold(repo_root: Path) -> str:
    """Render a draft ``context-manifest.yml`` worklist.

    Every target defaults to ``UNCLASSIFIED``. Only entries that explicitly
    announce their own supersession target are pre-filled, tagged as SUGGESTIONS
    for operator confirmation. Each item carries a one-line excerpt comment.
    """
    lines: list[str] = []
    a = lines.append

    a("# docs/context-manifest.yml — PCS status map (operator-owned; spec §4.4)")
    a("#")
    a("# This is a WORKLIST, not a pre-approved map. Every item defaults to")
    a("# UNCLASSIFIED and MUST be changed to exactly one of:")
    a("#     current | superseded | deprecated | historical")
    a("# UNCLASSIFIED is a sentinel (worklist only) — never a valid chunk status.")
    a("# 'pcs doctor' stays RED until zero UNCLASSIFIED items remain.")
    a("#")
    a("# superseded/deprecated MUST carry a 'superseded_by' pointer.")
    a("# Lines tagged 'SUGGESTION (confirm)' are proposals only — confirm each;")
    a("# suggestion != decision. Everything else was left UNCLASSIFIED on purpose")
    a("# (the text did not explicitly supersede a named prior entry — do not infer).")
    a("")
    a("# --- Tier-1 pinned documents (loaded whole, never chunked; spec §4.1) ------")
    a("# Structural: pinned docs are the current-state set, so they are pre-filled")
    a("# 'current'. They must never also appear as Tier-2 targets.")
    a("pinned:")
    for rel in TIER1_PINNED_DOCS:
        abs_path = repo_root / rel
        title = ""
        if abs_path.exists():
            for raw in abs_path.read_text(encoding="utf-8").splitlines():
                stripped = raw.strip().lstrip("#").lstrip(">").strip()
                if stripped:
                    title = stripped
                    break
        a(f"  {_dq(rel)}:")
        if title:
            a(f"    # {_comment(title)}")
        a("    tier: 1")
        a("    status: current")
    a("")
    a("# --- Tier-2 whole-file documents ------------------------------------------")
    a("documents:")
    for rel in resolve_whole_file_docs(repo_root):
        abs_path = repo_root / rel
        title = ""
        if abs_path.exists():
            for raw in abs_path.read_text(encoding="utf-8").splitlines():
                stripped = raw.strip().lstrip("#").lstrip(">").strip()
                if stripped:
                    title = stripped
                    break
        a(f"  {_dq(rel)}:")
        if title:
            a(f"    # {_comment(title)}")
        suggestion = _DOC_SUGGESTIONS.get(rel)
        if suggestion:
            status, pointer, note = suggestion
            a(f"    # SUGGESTION (confirm): {note}")
            a(f"    status: {status}")
            a(f"    superseded_by: {_dq(pointer)}")
        else:
            a("    status: UNCLASSIFIED")
    a("")
    a("# --- Tier-2 entry-chunked logs (one status per dated entry) ---------------")
    a("entries:")
    for log_rel in TIER2_ENTRY_LOGS:
        a(f"  {_dq(log_rel)}:")
        entries = iter_dated_entries(repo_root / log_rel, log_rel)
        for entry in entries:
            a(f"    - heading: {_dq(entry.heading)}")
            if entry.excerpt:
                a(f"      # {_comment(entry.excerpt)}")
            a(f"      date: {entry.entry_date.isoformat()}")
            match = next((s for s in _ENTRY_SUGGESTIONS if s.matches(entry)), None)
            if match:
                a(f"      # SUGGESTION (confirm): {match.note}")
                a(f"      status: {match.status}")
                a(f"      superseded_by: {_dq(match.superseded_by)}")
            else:
                a("      status: UNCLASSIFIED")
        a("")
    return "\n".join(lines).rstrip() + "\n"


def write_scaffold(repo_root: Path | None = None, *, force: bool = False) -> Path:
    """Write the draft manifest to ``docs/context-manifest.yml``.

    Refuses to overwrite an existing manifest unless ``force`` is set, so the
    operator's classifications are never clobbered.
    """
    root = repo_root or default_repo_root()
    path = root / MANIFEST_PATH_REL
    if path.exists() and not force:
        raise ManifestError(
            f"{path} already exists; refusing to overwrite (use force=True). "
            "This protects operator classifications."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_scaffold(root), encoding="utf-8")
    return path
