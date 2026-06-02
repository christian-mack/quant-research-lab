"""Network-free unit tests for the ICT transcript ingestion core.

All fixtures are synthetic and in-memory: no YouTube access, no youtube-transcript-api, and no
yt-dlp. Covers manifest parsing, normalization/missing-field handling, word-boundary keyword
matching, context-window assembly, and the every-concept-vs-every-video citation map.
"""

from __future__ import annotations

from pathlib import Path

from quant_research.utils.transcript_ingest import (
    BIAS_LEXICON,
    CONCEPT_LEXICON,
    BiasManifestRow,
    ManifestRow,
    build_bias_concept_map,
    build_citation_map,
    find_keyword_hits,
    log_missing,
    normalize_bias_transcript,
    normalize_segment,
    normalize_transcript,
    parse_concept_tags,
    parse_vtt,
    read_bias_manifest,
    read_manifest,
)


def _segments(*texts: str) -> list[dict[str, float | str]]:
    """Build evenly spaced 1-second segments from text strings."""
    return [
        {"start": float(i), "end": float(i) + 1.0, "text": text}
        for i, text in enumerate(texts)
    ]


# --------------------------------------------------------------------------------------------
# Word-boundary matching
# --------------------------------------------------------------------------------------------
def test_word_boundary_does_not_match_ote_inside_promote() -> None:
    segments = _segments("I promote this idea", "Take the OTE entry")
    hits = find_keyword_hits(segments, ["OTE"], context=0)
    assert len(hits) == 1
    assert hits[0]["start"] == 1.0
    assert hits[0]["matched_keywords"] == ["OTE"]


def test_keyword_match_is_case_insensitive() -> None:
    segments = _segments("price found LIQUIDITY above")
    hits = find_keyword_hits(segments, ["liquidity"], context=0)
    assert len(hits) == 1


def test_multiword_phrase_matches_across_spaces() -> None:
    segments = _segments("this is a fair value gap here", "a fair   value   gap again")
    hits = find_keyword_hits(segments, ["fair value gap"], context=0)
    assert len(hits) == 2


def test_punctuation_tokens_match_cleanly() -> None:
    segments = _segments("open at 8:30 sharp", "the 50% level", "near 850 ticks")
    hits_time = find_keyword_hits(segments, ["8:30"], context=0)
    hits_pct = find_keyword_hits(segments, ["50%"], context=0)
    assert [h["start"] for h in hits_time] == [0.0]
    assert [h["start"] for h in hits_pct] == [1.0]


def test_single_segment_with_multiple_keywords_yields_one_hit() -> None:
    segments = _segments("buyside liquidity sweep above old highs")
    hits = find_keyword_hits(segments, ["liquidity", "sweep", "buyside"], context=0)
    assert len(hits) == 1
    assert hits[0]["matched_keywords"] == ["buyside", "liquidity", "sweep"]


# --------------------------------------------------------------------------------------------
# Context-window assembly
# --------------------------------------------------------------------------------------------
def test_context_window_includes_two_adjacent_segments_each_side() -> None:
    segments = _segments("zero", "one", "match liquidity", "three", "four", "five")
    hits = find_keyword_hits(segments, ["liquidity"], context=2)
    assert len(hits) == 1
    window_texts = [seg["text"] for seg in hits[0]["context"]]
    assert window_texts == ["zero", "one", "match liquidity", "three", "four"]


def test_context_window_clamped_at_start_boundary() -> None:
    segments = _segments("match sweep here", "one", "two")
    hits = find_keyword_hits(segments, ["sweep"], context=2)
    window_texts = [seg["text"] for seg in hits[0]["context"]]
    assert window_texts == ["match sweep here", "one", "two"]


def test_context_window_clamped_at_end_boundary() -> None:
    segments = _segments("zero", "one", "match raid now")
    hits = find_keyword_hits(segments, ["raid"], context=2)
    window_texts = [seg["text"] for seg in hits[0]["context"]]
    assert window_texts == ["zero", "one", "match raid now"]


def test_context_zero_returns_only_matched_segment() -> None:
    segments = _segments("zero", "match judas swing", "two")
    hits = find_keyword_hits(segments, ["judas"], context=0)
    assert [seg["text"] for seg in hits[0]["context"]] == ["match judas swing"]


# --------------------------------------------------------------------------------------------
# Missing-field handling / normalization
# --------------------------------------------------------------------------------------------
def test_normalize_segment_derives_end_from_duration() -> None:
    seg = normalize_segment({"text": "hello", "start": 2.0, "duration": 1.5})
    assert seg == {"start": 2.0, "end": 3.5, "text": "hello"}


def test_normalize_segment_missing_text_becomes_empty_string() -> None:
    seg = normalize_segment({"start": 5.0, "duration": 1.0})
    assert seg["text"] == ""


def test_normalize_segment_missing_start_defaults_zero_and_no_duration() -> None:
    seg = normalize_segment({"text": "orphan"})
    assert seg == {"start": 0.0, "end": 0.0, "text": "orphan"}


def test_normalize_segment_prefers_explicit_end_over_duration() -> None:
    seg = normalize_segment({"text": "x", "start": 1.0, "end": 4.0, "duration": 99.0})
    assert seg["end"] == 4.0


def test_normalize_segment_non_numeric_start_falls_back() -> None:
    seg = normalize_segment({"text": "x", "start": "bad", "duration": "also-bad"})
    assert seg == {"start": 0.0, "end": 0.0, "text": "x"}


def test_normalize_transcript_sorts_segments_and_sets_schema() -> None:
    raw = [
        {"text": "later", "start": 5.0, "duration": 1.0},
        {"text": "earlier", "start": 1.0, "duration": 1.0},
    ]
    doc = normalize_transcript(
        video_id="vid1",
        title="Title",
        url="https://youtu.be/vid1",
        era="2022",
        concept_tags=["spec_a_sweep"],
        source="captions",
        raw_segments=raw,
    )
    assert doc["video_id"] == "vid1"
    assert doc["source"] == "captions"
    assert doc["concept_tags"] == ["spec_a_sweep"]
    assert [seg["text"] for seg in doc["segments"]] == ["earlier", "later"]


# --------------------------------------------------------------------------------------------
# Manifest parsing
# --------------------------------------------------------------------------------------------
def test_parse_concept_tags_pipe_separated() -> None:
    assert parse_concept_tags("spec_a_sweep|settlement") == ("spec_a_sweep", "settlement")


def test_parse_concept_tags_all_expands_to_every_concept() -> None:
    assert parse_concept_tags("all") == tuple(CONCEPT_LEXICON)


def test_parse_concept_tags_empty_expands_to_every_concept() -> None:
    assert parse_concept_tags("") == tuple(CONCEPT_LEXICON)


def test_read_manifest_missing_file_raises(tmp_path: Path) -> None:
    try:
        read_manifest(tmp_path / "does_not_exist.csv")
    except FileNotFoundError as exc:
        assert "do not guess video IDs" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("expected FileNotFoundError for a missing manifest")


def test_read_manifest_parses_rows(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "video_id,title,url,era,concept_tags\n"
        "abc123,Sample One,https://youtu.be/abc123,2022,spec_a_sweep|spec_b_pd\n"
        "def456,Sample Two,https://youtu.be/def456,2016,all\n",
        encoding="utf-8",
    )
    rows = read_manifest(manifest)
    assert rows[0] == ManifestRow(
        video_id="abc123",
        title="Sample One",
        url="https://youtu.be/abc123",
        era="2022",
        concept_tags=("spec_a_sweep", "spec_b_pd"),
    )
    assert rows[1].era == "2016"
    assert rows[1].concept_tags == tuple(CONCEPT_LEXICON)


def test_read_manifest_invalid_era_raises(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "video_id,title,url,era,concept_tags\n"
        "abc123,Sample,https://youtu.be/abc123,1999,all\n",
        encoding="utf-8",
    )
    try:
        read_manifest(manifest)
    except ValueError as exc:
        assert "invalid era" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("expected ValueError for an invalid era")


def test_read_manifest_missing_column_raises(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("video_id,title,url,era\nabc,Title,url,2022\n", encoding="utf-8")
    try:
        read_manifest(manifest)
    except ValueError as exc:
        assert "concept_tags" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("expected ValueError for a missing column")


# --------------------------------------------------------------------------------------------
# Citation map: every concept scanned against every video regardless of tags
# --------------------------------------------------------------------------------------------
def test_build_citation_map_scans_all_concepts_against_all_videos() -> None:
    video_a = normalize_transcript(
        video_id="vidA",
        title="A",
        url="https://youtu.be/vidA",
        era="2022",
        concept_tags=["spec_b_pd"],  # tagged ONLY spec_b, but mentions a session-timing term
        source="captions",
        raw_segments=_segments("trade the london killzone open", "premium to discount move"),
    )
    video_b = normalize_transcript(
        video_id="vidB",
        title="B",
        url="https://youtu.be/vidB",
        era="other",
        concept_tags=["session_timing"],
        source="auto_subs",
        raw_segments=_segments("new day opening gap NDOG fill"),
    )
    citation_map = build_citation_map([video_a, video_b])

    # Tag was spec_b only, but session_timing keywords are still found in video_a.
    session_videos = {hit["video_id"] for hit in citation_map["session_timing"]}
    assert "vidA" in session_videos

    pd_videos = {hit["video_id"] for hit in citation_map["spec_b_pd"]}
    assert "vidA" in pd_videos

    gap_videos = {hit["video_id"] for hit in citation_map["spec_c_gap"]}
    assert "vidB" in gap_videos


def test_citation_hit_carries_schema_fields() -> None:
    video = normalize_transcript(
        video_id="vidC",
        title="C",
        url="https://youtu.be/vidC",
        era="2022",
        concept_tags=["spec_a_sweep"],
        source="captions",
        raw_segments=_segments("before", "a clean liquidity sweep", "after"),
    )
    citation_map = build_citation_map([video], context=1)
    hits = citation_map["spec_a_sweep"]
    assert len(hits) == 1
    hit = hits[0]
    for key in ("video_id", "title", "url", "start", "text", "context", "matched_keywords"):
        assert key in hit
    assert hit["video_id"] == "vidC"
    assert [seg["text"] for seg in hit["context"]] == [
        "before",
        "a clean liquidity sweep",
        "after",
    ]


def test_build_citation_map_accepts_custom_lexicon() -> None:
    video = normalize_transcript(
        video_id="vidD",
        title="D",
        url="https://youtu.be/vidD",
        era="2022",
        concept_tags=["all"],
        source="captions",
        raw_segments=_segments("the unicorn pattern appears"),
    )
    citation_map = build_citation_map([video], lexicon={"custom": ["unicorn"]})
    assert set(citation_map) == {"custom"}
    assert len(citation_map["custom"]) == 1


# --------------------------------------------------------------------------------------------
# VTT parser (yt-dlp fallback path) and missing-log helper
# --------------------------------------------------------------------------------------------
def test_parse_vtt_extracts_timed_cues() -> None:
    vtt = (
        "WEBVTT\n"
        "\n"
        "00:00:01.000 --> 00:00:03.000\n"
        "first <c>cue</c> line\n"
        "\n"
        "00:00:03.500 --> 00:00:05.000 align:start position:0%\n"
        "second cue\n"
    )
    segments = parse_vtt(vtt)
    assert segments == [
        {"start": 1.0, "end": 3.0, "text": "first cue line"},
        {"start": 3.5, "end": 5.0, "text": "second cue"},
    ]


def test_log_missing_writes_header_then_appends(tmp_path: Path) -> None:
    missing = tmp_path / "_missing.csv"
    row = ManifestRow("vidX", "Title X", "https://youtu.be/vidX", "2022", ("all",))
    log_missing(missing, row, "no_transcript")
    log_missing(missing, row, "no_transcript")
    lines = missing.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "video_id,title,url,era,reason"
    assert len(lines) == 3  # header + two appended rows


# --------------------------------------------------------------------------------------------
# Daily-bias corpus: lexicon word-boundary correctness (kept distinct from 2022 corpus)
# --------------------------------------------------------------------------------------------
def test_bias_lexicon_matches_consequent_encroachment_phrase() -> None:
    segments = _segments("price tagged the consequent encroachment of the gap")
    hits = find_keyword_hits(segments, BIAS_LEXICON["midpoint_validation"], context=0)
    assert len(hits) == 1
    assert "consequent encroachment" in hits[0]["matched_keywords"]


def test_bias_lexicon_short_token_does_not_match_inside_larger_word() -> None:
    # "bos" (break of structure abbrev) must not match inside "embossed"; "mss" not in "dismiss".
    segments = _segments("the logo was embossed", "do not dismiss this")
    assert find_keyword_hits(segments, ["bos"], context=0) == []
    assert find_keyword_hits(segments, ["mss"], context=0) == []


def test_bias_lexicon_short_token_matches_standalone() -> None:
    segments = _segments("we got a BOS confirmation", "then an MSS to the upside")
    bos_hits = find_keyword_hits(segments, ["bos"], context=0)
    mss_hits = find_keyword_hits(segments, ["mss"], context=0)
    assert [h["start"] for h in bos_hits] == [0.0]
    assert [h["start"] for h in mss_hits] == [1.0]


def test_bias_lexicon_omits_bare_two_letter_abbreviation() -> None:
    # "ce" is intentionally NOT a keyword; only the spelled-out phrase should fire.
    assert "ce" not in BIAS_LEXICON["midpoint_validation"]
    segments = _segments("the ce of the range", "the ace was high")
    hits = find_keyword_hits(segments, BIAS_LEXICON["midpoint_validation"], context=0)
    assert hits == []


def test_bias_lexicon_50pct_token_matches_cleanly() -> None:
    segments = _segments("retraced to the 50% level", "near 500 ticks")
    hits = find_keyword_hits(segments, ["50%"], context=0)
    assert [h["start"] for h in hits] == [0.0]


# --------------------------------------------------------------------------------------------
# Daily-bias corpus: manifest, normalization, per-video concept map
# --------------------------------------------------------------------------------------------
def test_read_bias_manifest_parses_rows_including_leading_hyphen_id(tmp_path: Path) -> None:
    manifest = tmp_path / "bias_manifest.csv"
    manifest.write_text(
        "video_id,title,url,creator,role,corpus\n"
        "x4FJVEZUXhc,JadeCap,https://www.youtube.com/watch?v=x4FJVEZUXhc,jadecap,primary,bias\n"
        "-KKuZb5Z5aU,TTrades,https://www.youtube.com/watch?v=-KKuZb5Z5aU,ttrades,supplement,bias\n",
        encoding="utf-8",
    )
    rows = read_bias_manifest(manifest)
    assert rows[0] == BiasManifestRow(
        video_id="x4FJVEZUXhc",
        title="JadeCap",
        url="https://www.youtube.com/watch?v=x4FJVEZUXhc",
        creator="jadecap",
        role="primary",
        corpus="bias",
    )
    # Leading-hyphen video id is preserved verbatim as a value.
    assert rows[1].video_id == "-KKuZb5Z5aU"
    assert rows[1].role == "supplement"


def test_read_bias_manifest_invalid_role_raises(tmp_path: Path) -> None:
    manifest = tmp_path / "bias_manifest.csv"
    manifest.write_text(
        "video_id,title,url,creator,role,corpus\n"
        "abc123,Sample,https://youtu.be/abc123,someone,tertiary,bias\n",
        encoding="utf-8",
    )
    try:
        read_bias_manifest(manifest)
    except ValueError as exc:
        assert "invalid role" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("expected ValueError for an invalid role")


def test_read_bias_manifest_missing_column_raises(tmp_path: Path) -> None:
    manifest = tmp_path / "bias_manifest.csv"
    manifest.write_text(
        "video_id,title,url,creator,role\nabc,Title,url,someone,primary\n", encoding="utf-8"
    )
    try:
        read_bias_manifest(manifest)
    except ValueError as exc:
        assert "corpus" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("expected ValueError for a missing column")


def test_read_bias_manifest_missing_file_raises(tmp_path: Path) -> None:
    try:
        read_bias_manifest(tmp_path / "absent.csv")
    except FileNotFoundError as exc:
        assert "do not guess video IDs" in str(exc)
    else:  # pragma: no cover - explicit failure path
        raise AssertionError("expected FileNotFoundError for a missing bias manifest")


def test_normalize_bias_transcript_sets_schema_and_sorts() -> None:
    raw = [
        {"text": "later", "start": 5.0, "duration": 1.0},
        {"text": "earlier", "start": 1.0, "duration": 1.0},
    ]
    doc = normalize_bias_transcript(
        video_id="vid1",
        title="Title",
        url="https://youtu.be/vid1",
        creator="jadecap",
        role="primary",
        source="captions",
        raw_segments=raw,
    )
    assert doc["creator"] == "jadecap"
    assert doc["role"] == "primary"
    assert doc["corpus"] == "bias"
    assert doc["source"] == "captions"
    assert [seg["text"] for seg in doc["segments"]] == ["earlier", "later"]


def test_build_bias_concept_map_single_video_metadata_and_primary_flag() -> None:
    transcript = normalize_bias_transcript(
        video_id="x4FJVEZUXhc",
        title="JadeCap",
        url="https://www.youtube.com/watch?v=x4FJVEZUXhc",
        creator="jadecap",
        role="primary",
        source="captions",
        raw_segments=_segments(
            "we look for the daily bias first",
            "draw on liquidity into the previous day high",
            "premium and discount inside the dealing range",
        ),
    )
    bias_map = build_bias_concept_map(transcript, git_sha="abc1234")
    assert bias_map["creator"] == "jadecap"
    assert bias_map["role"] == "primary"
    assert bias_map["video_id"] == "x4FJVEZUXhc"
    assert bias_map["primary"] is True
    assert bias_map["git_sha"] == "abc1234"
    assert set(bias_map["concepts"]) == set(BIAS_LEXICON)
    core_hits = bias_map["concepts"]["bias_core"]
    assert any("daily bias" in hit["matched_keywords"] for hit in core_hits)
    assert all(hit["creator"] == "jadecap" and hit["role"] == "primary" for hit in core_hits)


def test_build_bias_concept_map_supplement_sets_primary_false() -> None:
    transcript = normalize_bias_transcript(
        video_id="-KKuZb5Z5aU",
        title="TTrades",
        url="https://www.youtube.com/watch?v=-KKuZb5Z5aU",
        creator="ttrades",
        role="supplement",
        source="auto_subs",
        raw_segments=_segments("the market is consolidating with no clear bias"),
    )
    bias_map = build_bias_concept_map(transcript)
    assert bias_map["primary"] is False
    assert bias_map["role"] == "supplement"
    assert "git_sha" not in bias_map  # omitted when not supplied
    no_bias_hits = bias_map["concepts"]["no_clear_bias"]
    assert any("consolidating" in hit["matched_keywords"] for hit in no_bias_hits)
