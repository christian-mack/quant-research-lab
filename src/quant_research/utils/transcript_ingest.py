"""ICT transcript ingestion: manifest parsing, normalization, and concept citation mapping.

Phase A source-material ingestion only. There is NO strategy logic, NO edge claim, and NO
interpretation/summarization of what ICT "means" in this module: the citation map is pure
case-insensitive, alphanumeric-boundary keyword windowing over raw timestamped segments so a
human can read and cite the original wording.

The parsing/normalization/tagging core is network-free and unit-testable on in-memory fixtures.
The optional fetch helpers (``youtube-transcript-api`` and the ``yt-dlp`` CLI) are isolated
behind lazy imports so importing this module never requires those dependencies or the network.
"""

from __future__ import annotations

import csv
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Concept lexicon: concept key -> keyword/phrase list. This is the ONLY tagging signal. The
# manifest's ``concept_tags`` column is metadata only and does NOT filter this scan; every
# concept lexicon is scanned against every video regardless of its tags.
CONCEPT_LEXICON: dict[str, tuple[str, ...]] = {
    "spec_a_sweep": (
        "liquidity",
        "buyside",
        "sellside",
        "stop hunt",
        "stop run",
        "raid",
        "sweep",
        "judas",
        "market structure shift",
        "MSS",
        "displacement",
        "fair value gap",
        "FVG",
        "order block",
        "OTE",
        "optimal trade entry",
    ),
    "spec_b_pd": (
        "premium",
        "discount",
        "equilibrium",
        "dealing range",
        "fibonacci",
        "50%",
    ),
    "spec_c_gap": (
        "opening gap",
        "new day opening gap",
        "NDOG",
        "new week opening gap",
        "NWOG",
        "gap",
        "opening price",
    ),
    "settlement": (
        "settlement",
        "closing price",
        "session close",
        "prior close",
    ),
    "session_timing": (
        "london",
        "new york",
        "midnight",
        "asian",
        "asia",
        "killzone",
        "kill zone",
        "8:30",
        "0830",
        "9:30",
        "0930",
    ),
}

# Daily-bias corpus lexicon: concept group -> keyword/phrase list. This corpus is intentionally
# SEPARATE from CONCEPT_LEXICON (2022 mentorship) and must not be merged with it. Like
# CONCEPT_LEXICON it is the ONLY tagging signal — pure case-insensitive, alphanumeric-boundary
# windowing with no interpretation. Short tokens (e.g. "h4", "bos", "mss", "pdh") rely on
# ``_compile_keyword``'s boundary guards so they never match inside larger words; bare
# two-letter abbreviations such as "ce" are deliberately omitted in favor of the spelled-out
# phrase ("consequent encroachment").
BIAS_LEXICON: dict[str, tuple[str, ...]] = {
    "bias_core": (
        "daily bias",
        "directional bias",
        "bias",
        "draw on liquidity",
        "draw",
        "objective",
        "narrative",
        "expansion",
        "intent",
    ),
    "htf_reference": (
        "higher time frame",
        "higher timeframe",
        "htf",
        "daily",
        "weekly",
        "monthly",
        "4 hour",
        "four hour",
        "h4",
        "timeframe",
    ),
    "liquidity_targets": (
        "liquidity",
        "buyside",
        "buy side",
        "sellside",
        "sell side",
        "previous day high",
        "previous day low",
        "pdh",
        "pdl",
        "old high",
        "old low",
        "swing high",
        "swing low",
        "relative equal",
    ),
    "pd_array": (
        "premium",
        "discount",
        "equilibrium",
        "fair value gap",
        "fvg",
        "order block",
        "breaker",
        "mitigation block",
    ),
    "midpoint_validation": (
        "midpoint",
        "consequent encroachment",
        "mean threshold",
        "50%",
    ),
    "structure": (
        "market structure",
        "break of structure",
        "bos",
        "market structure shift",
        "mss",
        "displacement",
        "shift",
    ),
    "timeframe_nesting": (
        "nested",
        "alignment",
        "align",
        "conflict",
        "against",
        "override",
        "higher time frame objective",
    ),
    "no_clear_bias": (
        "consolidation",
        "consolidating",
        "neutral",
        "no trade",
        "unclear",
        "choppy",
        "range",
        "balanced",
        "indecision",
    ),
}

# Extended daily-bias lexicon: NEW concept groups capturing TTrades' mechanical vocabulary,
# which the ICT-standard ``BIAS_LEXICON`` under-collected. These are ADDITIVE groups (the base
# groups above are left untouched and remain reproducible); they are merged into the per-video
# concept maps alongside the originals. Same matcher and short-token discipline apply: every
# token is boundary-guarded by ``_compile_keyword`` (no matches inside larger words) and bare
# two-letter abbreviations (e.g. "eq", "po3") are deliberately omitted in favor of multiword or
# safe forms. ``cisd`` and ``smt`` are 3+ chars and safe under the boundary guards.
BIAS_LEXICON_EXTENSION: dict[str, tuple[str, ...]] = {
    "delivery": (
        "change in state of delivery",
        "change in the state of delivery",
        "state of delivery",
        "cisd",
    ),
    "smt": (
        "smt",
        "divergence",
    ),
    "candle_mechanics": (
        "wick",
        "shallow wick",
        "large wick",
        "small wick",
        "candle close",
        "candle closure",
        "closure",
        "close above",
        "close below",
        "close near",
        "body of the candle",
    ),
    "day_type": (
        "continuation",
        "reversal",
        "reversal day",
        "continuation day",
    ),
    "protected_swing": (
        "protected swing",
        "protected high",
        "protected low",
    ),
    "eq_targets": (
        "equilibrium",
        "previous day high",
        "previous day low",
        "pdh",
        "pdl",
        "draw on liquidity",
        "opposing liquidity",
    ),
    "power_of_three": (
        "power of three",
        "accumulation",
        "manipulation",
        "distribution",
    ),
}

VALID_ERAS = frozenset({"2022", "2016", "other"})
VALID_ROLES = frozenset({"primary", "supplement"})
MANIFEST_COLUMNS = ("video_id", "title", "url", "era", "concept_tags")
BIAS_MANIFEST_COLUMNS = ("video_id", "title", "url", "creator", "role", "corpus")
DEFAULT_CONTEXT = 2
DEFAULT_LANGUAGES = ("en", "en-US", "en-GB")
MISSING_CSV_COLUMNS = ("video_id", "title", "url", "era", "reason")
BIAS_MISSING_CSV_COLUMNS = ("video_id", "title", "url", "creator", "reason")

# Fetch resilience: YouTube rate-limits caption downloads per IP (HTTP 429 / IpBlocked) even
# when caption metadata is retrievable, so transient failures are retried with exponential
# backoff before a video is treated as missing.
DEFAULT_FETCH_RETRIES = 3
DEFAULT_FETCH_BACKOFF_S = 5.0
_RATE_LIMIT_TOKENS = (
    "ipblocked",
    "requestblocked",
    "toomanyrequests",
    "too many requests",
    "429",
)


@dataclass(frozen=True, slots=True)
class ManifestRow:
    """One curated ICT source video from the manifest.

    Attributes:
        video_id: YouTube video id.
        title: Human-readable title.
        url: Canonical video URL.
        era: One of ``{"2022", "2016", "other"}``.
        concept_tags: Concept keys (metadata only; never used to filter the citation scan).
    """

    video_id: str
    title: str
    url: str
    era: str
    concept_tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BiasManifestRow:
    """One daily-bias-corpus source video from ``bias_manifest.csv``.

    Distinct from :class:`ManifestRow`: the daily-bias corpus is tracked by ``creator`` and
    ``role`` (not ``era``/``concept_tags``) and must stay separate from the 2022 mentorship
    corpus. The whole bias lexicon is scanned against every bias video.

    Attributes:
        video_id: YouTube video id. May begin with ``-`` (e.g. ``-KKuZb5Z5aU``); always pass
            such ids as values, never as bare CLI arguments.
        title: Human-readable title (provisional; verify against the live video).
        url: Canonical video URL.
        creator: Source creator slug (e.g. ``"jadecap"``, ``"ttrades"``).
        role: One of ``{"primary", "supplement"}``.
        corpus: Corpus tag; expected to be ``"bias"`` for this manifest.
    """

    video_id: str
    title: str
    url: str
    creator: str
    role: str
    corpus: str


# --------------------------------------------------------------------------------------------
# Manifest parsing
# --------------------------------------------------------------------------------------------
def parse_concept_tags(raw: str | None) -> tuple[str, ...]:
    """Parse a ``concept_tags`` cell into a tuple of concept keys.

    An empty cell or the literal ``"all"`` (case-insensitive) expands to every concept key.
    Otherwise the cell is a ``"|"``-separated list of concept keys. Tags are metadata only and
    do not filter the citation-map scan.

    Args:
        raw: The raw cell value.

    Returns:
        Concept keys in declared order (deduplicated).
    """
    value = (raw or "").strip()
    if not value or value.lower() == "all":
        return tuple(CONCEPT_LEXICON)
    seen: dict[str, None] = {}
    for tag in value.split("|"):
        cleaned = tag.strip()
        if cleaned:
            seen.setdefault(cleaned, None)
    return tuple(seen)


def read_manifest(path: str | Path) -> list[ManifestRow]:
    """Read the ICT source manifest CSV.

    Args:
        path: Path to ``manifest.csv`` with columns
            ``video_id, title, url, era, concept_tags``.

    Returns:
        Parsed manifest rows in file order.

    Raises:
        FileNotFoundError: If the manifest does not exist. The caller should stop and report
            rather than guess video IDs.
        ValueError: If a required column is missing or a row has an invalid ``era``.
    """
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"ICT source manifest not found at {manifest_path}. "
            "Place manifest.csv before running; do not guess video IDs."
        )
    rows: list[ManifestRow] = []
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(MANIFEST_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Manifest missing required columns: {sorted(missing)}")
        for line_no, record in enumerate(reader, start=2):
            era = (record.get("era") or "").strip()
            if era not in VALID_ERAS:
                raise ValueError(
                    f"Manifest line {line_no}: invalid era {era!r}; "
                    f"expected one of {sorted(VALID_ERAS)}."
                )
            rows.append(
                ManifestRow(
                    video_id=(record.get("video_id") or "").strip(),
                    title=(record.get("title") or "").strip(),
                    url=(record.get("url") or "").strip(),
                    era=era,
                    concept_tags=parse_concept_tags(record.get("concept_tags")),
                )
            )
    return rows


def read_bias_manifest(path: str | Path) -> list[BiasManifestRow]:
    """Read the daily-bias-corpus manifest CSV.

    Args:
        path: Path to ``bias_manifest.csv`` with columns
            ``video_id, title, url, creator, role, corpus``.

    Returns:
        Parsed bias-manifest rows in file order.

    Raises:
        FileNotFoundError: If the manifest does not exist. The caller should stop and report
            rather than guess video IDs.
        ValueError: If a required column is missing or a row has an invalid ``role``.
    """
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Bias-corpus manifest not found at {manifest_path}. "
            "Place bias_manifest.csv before running; do not guess video IDs."
        )
    rows: list[BiasManifestRow] = []
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(BIAS_MANIFEST_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Bias manifest missing required columns: {sorted(missing)}")
        for line_no, record in enumerate(reader, start=2):
            role = (record.get("role") or "").strip()
            if role not in VALID_ROLES:
                raise ValueError(
                    f"Bias manifest line {line_no}: invalid role {role!r}; "
                    f"expected one of {sorted(VALID_ROLES)}."
                )
            rows.append(
                BiasManifestRow(
                    video_id=(record.get("video_id") or "").strip(),
                    title=(record.get("title") or "").strip(),
                    url=(record.get("url") or "").strip(),
                    creator=(record.get("creator") or "").strip(),
                    role=role,
                    corpus=(record.get("corpus") or "").strip(),
                )
            )
    return rows


# --------------------------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------------------------
def _as_float(value: Any, *, default: float) -> float:
    """Coerce ``value`` to ``float``, returning ``default`` if it is missing or non-numeric."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_segment(raw: Mapping[str, Any]) -> dict[str, float | str]:
    """Coerce one raw caption snippet into a ``{"start", "end", "text"}`` segment.

    Missing-field handling tolerates the schema differences between caption sources:
    a missing ``text`` becomes ``""`` and a missing ``start`` becomes ``0.0``. ``end`` is taken
    directly when present, else derived as ``start + duration``, else defaults to ``start``
    (a zero-length segment).

    Args:
        raw: Mapping that may contain ``text``, ``start``, and either ``end`` or ``duration``.

    Returns:
        A normalized segment dict.
    """
    text = str(raw.get("text", "") or "")
    start = _as_float(raw.get("start"), default=0.0)
    if raw.get("end") is not None:
        end = _as_float(raw.get("end"), default=start)
    elif raw.get("duration") is not None:
        end = start + _as_float(raw.get("duration"), default=0.0)
    else:
        end = start
    return {"start": start, "end": end, "text": text}


def normalize_transcript(
    *,
    video_id: str,
    title: str,
    url: str,
    era: str,
    concept_tags: Sequence[str],
    source: str,
    raw_segments: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Normalize raw caption snippets into the structured per-video transcript schema.

    Args:
        video_id: YouTube video id.
        title: Video title.
        url: Video URL.
        era: One of ``{"2022", "2016", "other"}``.
        concept_tags: Concept tags from the manifest (metadata only).
        source: ``"captions"`` (manual) or ``"auto_subs"`` (auto-generated fallback).
        raw_segments: Iterable of raw snippet mappings (see ``normalize_segment``).

    Returns:
        A dict matching the normalized transcript schema, with ``segments`` sorted by start.
    """
    segments = [normalize_segment(seg) for seg in raw_segments]
    segments.sort(key=lambda seg: seg["start"])
    return {
        "video_id": video_id,
        "title": title,
        "url": url,
        "era": era,
        "concept_tags": list(concept_tags),
        "source": source,
        "segments": segments,
    }


def normalize_bias_transcript(
    *,
    video_id: str,
    title: str,
    url: str,
    creator: str,
    role: str,
    corpus: str = "bias",
    source: str,
    raw_segments: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Normalize raw caption snippets into the daily-bias per-video transcript schema.

    Mirrors :func:`normalize_transcript` but carries the bias-corpus metadata
    (``creator``/``role``/``corpus``) instead of ``era``/``concept_tags``. Kept distinct so the
    bias corpus never co-mingles with the 2022 mentorship corpus.

    Args:
        video_id: YouTube video id.
        title: Video title.
        url: Video URL.
        creator: Source creator slug.
        role: One of ``{"primary", "supplement"}``.
        corpus: Corpus tag (defaults to ``"bias"``).
        source: ``"captions"``, ``"auto_subs"``, or ``"operator_supplied"``.
        raw_segments: Iterable of raw snippet mappings (see :func:`normalize_segment`).

    Returns:
        A dict matching the bias transcript schema, with ``segments`` sorted by start.
    """
    segments = [normalize_segment(seg) for seg in raw_segments]
    segments.sort(key=lambda seg: seg["start"])
    return {
        "video_id": video_id,
        "title": title,
        "url": url,
        "creator": creator,
        "role": role,
        "corpus": corpus,
        "source": source,
        "segments": segments,
    }


# --------------------------------------------------------------------------------------------
# Concept citation map (pure keyword windowing)
# --------------------------------------------------------------------------------------------
def _compile_keyword(keyword: str) -> re.Pattern[str]:
    """Compile a case-insensitive, alphanumeric-boundary pattern for one keyword or phrase.

    Boundaries are lookarounds against ``[A-Za-z0-9]`` rather than ``\\b`` so that:
    multi-word phrases match across single or multiple spaces; tokens with punctuation such as
    ``8:30`` and ``50%`` match cleanly; and a keyword never matches inside a larger word (for
    example ``OTE`` does not match inside ``promote``).
    """
    escaped = r"\s+".join(re.escape(part) for part in keyword.split())
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def find_keyword_hits(
    segments: Sequence[Mapping[str, Any]],
    keywords: Iterable[str],
    *,
    context: int = DEFAULT_CONTEXT,
) -> list[dict[str, Any]]:
    """Find segments matching any keyword, attaching ``±context`` adjacent segments.

    Pure keyword windowing: case-insensitive, alphanumeric-boundary matching with no
    paraphrasing or summarization. A segment matching several keywords yields a single hit that
    records all matched keywords. The context window is clamped at the segment-list boundaries.

    Args:
        segments: Ordered segments, each a mapping with ``start``, ``end``, and ``text``.
        keywords: Keyword/phrase lexicon to scan for.
        context: Number of adjacent segments to include on each side of a match.

    Returns:
        Hits in segment order, each with ``start``, ``end``, ``text``, ``matched_keywords``
        (sorted), and ``context`` (the windowed segments in order).
    """
    patterns = [(kw, _compile_keyword(kw)) for kw in keywords]
    hits: list[dict[str, Any]] = []
    for idx, segment in enumerate(segments):
        text = str(segment.get("text", "") or "")
        matched = sorted({kw for kw, pattern in patterns if pattern.search(text)})
        if not matched:
            continue
        lo = max(0, idx - context)
        hi = min(len(segments), idx + context + 1)
        window = [
            {
                "start": _as_float(segments[j].get("start"), default=0.0),
                "end": _as_float(segments[j].get("end"), default=0.0),
                "text": str(segments[j].get("text", "") or ""),
            }
            for j in range(lo, hi)
        ]
        hits.append(
            {
                "start": _as_float(segment.get("start"), default=0.0),
                "end": _as_float(segment.get("end"), default=0.0),
                "text": text,
                "matched_keywords": matched,
                "context": window,
            }
        )
    return hits


def build_citation_map(
    transcripts: Iterable[Mapping[str, Any]],
    *,
    lexicon: Mapping[str, Sequence[str]] | None = None,
    context: int = DEFAULT_CONTEXT,
) -> dict[str, list[dict[str, Any]]]:
    """Scan every concept lexicon against every transcript, regardless of concept tags.

    Args:
        transcripts: Normalized per-video transcript dicts (see ``normalize_transcript``).
        lexicon: Concept -> keyword lists. Defaults to ``CONCEPT_LEXICON``.
        context: Adjacent-segment context window per hit.

    Returns:
        Concept -> list of citation hits. Each hit carries ``video_id``, ``title``, ``url``,
        ``start``, and ``text`` (the citation-map schema) plus ``end``, ``matched_keywords``,
        and ``context`` for human review.
    """
    active = dict(lexicon) if lexicon is not None else CONCEPT_LEXICON
    citation_map: dict[str, list[dict[str, Any]]] = {concept: [] for concept in active}
    materialized = list(transcripts)
    for concept, keywords in active.items():
        for video in materialized:
            segments = video.get("segments", [])
            for hit in find_keyword_hits(segments, keywords, context=context):
                citation_map[concept].append(
                    {
                        "video_id": video.get("video_id", ""),
                        "title": video.get("title", ""),
                        "url": video.get("url", ""),
                        "start": hit["start"],
                        "text": hit["text"],
                        "end": hit["end"],
                        "matched_keywords": hit["matched_keywords"],
                        "context": hit["context"],
                    }
                )
    return citation_map


def build_bias_concept_map(
    transcript: Mapping[str, Any],
    *,
    lexicon: Mapping[str, Sequence[str]] | None = None,
    context: int = DEFAULT_CONTEXT,
    git_sha: str | None = None,
) -> dict[str, Any]:
    """Build one daily-bias concept map for a SINGLE video (kept distinct per video).

    Reuses :func:`find_keyword_hits` (the word-boundary windowing core) — no new matching
    logic. Every bias-lexicon group is scanned against the one video's segments; this function
    deliberately operates on a single transcript so the two creators' maps are never merged or
    reconciled (that is downstream work).

    Args:
        transcript: A normalized bias transcript (see :func:`normalize_bias_transcript`).
        lexicon: Concept group -> keyword lists. Defaults to :data:`BIAS_LEXICON`.
        context: Adjacent-segment context window per hit.
        git_sha: Optional code version recorded in the output metadata for provenance.

    Returns:
        A dict with top-level provenance metadata (``video_id``, ``title``, ``url``,
        ``creator``, ``role``, ``corpus``, ``primary`` (``role == "primary"``), and ``git_sha``
        when provided) plus a ``concepts`` map of concept group -> list of hits. Each hit
        carries ``video_id``, ``creator``, ``role``, ``start``, ``text``, ``matched_keywords``,
        ``end``, and ``context``.
    """
    active = dict(lexicon) if lexicon is not None else BIAS_LEXICON
    segments = transcript.get("segments", [])
    video_id = transcript.get("video_id", "")
    creator = transcript.get("creator", "")
    role = transcript.get("role", "")
    concepts: dict[str, list[dict[str, Any]]] = {}
    for concept, keywords in active.items():
        hits: list[dict[str, Any]] = []
        for hit in find_keyword_hits(segments, keywords, context=context):
            hits.append(
                {
                    "video_id": video_id,
                    "creator": creator,
                    "role": role,
                    "start": hit["start"],
                    "text": hit["text"],
                    "matched_keywords": hit["matched_keywords"],
                    "end": hit["end"],
                    "context": hit["context"],
                }
            )
        concepts[concept] = hits
    metadata: dict[str, Any] = {
        "video_id": video_id,
        "title": transcript.get("title", ""),
        "url": transcript.get("url", ""),
        "creator": creator,
        "role": role,
        "corpus": transcript.get("corpus", "bias"),
        "primary": role == "primary",
    }
    if git_sha is not None:
        metadata["git_sha"] = git_sha
    metadata["concepts"] = concepts
    return metadata


# --------------------------------------------------------------------------------------------
# Local I/O helpers (no network)
# --------------------------------------------------------------------------------------------
def write_json(path: str | Path, data: Any) -> Path:
    """Write ``data`` as pretty UTF-8 JSON, creating parent directories as needed."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    return out_path


def log_missing(path: str | Path, row: ManifestRow, reason: str) -> Path:
    """Append a row to the ``_missing.csv`` log, writing the header if the file is new.

    Args:
        path: Path to ``_missing.csv``.
        row: The manifest row whose transcript could not be retrieved.
        reason: Short machine-readable reason (e.g. ``"no_transcript"``).

    Returns:
        The path written to.
    """
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not out_path.exists()
    with out_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if write_header:
            writer.writerow(MISSING_CSV_COLUMNS)
        writer.writerow([row.video_id, row.title, row.url, row.era, reason])
    return out_path


def parse_vtt(text: str) -> list[dict[str, float | str]]:
    """Parse WebVTT caption text into normalized ``{"start", "end", "text"}`` segments.

    This is the parser for the ``yt-dlp`` auto-subs fallback. It is deliberately network-free
    so it can be unit-tested. Inline cue tags (e.g. ``<00:00:01.000>`` and ``<c>``) and cue
    settings on the timing line are stripped; cues are merged across their text lines.

    Args:
        text: Raw WebVTT file contents.

    Returns:
        Segments in file order.
    """
    timing = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})"
    )
    tag = re.compile(r"<[^>]+>")
    segments: list[dict[str, float | str]] = []
    start: float | None = None
    end: float | None = None
    lines: list[str] = []

    def _flush() -> None:
        nonlocal start, end, lines
        if start is not None and lines:
            cue = tag.sub("", " ".join(lines)).strip()
            if cue:
                segments.append({"start": start, "end": end or start, "text": cue})
        start, end, lines = None, None, []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = timing.search(line)
        if match:
            _flush()
            start = _vtt_timestamp_to_seconds(match.group(1))
            end = _vtt_timestamp_to_seconds(match.group(2))
        elif not line or line in {"WEBVTT"} or line.isdigit():
            if not line:
                _flush()
        elif start is not None:
            lines.append(line)
    _flush()
    return segments


def _vtt_timestamp_to_seconds(stamp: str) -> float:
    """Convert a ``HH:MM:SS.mmm`` or ``MM:SS.mmm`` WebVTT timestamp to seconds."""
    stamp = stamp.replace(",", ".")
    parts = stamp.split(":")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


# --------------------------------------------------------------------------------------------
# Network fetch helpers (lazy imports; not exercised by unit tests)
# --------------------------------------------------------------------------------------------
def _to_raw_segments(fetched: Any) -> list[dict[str, Any]]:
    """Normalize a youtube-transcript-api result into a list of raw snippet dicts."""
    if hasattr(fetched, "to_raw_data"):
        return list(fetched.to_raw_data())
    if isinstance(fetched, list):
        return [dict(item) for item in fetched]
    return [
        {
            "text": getattr(snippet, "text", ""),
            "start": getattr(snippet, "start", 0.0),
            "duration": getattr(snippet, "duration", 0.0),
        }
        for snippet in fetched
    ]


def _looks_rate_limited(error: BaseException) -> bool:
    """Return ``True`` if an exception looks like a YouTube rate-limit / IP block."""
    text = f"{type(error).__name__} {error}".lower()
    return any(token in text for token in _RATE_LIMIT_TOKENS)


def _fetch_via_transcript_api(
    video_id: str, *, languages: Sequence[str], retries: int, backoff: float
) -> tuple[str, list[dict[str, Any]]] | None:
    """Fetch via youtube-transcript-api, preferring manual captions over generated ones.

    Retries with exponential backoff on rate-limit / IP-block errors; other errors (e.g. no
    transcript exists) fail fast. Returns ``(source, raw_segments)`` or ``None`` if the
    dependency is absent or no transcript is retrievable. ``source`` is ``"captions"`` for
    manual captions, ``"auto_subs"`` for generated ones.
    """
    import time

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None
    languages = list(languages)
    api = YouTubeTranscriptApi()
    for attempt in range(retries + 1):
        try:
            transcript_list = api.list(video_id)
            try:
                transcript = transcript_list.find_manually_created_transcript(languages)
                source = "captions"
            except Exception:
                transcript = transcript_list.find_generated_transcript(languages)
                source = "auto_subs"
            return source, _to_raw_segments(transcript.fetch())
        except Exception as exc:
            if attempt < retries and _looks_rate_limited(exc):
                time.sleep(backoff * (2**attempt))
                continue
            return None
    return None


def _fetch_via_yt_dlp(
    video_id: str,
    *,
    languages: Sequence[str],
    workdir: str | Path | None,
    retries: int,
    backoff: float,
) -> tuple[str, list[dict[str, Any]]] | None:
    """Fetch auto-generated captions via the ``yt-dlp`` CLI (``--write-auto-subs``).

    Retries with exponential backoff when ``yt-dlp`` reports an HTTP 429 / rate-limit. Returns
    ``(source, raw_segments)`` with ``source == "auto_subs"`` or ``None`` if ``yt-dlp`` is
    unavailable or produced no usable subtitle file.
    """
    import shutil
    import subprocess
    import tempfile
    import time

    if shutil.which("yt-dlp") is None:
        return None

    cleanup_dir: tempfile.TemporaryDirectory[str] | None = None
    if workdir is None:
        cleanup_dir = tempfile.TemporaryDirectory(prefix="ict_subs_")
        out_dir = Path(cleanup_dir.name)
    else:
        out_dir = Path(workdir)
        out_dir.mkdir(parents=True, exist_ok=True)
    try:
        command = [
            "yt-dlp",
            "--write-auto-subs",
            "--skip-download",
            "--sub-langs",
            ",".join(languages),
            "--sub-format",
            "vtt",
            "-o",
            str(out_dir / "%(id)s.%(ext)s"),
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        for attempt in range(retries + 1):
            try:
                proc = subprocess.run(command, capture_output=True, text=True)
            except OSError:
                return None
            vtt_files = sorted(out_dir.glob(f"{video_id}*.vtt"))
            if vtt_files:
                segments = parse_vtt(
                    vtt_files[0].read_text(encoding="utf-8", errors="replace")
                )
                if segments:
                    return "auto_subs", [
                        {"text": seg["text"], "start": seg["start"], "end": seg["end"]}
                        for seg in segments
                    ]
                return None
            combined = f"{proc.stdout or ''}\n{proc.stderr or ''}".lower()
            rate_limited = any(token in combined for token in _RATE_LIMIT_TOKENS)
            if attempt < retries and rate_limited:
                time.sleep(backoff * (2**attempt))
                continue
            return None
        return None
    finally:
        if cleanup_dir is not None:
            cleanup_dir.cleanup()


def fetch_transcript(
    video_id: str,
    *,
    languages: Sequence[str] = DEFAULT_LANGUAGES,
    workdir: str | Path | None = None,
    retries: int = DEFAULT_FETCH_RETRIES,
    backoff: float = DEFAULT_FETCH_BACKOFF_S,
) -> tuple[str, list[dict[str, Any]]] | None:
    """Fetch a transcript, preferring manual captions, then auto-generated captions.

    Step order matches the Phase A spec: youtube-transcript-api first (manual captions if
    present, otherwise its generated track), then a ``yt-dlp --write-auto-subs --skip-download``
    fallback. Both backends retry with exponential backoff on YouTube rate-limit / IP-block
    errors. Network-bound; the optional dependencies are imported lazily.

    Args:
        video_id: YouTube video id.
        languages: Caption language priority list.
        workdir: Optional directory for ``yt-dlp`` subtitle downloads (a temp dir by default).
        retries: Number of additional attempts per backend on rate-limit errors.
        backoff: Base backoff seconds; attempt ``n`` waits ``backoff * 2**n``.

    Returns:
        ``(source, raw_segments)`` where ``source`` is ``"captions"`` or ``"auto_subs"`` and
        ``raw_segments`` is a list of raw snippet mappings, or ``None`` if no transcript could
        be retrieved (caller should log the video to ``_missing.csv`` and continue).
    """
    result = _fetch_via_transcript_api(
        video_id, languages=languages, retries=retries, backoff=backoff
    )
    if result is not None:
        return result
    return _fetch_via_yt_dlp(
        video_id, languages=languages, workdir=workdir, retries=retries, backoff=backoff
    )
