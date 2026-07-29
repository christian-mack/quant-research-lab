"""Unit tests for PCS configuration (D1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quant_research.context import config as config_module
from quant_research.context.config import (
    EMBED_DIM,
    EMBED_MODEL,
    EMBED_REVISION,
    PCSConfig,
    repo_root,
)


def test_default_dsn_targets_localhost_container() -> None:
    cfg = PCSConfig()
    dsn = cfg.dsn()
    assert "host=127.0.0.1" in dsn
    assert "port=5432" in dsn
    assert "dbname=pcs" in dsn
    assert "user=pcs" in dsn
    assert "password=pcs" in dsn


def test_env_overrides_are_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PCS_DB_HOST", "db.internal")
    monkeypatch.setenv("PCS_DB_PORT", "6543")
    monkeypatch.setenv("PCS_DB_NAME", "other")
    # env_file=".env" could otherwise leak local settings into this assertion.
    cfg = PCSConfig(_env_file=None)
    assert cfg.db_host == "db.internal"
    assert cfg.db_port == 6543
    assert cfg.db_name == "other"
    assert "host=db.internal" in cfg.dsn()
    assert "port=6543" in cfg.dsn()


def test_embedding_identity_is_pinned() -> None:
    cfg = PCSConfig()
    assert cfg.embed_model == EMBED_MODEL == "BAAI/bge-base-en-v1.5"
    # Exact commit SHA (40 hex chars) — deterministic embeddings (D-03).
    assert len(EMBED_REVISION) == 40
    assert all(c in "0123456789abcdef" for c in EMBED_REVISION)
    assert cfg.embed_revision == EMBED_REVISION
    assert cfg.embed_dim == EMBED_DIM == 768


def test_repo_root_points_at_repository() -> None:
    root = repo_root()
    assert isinstance(root, Path)
    assert (root / "pyproject.toml").is_file()
    assert (root / "docs" / "ai-project-instructions.md").is_file()


def test_schema_sql_ships_with_package() -> None:
    schema = Path(config_module.__file__).with_name("schema.sql")
    assert schema.is_file()
    text = schema.read_text(encoding="utf-8")
    assert "CREATE EXTENSION IF NOT EXISTS vector" in text
    assert "vector(768)" in text
