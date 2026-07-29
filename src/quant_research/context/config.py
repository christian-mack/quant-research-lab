"""PCS configuration.

Single source of truth for connection parameters and the pinned embedding model
identity. Values are overridable via ``PCS_``-prefixed environment variables (or
a ``.env`` file), but the defaults are deliberately usable as-is against the
localhost Docker container defined in ``docker/pcs-compose.yml``.

The embedding model id and revision are pinned here (decision D-03). Changing
either invalidates existing embeddings and must be treated as a re-index event.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Pinned embedding model (D-03). The revision is an exact commit SHA on the
# Hugging Face repo so embeddings are byte-reproducible across machines/time.
EMBED_MODEL = "BAAI/bge-base-en-v1.5"
EMBED_REVISION = "a5beb1e3e68b9ab74eb54cfd186867f64f240e1a"
EMBED_DIM = 768

# Bumped whenever chunking logic changes in a way that alters chunk boundaries
# or breadcrumb text. Recorded per index run for reproducibility (D-09).
CHUNKER_VERSION = "1"

# Current schema version applied by migrate.py.
SCHEMA_VERSION = 1


class PCSConfig(BaseSettings):
    """Runtime configuration for the Program Context System.

    Attributes are populated from ``PCS_``-prefixed environment variables when
    present, otherwise from the defaults below (which target the localhost
    Docker container).
    """

    model_config = SettingsConfigDict(
        env_prefix="PCS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "pcs"
    db_user: str = "pcs"
    db_password: str = "pcs"

    embed_model: str = Field(default=EMBED_MODEL)
    embed_revision: str = Field(default=EMBED_REVISION)
    embed_dim: int = Field(default=EMBED_DIM)
    chunker_version: str = Field(default=CHUNKER_VERSION)

    def dsn(self) -> str:
        """Return a libpq connection string for psycopg."""
        return (
            f"host={self.db_host} port={self.db_port} dbname={self.db_name} "
            f"user={self.db_user} password={self.db_password}"
        )


@lru_cache(maxsize=1)
def get_config() -> PCSConfig:
    """Return a process-wide cached :class:`PCSConfig` instance."""
    return PCSConfig()


def repo_root() -> Path:
    """Return the repository root (four levels up from this file).

    ``src/quant_research/context/config.py`` -> repo root.
    """
    return Path(__file__).resolve().parents[3]


def git_sha_and_dirty(root: Path | None = None) -> tuple[str, bool]:
    """Return ``(HEAD sha, working-tree-dirty)``; degrade to ('unknown', True).

    Lives here (a dependency-free module) so both the indexer and the pinned-doc
    loader can record provenance without the pinned path importing anything on the
    vector/embedding side.
    """
    root = root or repo_root()
    try:
        sha = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
        status = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain"], text=True
        )
        return sha, bool(status.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown", True
