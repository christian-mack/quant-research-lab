"""Indexer tests (D4).

The headline is the **idempotence** test (spec D4 exit criterion): a second
reindex with no file changes writes zero rows — no chunks, no document rows, not
even an index-run row. The status/split wiring and provenance columns are also
verified end-to-end against an isolated ``pcs_test`` database so the operator's
real index is never touched.

DB-backed tests skip cleanly when the PCS Postgres container is not running; the
pure ``build_document_chunks`` test always runs.
"""

from __future__ import annotations

import hashlib

import numpy as np
import psycopg
import pytest
from psycopg import sql

from quant_research.context.config import PCSConfig, get_config, repo_root
from quant_research.context.indexer import build_document_chunks, reindex
from quant_research.context.manifest import MANIFEST_PATH_REL, load_manifest
from quant_research.context.migrate import migrate

TEST_DB = "pcs_test"
PRODUCTION_CUT = "Production cut to ORB+Opt3"


class FakeEmbedder:
    """Deterministic unit-vector embedder — no torch, dim matches schema (768)."""

    embed_dim = 768

    def _vec(self, text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "little")
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(self.embed_dim).astype(np.float32)
        v /= np.linalg.norm(v)
        return v.tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


# --------------------------------------------------------------------------- #
# Pure (no DB): split wiring through the manifest
# --------------------------------------------------------------------------- #
def test_build_document_chunks_applies_split_status_from_manifest() -> None:
    root = repo_root()
    manifest = load_manifest(root / MANIFEST_PATH_REL)
    text = (root / "docs/lessons-log.md").read_text(encoding="utf-8")
    chunks = build_document_chunks("docs/lessons-log.md", text, manifest)

    prod = [c for c in chunks if PRODUCTION_CUT in c.breadcrumb]
    assert prod, "Production-cut entry must produce chunks"
    superseded = [c for c in prod if c.status == "superseded"]
    current = [c for c in prod if c.status == "current"]
    assert superseded and current
    assert any("10,885" in c.chunk_text for c in superseded)
    assert all("$10,885/yr per contract" not in c.chunk_text for c in current)
    # chunk_index is unique across the whole document
    assert len({c.chunk_index for c in chunks}) == len(chunks)


# --------------------------------------------------------------------------- #
# DB-backed fixture
# --------------------------------------------------------------------------- #
def _admin_dsn(base: PCSConfig) -> str:
    return (
        f"host={base.db_host} port={base.db_port} dbname={base.db_name} "
        f"user={base.db_user} password={base.db_password}"
    )


@pytest.fixture(scope="module")
def test_config() -> PCSConfig:
    base = get_config()
    try:
        admin = psycopg.connect(_admin_dsn(base), connect_timeout=5, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("PCS Postgres not reachable; skipping DB-backed indexer tests")

    drop = sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(TEST_DB))
    create = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB))
    try:
        with admin.cursor() as cur:
            cur.execute(drop)
            cur.execute(create)
    finally:
        admin.close()

    cfg = PCSConfig(
        db_host=base.db_host,
        db_port=base.db_port,
        db_name=TEST_DB,
        db_user=base.db_user,
        db_password=base.db_password,
    )
    migrate(cfg)
    yield cfg

    admin = psycopg.connect(_admin_dsn(base), connect_timeout=5, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(drop)
    finally:
        admin.close()


def _counts(cfg: PCSConfig) -> tuple[int, int, int]:
    with psycopg.connect(cfg.dsn()) as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM pcs_chunk")
        (chunks,) = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM pcs_document")
        (docs,) = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM pcs_index_run")
        (runs,) = cur.fetchone()
    return chunks, docs, runs


# --------------------------------------------------------------------------- #
# DB-backed tests
# --------------------------------------------------------------------------- #
def test_reindex_then_idempotent(test_config: PCSConfig) -> None:
    first = reindex(config=test_config, embedder=FakeEmbedder())
    assert first.files_indexed > 0
    assert first.chunks_written > 0
    assert first.run_id is not None
    chunks_1, docs_1, runs_1 = _counts(test_config)
    assert chunks_1 == first.chunks_written
    assert runs_1 == 1

    # Second pass: nothing changed → zero rows, no new run row (exact idempotence).
    second = reindex(config=test_config, embedder=FakeEmbedder())
    assert second.up_to_date
    assert second.files_indexed == 0
    assert second.chunks_written == 0
    assert second.run_id is None
    chunks_2, docs_2, runs_2 = _counts(test_config)
    assert (chunks_2, docs_2, runs_2) == (chunks_1, docs_1, 1)


def test_reindex_records_provenance(test_config: PCSConfig) -> None:
    reindex(config=test_config, embedder=FakeEmbedder())
    cfg = test_config
    with psycopg.connect(cfg.dsn()) as conn, conn.cursor() as cur:
        cur.execute("SELECT embed_model, embed_revision, chunker_version FROM pcs_index_run")
        model, revision, chunker_version = cur.fetchone()
        assert model == cfg.embed_model
        assert revision == cfg.embed_revision
        assert chunker_version
        cur.execute("SELECT DISTINCT git_sha, content_hash FROM pcs_document")
        for git_sha, content_hash in cur.fetchall():
            assert git_sha and content_hash


def test_reindex_split_entry_lands_mixed_status_in_db(test_config: PCSConfig) -> None:
    reindex(config=test_config, embedder=FakeEmbedder())
    with psycopg.connect(test_config.dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT status, superseded_by, chunk_text FROM pcs_chunk WHERE breadcrumb LIKE %s",
            (f"%{PRODUCTION_CUT}%",),
        )
        rows = cur.fetchall()
    assert rows
    superseded = [r for r in rows if r[0] == "superseded"]
    current = [r for r in rows if r[0] == "current"]
    assert superseded and current
    # Trap: the misread is off the current surface; it lives on a superseded chunk.
    assert all("$10,885/yr per contract" not in r[2] for r in current)
    assert any("10,885" in r[2] for r in superseded)
    assert all(r[1] and "2026-05-13" in r[1] for r in superseded)


def test_force_reindexes_all_files(test_config: PCSConfig) -> None:
    reindex(config=test_config, embedder=FakeEmbedder())
    _, docs_before, runs_before = _counts(test_config)
    forced = reindex(config=test_config, embedder=FakeEmbedder(), force=True)
    assert forced.files_indexed == docs_before  # every file re-embedded
    assert forced.run_id is not None
    _, _, runs_after = _counts(test_config)
    assert runs_after == runs_before + 1
