"""Shared fixtures for DB-backed PCS tests (retriever).

Provides an isolated ``pcs_test_ret`` database indexed once with a deterministic
fake embedder — no torch, no touching the operator's real index. Skips cleanly
when the PCS Postgres container is not running.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator

import numpy as np
import psycopg
import pytest
from psycopg import sql

from quant_research.context.config import PCSConfig, get_config
from quant_research.context.indexer import reindex
from quant_research.context.migrate import migrate

RETRIEVER_DB = "pcs_test_ret"


class FakeEmbedder:
    """Deterministic unit-vector embedder keyed by text (dim 768)."""

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


@pytest.fixture(scope="session")
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()


def _admin_dsn(base: PCSConfig) -> str:
    return (
        f"host={base.db_host} port={base.db_port} dbname={base.db_name} "
        f"user={base.db_user} password={base.db_password}"
    )


@pytest.fixture(scope="session")
def indexed_config(fake_embedder: FakeEmbedder) -> Iterator[PCSConfig]:
    """Create + migrate + index an isolated DB with the fake embedder; drop after."""
    base = get_config()
    try:
        admin = psycopg.connect(_admin_dsn(base), connect_timeout=5, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("PCS Postgres not reachable; skipping DB-backed retriever tests")

    drop = sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(RETRIEVER_DB))
    create = sql.SQL("CREATE DATABASE {}").format(sql.Identifier(RETRIEVER_DB))
    try:
        with admin.cursor() as cur:
            cur.execute(drop)
            cur.execute(create)
    finally:
        admin.close()

    cfg = PCSConfig(
        db_host=base.db_host,
        db_port=base.db_port,
        db_name=RETRIEVER_DB,
        db_user=base.db_user,
        db_password=base.db_password,
    )
    migrate(cfg)
    reindex(config=cfg, embedder=fake_embedder)
    yield cfg

    admin = psycopg.connect(_admin_dsn(base), connect_timeout=5, autocommit=True)
    try:
        with admin.cursor() as cur:
            cur.execute(drop)
    finally:
        admin.close()
