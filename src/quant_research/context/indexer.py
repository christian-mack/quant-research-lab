"""Corpus indexer (D4): walk → hash → chunk → embed → upsert.

Rebuilds the Tier-2 slice of ``pcs_document`` / ``pcs_chunk`` from git-tracked
docs. Incremental by **content hash** (D-10): a file whose sha256 is unchanged is
skipped and writes zero rows. A run that changes nothing writes *nothing at all*
— not even an ``pcs_index_run`` row — so re-indexing is exactly idempotent
(spec D4 exit criterion).

Every persisted row carries provenance (D-09): the embedding model id + revision,
chunker version, git SHA, and content hash. The manifest gate (§4.4 rule 5) runs
first: indexing aborts loudly if any Tier-2 file or dated entry is unclassified,
so unclassified content can never enter the index as ``current``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from quant_research.context import manifest as m
from quant_research.context.chunker import (
    Chunk,
    SplitSpec,
    chunk_entry,
    chunk_whole_file,
    iter_log_entries,
)
from quant_research.context.config import (
    CHUNKER_VERSION,
    PCSConfig,
    get_config,
    git_sha_and_dirty,
    repo_root,
)
from quant_research.context.embedder import SupportsEmbedding, get_embedder

TIER_PINNED = 1
TIER_RETRIEVED = 2


@dataclass(frozen=True)
class ReindexResult:
    """Summary of a reindex pass."""

    files_indexed: int
    files_skipped: int
    chunks_written: int
    run_id: int | None

    @property
    def up_to_date(self) -> bool:
        return self.files_indexed == 0


@dataclass(frozen=True)
class IndexStatus:
    """Snapshot of the current index state (latest run + working-tree drift)."""

    latest_run: dict | None
    total_chunks: int
    stale_files: list[str]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_document_chunks(rel_path: str, text: str, manifest: dict) -> list[Chunk]:
    """Chunk one Tier-2 file, applying manifest status (and any split) per unit."""
    if rel_path in m.TIER2_ENTRY_LOGS:
        chunks: list[Chunk] = []
        for heading, body in iter_log_entries(text):
            status, superseded_by = m.classification_for_entry(manifest, rel_path, heading)
            sr = m.split_for_entry(manifest, rel_path, heading)
            split = SplitSpec(sr.anchors, sr.superseded_by) if sr and sr.superseded_by else None
            chunks.extend(
                chunk_entry(
                    rel_path,
                    heading,
                    body,
                    status,
                    superseded_by=superseded_by,
                    split=split,
                    start_index=len(chunks),
                )
            )
        return chunks
    status, superseded_by = m.classification_for_document(manifest, rel_path)
    return chunk_whole_file(rel_path, text, status, superseded_by=superseded_by)


def _tier2_files(root: Path) -> list[str]:
    return list(m.resolve_whole_file_docs(root)) + list(m.TIER2_ENTRY_LOGS)


def _insert_chunks(
    conn: psycopg.Connection, document_id: int, chunks: list[Chunk], embedder: SupportsEmbedding
) -> int:
    if not chunks:
        return 0
    embeddings = embedder.embed_passages([c.embed_text for c in chunks])
    with conn.cursor() as cur:
        for chunk, emb in zip(chunks, embeddings, strict=True):
            cur.execute(
                "INSERT INTO pcs_chunk (document_id, chunk_index, breadcrumb, entry_date, "
                "chunk_text, embed_text, token_count, status, superseded_by, embedding) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    document_id,
                    chunk.chunk_index,
                    chunk.breadcrumb,
                    chunk.entry_date,
                    chunk.chunk_text,
                    chunk.embed_text,
                    chunk.token_count,
                    chunk.status,
                    chunk.superseded_by,
                    np.asarray(emb, dtype=np.float32),
                ),
            )
    return len(chunks)


def reindex(
    *,
    config: PCSConfig | None = None,
    embedder: SupportsEmbedding | None = None,
    manifest: dict | None = None,
    force: bool = False,
) -> ReindexResult:
    """Reindex the Tier-2 corpus; content-hash incremental unless ``force``.

    Args:
        config: DB/model config; defaults to :func:`get_config`.
        embedder: Injectable embedder (tests use a fake). The real model is only
            constructed when there is actually work to do.
        manifest: Pre-loaded manifest dict; defaults to loading + validating.
        force: Re-embed every file regardless of content hash (``pcs reindex --all``).
    """
    cfg = config or get_config()
    root = repo_root()

    # Gate: never index an unclassified corpus (§4.4 rule 5). Fails loudly.
    m.assert_manifest_valid()
    manifest = manifest if manifest is not None else m.load_manifest(root / m.MANIFEST_PATH_REL)

    git_sha, git_dirty = git_sha_and_dirty(root)
    files = _tier2_files(root)

    with psycopg.connect(cfg.dsn()) as conn:
        register_vector(conn)

        changed: list[tuple[str, str, str]] = []  # (rel_path, text, content_hash)
        for rel in files:
            data = (root / rel).read_bytes()
            content_hash = _sha256(data)
            if not force:
                row = conn.execute(
                    "SELECT content_hash FROM pcs_document WHERE file_path = %s", (rel,)
                ).fetchone()
                if row is not None and row[0] == content_hash:
                    continue
            changed.append((rel, data.decode("utf-8"), content_hash))

        if not changed:
            return ReindexResult(0, len(files), 0, None)  # exactly zero rows written

        active_embedder = embedder or get_embedder()
        chunks_written = 0
        with conn.transaction():
            run_id: int = conn.execute(
                "INSERT INTO pcs_index_run "
                "(git_sha, git_dirty, embed_model, embed_revision, chunker_version) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (git_sha, git_dirty, cfg.embed_model, cfg.embed_revision, CHUNKER_VERSION),
            ).fetchone()[0]

            for rel, text, content_hash in changed:
                conn.execute("DELETE FROM pcs_document WHERE file_path = %s", (rel,))
                document_id: int = conn.execute(
                    "INSERT INTO pcs_document (file_path, tier, content_hash, git_sha, run_id) "
                    "VALUES (%s,%s,%s,%s,%s) RETURNING id",
                    (rel, TIER_RETRIEVED, content_hash, git_sha, run_id),
                ).fetchone()[0]
                chunks = build_document_chunks(rel, text, manifest)
                chunks_written += _insert_chunks(conn, document_id, chunks, active_embedder)

            conn.execute(
                "UPDATE pcs_index_run SET completed_at = NOW(), files_indexed = %s, "
                "chunks_written = %s WHERE id = %s",
                (len(changed), chunks_written, run_id),
            )

        return ReindexResult(len(changed), len(files) - len(changed), chunks_written, run_id)


def index_status(config: PCSConfig | None = None) -> IndexStatus:
    """Return the latest index run, chunk count, and files that drifted since.

    Raises ``psycopg.OperationalError`` if the database is unreachable; callers
    (CLI, MCP) decide how to surface that.
    """
    cfg = config or get_config()
    root = repo_root()
    with psycopg.connect(cfg.dsn(), connect_timeout=5) as conn:
        run = conn.execute(
            "SELECT id, completed_at, git_sha, git_dirty, files_indexed, chunks_written "
            "FROM pcs_index_run ORDER BY id DESC LIMIT 1"
        ).fetchone()
        (total_chunks,) = conn.execute("SELECT COUNT(*) FROM pcs_chunk").fetchone()
        stored = dict(conn.execute("SELECT file_path, content_hash FROM pcs_document").fetchall())

    stale = [
        rel for rel in _tier2_files(root) if stored.get(rel) != _sha256((root / rel).read_bytes())
    ]
    latest = None
    if run is not None:
        latest = {
            "id": run[0],
            "completed_at": run[1],
            "git_sha": run[2],
            "git_dirty": run[3],
            "files_indexed": run[4],
            "chunks_written": run[5],
        }
    return IndexStatus(latest_run=latest, total_chunks=total_chunks, stale_files=stale)
