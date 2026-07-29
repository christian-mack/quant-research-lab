"""Unit tests for the PCS manifest parser/validator/scaffold (D2).

Failure paths are the point of this milestone: an UNCLASSIFIED or missing entry
MUST block indexing before any chunk is written (spec section 4.4 point 5).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from quant_research.context import manifest as m
from quant_research.context.config import repo_root
from quant_research.context.manifest import (
    TIER1_PINNED_DOCS,
    TIER2_ENTRY_LOGS,
    UNCLASSIFIED,
    VALID_STATUSES,
    ManifestError,
    assert_manifest_valid,
    iter_dated_entries,
    iter_latent_split,
    iter_split_required,
    render_scaffold,
    resolve_whole_file_docs,
    validate_manifest,
)

MINI_LOG = "docs/mini-log.md"
MINI_DOC = "docs/doc-a.md"
MINI_LOG_TEXT = """# Mini Log

## 2026-01-02 — Alpha finding

**Phase:** 1
First body line of alpha.

### A sub-heading that must be ignored

## 2026-01-01 — Beta finding

**Phase:** 2
First body line of beta.

## Entry template (not dated, must be ignored)
"""


def _write_mini_corpus(tmp_path: Path) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "mini-log.md").write_text(MINI_LOG_TEXT, encoding="utf-8")
    (docs / "doc-a.md").write_text("# Doc A\n\nsome content\n", encoding="utf-8")
    return tmp_path


def _validate(tmp_path: Path, manifest: dict) -> list[str]:
    return validate_manifest(
        manifest,
        tmp_path,
        whole_file_docs=(MINI_DOC,),
        entry_logs=(MINI_LOG,),
        pinned_docs=(),  # Tier-1 validation is exercised separately, below.
    )


def _valid_manifest() -> dict:
    return {
        "documents": {MINI_DOC: {"status": "current"}},
        "entries": {
            MINI_LOG: [
                {"heading": "2026-01-02 — Alpha finding", "status": "current"},
                {
                    "heading": "2026-01-01 — Beta finding",
                    "status": "superseded",
                    "superseded_by": "docs/mini-log.md :: 2026-01-02 — Alpha finding",
                },
            ]
        },
    }


# --------------------------------------------------------------------------- #
# Enumeration
# --------------------------------------------------------------------------- #
def test_iter_dated_entries_parses_headings_and_skips_noise(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    entries = iter_dated_entries(tmp_path / MINI_LOG, MINI_LOG)
    headings = [e.heading for e in entries]
    assert headings == ["2026-01-02 — Alpha finding", "2026-01-01 — Beta finding"]
    assert entries[0].entry_date == date(2026, 1, 2)
    assert entries[0].excerpt == "**Phase:** 1"
    # sub-headings ("### ") and undated headings ("## Entry template") are skipped.
    assert all("sub-heading" not in h for h in headings)
    assert all("template" not in h for h in headings)


def test_iter_dated_entries_matches_real_lessons_log() -> None:
    entries = iter_dated_entries(repo_root() / "docs/lessons-log.md", "docs/lessons-log.md")
    headings = {e.heading for e in entries}
    assert (
        "2026-05-13 — Correction: ~$10,885/yr was qty=10 total, "
        "not per contract; M6 closes" in headings
    )
    # dates are NOT unique keys: seven distinct entries share 2026-04-28.
    same_day = [e for e in entries if e.entry_date == date(2026, 4, 28)]
    assert len(same_day) == 7
    assert len({e.heading for e in same_day}) == 7


# --------------------------------------------------------------------------- #
# Failure paths
# --------------------------------------------------------------------------- #
def test_unclassified_entry_fails(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["entries"][MINI_LOG][0]["status"] = UNCLASSIFIED
    errors = _validate(tmp_path, manifest)
    assert any("still UNCLASSIFIED" in e for e in errors)


def test_missing_entry_fails(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["entries"][MINI_LOG].pop()  # drop Beta
    errors = _validate(tmp_path, manifest)
    assert any("not classified in manifest" in e and "Beta finding" in e for e in errors)


def test_superseded_without_pointer_fails(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["entries"][MINI_LOG][1].pop("superseded_by")
    errors = _validate(tmp_path, manifest)
    assert any("requires a 'superseded_by'" in e for e in errors)


def test_deprecated_document_without_pointer_fails(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["documents"][MINI_DOC] = {"status": "deprecated"}
    errors = _validate(tmp_path, manifest)
    assert any("requires a 'superseded_by'" in e for e in errors)


def test_invalid_status_fails(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["entries"][MINI_LOG][0]["status"] = "stale"
    errors = _validate(tmp_path, manifest)
    assert any("invalid status 'stale'" in e for e in errors)


def test_stale_manifest_heading_fails(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["entries"][MINI_LOG].append(
        {"heading": "2099-01-01 — Not in the file", "status": "current"}
    )
    errors = _validate(tmp_path, manifest)
    assert any("stale" in e and "Not in the file" in e for e in errors)


def test_unknown_document_key_fails(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["documents"]["docs/not-a-tier2-doc.md"] = {"status": "current"}
    errors = _validate(tmp_path, manifest)
    assert any("unknown document" in e for e in errors)


def test_date_mismatch_fails(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["entries"][MINI_LOG][0]["date"] = "2020-12-31"
    errors = _validate(tmp_path, manifest)
    assert any("date" in e and "!=" in e for e in errors)


def test_assert_manifest_valid_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="manifest not found"):
        assert_manifest_valid(repo_root=tmp_path, manifest_path=tmp_path / "nope.yml")


# --------------------------------------------------------------------------- #
# split_required (D3 chunk-split debt)
# --------------------------------------------------------------------------- #
def test_split_required_without_note_fails(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["entries"][MINI_LOG][0]["split_required"] = True
    errors = _validate(tmp_path, manifest)
    assert any("split_required" in e and "split_note" in e for e in errors)


def test_split_required_with_note_passes_and_is_surfaced(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    entry = manifest["entries"][MINI_LOG][0]
    entry["split_required"] = True
    entry["split_note"] = "stale number becomes its own superseded chunk"
    entry["split_anchor"] = ["stale: $10,885/yr per contract"]
    entry["split_superseded_by"] = "docs/mini-log.md :: 2026-01-01 — Beta finding"
    assert _validate(tmp_path, manifest) == []
    pending = iter_split_required(manifest)
    assert len(pending) == 1
    assert pending[0].location == f"{MINI_LOG} :: 2026-01-02 — Alpha finding"
    assert "superseded chunk" in pending[0].split_note
    assert pending[0].anchors == ("stale: $10,885/yr per contract",)
    assert pending[0].superseded_by == "docs/mini-log.md :: 2026-01-01 — Beta finding"


def test_split_required_without_anchor_fails(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    entry = manifest["entries"][MINI_LOG][0]
    entry["split_required"] = True
    entry["split_note"] = "has note but no anchor"
    errors = _validate(tmp_path, manifest)
    assert any("split_anchor" in e for e in errors)
    assert any("split_superseded_by" in e for e in errors)


# --------------------------------------------------------------------------- #
# latent_split_note (off-surface recorded debt)
# --------------------------------------------------------------------------- #
def test_latent_split_note_on_historical_passes_and_is_surfaced(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["entries"][MINI_LOG][1]["status"] = "historical"
    manifest["entries"][MINI_LOG][1].pop("superseded_by", None)
    manifest["entries"][MINI_LOG][1]["latent_split_note"] = "stale number, split only if recalled"
    assert _validate(tmp_path, manifest) == []
    latent = iter_latent_split(manifest)
    assert len(latent) == 1
    assert latent[0].location == f"{MINI_LOG} :: 2026-01-01 — Beta finding"


def test_latent_split_note_on_current_is_rejected(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["entries"][MINI_LOG][0]["latent_split_note"] = "should have used split_required"
    errors = _validate(tmp_path, manifest)
    assert any("latent_split_note" in e and "split_required" in e for e in errors)


# --------------------------------------------------------------------------- #
# Tier-1 pinned classification (spec §4.1)
# --------------------------------------------------------------------------- #
def _pinned_corpus(tmp_path: Path) -> tuple[str, str]:
    docs = tmp_path / "docs"
    docs.mkdir(exist_ok=True)
    rel = "docs/pin-a.md"
    (tmp_path / rel).write_text("# Pin A\n\ncurrent-state doc\n", encoding="utf-8")
    return rel, rel


def test_pinned_doc_must_be_current(tmp_path: Path) -> None:
    rel, _ = _pinned_corpus(tmp_path)
    manifest = {"pinned": {rel: {"tier": 1, "status": "historical"}}}
    errors = validate_manifest(
        manifest, tmp_path, whole_file_docs=(), entry_logs=(), pinned_docs=(rel,)
    )
    assert any("must be" in e and "current" in e for e in errors)


def test_pinned_doc_missing_from_manifest_fails(tmp_path: Path) -> None:
    rel, _ = _pinned_corpus(tmp_path)
    errors = validate_manifest(
        {"pinned": {}}, tmp_path, whole_file_docs=(), entry_logs=(), pinned_docs=(rel,)
    )
    assert any("not classified in manifest" in e and rel in e for e in errors)


def test_pinned_doc_also_in_tier2_is_rejected(tmp_path: Path) -> None:
    rel, _ = _pinned_corpus(tmp_path)
    manifest = {
        "pinned": {rel: {"tier": 1, "status": "current"}},
        "documents": {rel: {"status": "current"}},
    }
    errors = validate_manifest(
        manifest, tmp_path, whole_file_docs=(rel,), entry_logs=(), pinned_docs=(rel,)
    )
    assert any("also listed as Tier-2" in e for e in errors)


def test_real_manifest_pins_flux_response_style_as_current_tier1_not_tier2() -> None:
    root = repo_root()
    manifest = m.load_manifest(root / m.MANIFEST_PATH_REL)
    rel = "docs/flux-response-style.md"
    assert rel in TIER1_PINNED_DOCS
    block = manifest["pinned"][rel]
    assert block["status"] == "current"
    # Excluded from every Tier-2 path (never chunked/embedded).
    tier2 = set(resolve_whole_file_docs(root)) | set(TIER2_ENTRY_LOGS)
    assert rel not in tier2
    assert not (set(TIER1_PINNED_DOCS) & tier2)


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #
def test_fully_classified_manifest_passes(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    assert _validate(tmp_path, _valid_manifest()) == []


def test_matching_date_field_is_accepted(tmp_path: Path) -> None:
    _write_mini_corpus(tmp_path)
    manifest = _valid_manifest()
    manifest["entries"][MINI_LOG][0]["date"] = "2026-01-02"
    assert _validate(tmp_path, manifest) == []


# --------------------------------------------------------------------------- #
# Sentinel + scaffold
# --------------------------------------------------------------------------- #
def test_sentinel_is_not_a_valid_status() -> None:
    assert UNCLASSIFIED not in VALID_STATUSES


def test_scaffold_round_trips_and_only_unclassified_blocks() -> None:
    root = repo_root()
    text = render_scaffold(root)
    data = yaml.safe_load(text)

    assert set(data["documents"]) == set(m.resolve_whole_file_docs(root))
    # Tier-1 pinned docs are emitted pre-filled 'current' (structural, not a worklist item).
    assert set(data["pinned"]) == set(TIER1_PINNED_DOCS)
    assert all(block["status"] == "current" for block in data["pinned"].values())
    for log in m.TIER2_ENTRY_LOGS:
        assert log in data["entries"]
        for item in data["entries"][log]:
            assert "heading" in item and "status" in item

    # The scaffold is a worklist: every remaining issue is UNCLASSIFIED — never a
    # stale/missing/invalid error. If any non-UNCLASSIFIED error appears, the
    # generator and validator have drifted apart.
    errors = validate_manifest(data, root)
    assert errors, "a fresh scaffold must not validate clean"
    assert all("still UNCLASSIFIED" in e for e in errors)

    # The three suggested supersessions validate cleanly.
    lessons = {i["heading"]: i for i in data["entries"]["docs/lessons-log.md"]}
    suggested = [h for h, i in lessons.items() if i["status"] == "superseded"]
    assert len(suggested) == 3
    assert all(lessons[h]["superseded_by"] for h in suggested)
