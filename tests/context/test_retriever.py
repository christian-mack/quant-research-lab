"""Retriever tests (D5, spec §5.2 + §4.4).

The two load-bearing tests enforce the locked D5 constraints:

* **Filter-before-fusion** — the ~$10,885/contract *misread* (superseded) is absent
  from the semantic *and* lexical candidate pools by default, not merely trimmed
  from the final top-k. Proven by calling the candidate SQL functions directly.
* **Labeled recall** — under ``include_superseded=True`` the misread arrives with a
  ``[SUPERSEDED by ... 2026-05-13 ...]`` prefix in the text an agent reads.
"""

from __future__ import annotations

import psycopg
import pytest
from pgvector.psycopg import register_vector

from quant_research.context.config import PCSConfig
from quant_research.context.retriever import (
    lexical_candidates,
    rrf_fuse,
    search,
    semantic_candidates,
)

MISREAD_LIKE = "%$10,885/yr per contract%"  # carved superseded fragment (Production-cut)
CORRECTION_BREADCRUMB_LIKE = "%2026-05-13 — Correction%"


def _misread_chunk(cfg: PCSConfig) -> tuple[int, str]:
    """Return (id, embed_text) of the superseded ~$10,885/contract misread chunk."""
    with psycopg.connect(cfg.dsn()) as conn:
        row = conn.execute(
            "SELECT id, embed_text FROM pcs_chunk "
            "WHERE status = 'superseded' AND chunk_text LIKE %s LIMIT 1",
            (MISREAD_LIKE,),
        ).fetchone()
    assert row is not None, "expected a superseded misread chunk in the index"
    return row[0], row[1]


def _correction_chunk_id(cfg: PCSConfig) -> int:
    with psycopg.connect(cfg.dsn()) as conn:
        row = conn.execute(
            "SELECT id FROM pcs_chunk "
            "WHERE status = 'current' AND breadcrumb LIKE %s AND chunk_text LIKE %s LIMIT 1",
            (CORRECTION_BREADCRUMB_LIKE, "%10,885%"),
        ).fetchone()
    assert row is not None, "expected the 2026-05-13 correction as a current chunk"
    return row[0]


# --------------------------------------------------------------------------- #
# Pure fusion
# --------------------------------------------------------------------------- #
def test_rrf_fuse_rewards_agreement_and_rank() -> None:
    # id 7 is rank-1 in both arms → highest; agreement beats a single strong hit.
    fused = rrf_fuse([7, 3, 1], [7, 5], k=60)
    assert fused[7] == pytest.approx(1 / 61 + 1 / 61)  # both arms, rank 1
    assert fused[3] == pytest.approx(1 / 62)  # semantic rank 2 only
    assert fused[1] == pytest.approx(1 / 63)  # semantic rank 3 only
    assert fused[5] == pytest.approx(1 / 62)  # lexical rank 2 only
    assert fused[7] > fused[3] > fused[1]
    assert fused[3] == pytest.approx(fused[5])
    assert max(fused, key=lambda c: fused[c]) == 7


def test_rrf_fuse_empty_is_empty() -> None:
    assert rrf_fuse([], []) == {}


def test_normalize_lexical_query_unwraps_compound_identifiers() -> None:
    from quant_research.context.retriever import _normalize_lexical_query

    assert "ORB Opt3" in _normalize_lexical_query("ORB+Opt3 per-contract")
    assert "R q" in _normalize_lexical_query("max sustainable qty R(q)")
    assert "MES" in _normalize_lexical_query("MES+MNQ cross-instrument")


# --------------------------------------------------------------------------- #
# Identifier-heavy lexical regression (D7 / D8 — not golden-query paraphrases)
# --------------------------------------------------------------------------- #
def test_search_orb_plus_opt3_non_golden_wording(indexed_config, fake_embedder) -> None:
    """Full search path: ORB+Opt3 compound identifier, non-golden phrasing."""
    results = search(
        "ORB+Opt3 per-contract figure",
        top_k=3,
        config=indexed_config,
        embedder=fake_embedder,
    )
    assert results
    assert any("2026-05-13" in r.breadcrumb for r in results)


def test_search_dll_and_sizing_identifiers(indexed_config, fake_embedder) -> None:
    """DLL and sizing vocabulary retrieve distinct current hits."""
    dll = search(
        "Apex EOD DLL session pause",
        top_k=3,
        config=indexed_config,
        embedder=fake_embedder,
    )
    sizing = search(
        "max sustainable qty ORB+Opt3",
        top_k=3,
        config=indexed_config,
        embedder=fake_embedder,
    )
    assert dll and sizing
    assert {r.chunk_id for r in dll} != {r.chunk_id for r in sizing}


def test_search_git_sha_artifact_lookup(indexed_config, fake_embedder) -> None:
    """Short git SHAs cited in artifacts must be retrievable."""
    results = search(
        "git 1fe521b M4 migration",
        top_k=5,
        config=indexed_config,
        embedder=fake_embedder,
    )
    assert results
    blob = " ".join(r.chunk_text for r in results)
    assert "1fe521b" in blob


# --------------------------------------------------------------------------- #
# Filter-before-fusion (locked constraint 1)
# --------------------------------------------------------------------------- #
def test_superseded_absent_from_candidate_pools_by_default(indexed_config, fake_embedder) -> None:
    cfg = indexed_config
    misread_id, misread_embed_text = _misread_chunk(cfg)
    correction_id = _correction_chunk_id(cfg)

    # A query embedding identical to the misread's own vector → it would be rank-1
    # in the semantic arm if the status filter did NOT run inside the SQL.
    q_vec = fake_embedder.embed_query(misread_embed_text)

    with psycopg.connect(cfg.dsn()) as conn:
        register_vector(conn)
        sem_default = semantic_candidates(conn, q_vec, limit=30, include_superseded=False)
        sem_all = semantic_candidates(conn, q_vec, limit=30, include_superseded=True)
        lex_default = lexical_candidates(
            conn, "ORB Opt3 per contract", limit=30, include_superseded=False
        )
        lex_all = lexical_candidates(
            conn, "ORB Opt3 per contract", limit=30, include_superseded=True
        )

    # Default: the superseded misread never enters either candidate pool.
    assert misread_id not in sem_default
    assert misread_id not in lex_default
    # With include_superseded it re-enters (proving it was the filter, not absence).
    assert misread_id in sem_all
    assert misread_id in lex_all
    # The current correction is reachable lexically in the default pool.
    assert correction_id in lex_default


def test_default_search_returns_correction_not_misread(indexed_config, fake_embedder) -> None:
    cfg = indexed_config
    misread_id, _ = _misread_chunk(cfg)
    correction_id = _correction_chunk_id(cfg)

    results = search(
        "ORB Opt3 per contract", top_k=20, config=cfg, embedder=fake_embedder
    )
    ids = {r.chunk_id for r in results}
    assert results, "expected at least one result"
    assert all(r.status == "current" for r in results)
    assert misread_id not in ids
    assert correction_id in ids


# --------------------------------------------------------------------------- #
# Labeled recall (locked constraint 2)
# --------------------------------------------------------------------------- #
def test_include_superseded_arrives_labeled(indexed_config, fake_embedder) -> None:
    cfg = indexed_config
    misread_id, misread_embed_text = _misread_chunk(cfg)

    # Query with the misread's own vector so it ranks top under include_superseded.
    results = search(
        misread_embed_text,
        top_k=10,
        include_superseded=True,
        config=cfg,
        embedder=fake_embedder,
    )
    labeled = [r for r in results if r.chunk_id == misread_id]
    assert labeled, "misread must be recallable under include_superseded"
    r = labeled[0]
    assert r.status == "superseded"
    assert r.text.startswith("[SUPERSEDED by ")
    assert "2026-05-13" in r.text  # the correction pointer is rendered in-band
    assert "10,885" in r.text
    # Provenance is inline (§5.2): no second lookup needed.
    assert r.file_path
    assert r.git_sha
    assert r.breadcrumb


def test_include_superseded_excludes_historical_and_deprecated(
    indexed_config, fake_embedder
) -> None:
    """The narrowed flag admits current+superseded only — not archived content."""
    cfg = indexed_config
    with psycopg.connect(cfg.dsn()) as conn:
        hist = conn.execute(
            "SELECT id, embed_text FROM pcs_chunk WHERE status='historical' LIMIT 1"
        ).fetchone()
        dep = conn.execute(
            "SELECT id, embed_text FROM pcs_chunk WHERE status='deprecated' LIMIT 1"
        ).fetchone()
    assert hist is not None, "corpus should contain a historical chunk"
    assert dep is not None, "corpus should contain a deprecated chunk"

    with psycopg.connect(cfg.dsn()) as conn:
        register_vector(conn)
        # Query each archived chunk with its own vector → would be rank-1 if unfiltered.
        for chunk_id, embed_text in (hist, dep):
            q = fake_embedder.embed_query(embed_text)
            sem = semantic_candidates(conn, q, limit=30, include_superseded=True)
            assert chunk_id not in sem  # excluded even under include_superseded


def test_provenance_is_inline_on_current_results(indexed_config, fake_embedder) -> None:
    results = search(
        "ORB Opt3 production cut", top_k=5, config=indexed_config, embedder=fake_embedder
    )
    assert results
    for r in results:
        assert r.breadcrumb and r.file_path and r.git_sha
        assert isinstance(r.score, float) and r.score > 0
        assert r.status == "current"
