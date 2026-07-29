-- PCS schema (authoritative DDL). Applied by migrate.py.
-- Mirrors the implementation spec section 5.1. IF NOT EXISTS guards are added so
-- the script is safe to re-apply; migrate.py additionally version-gates it.
--
-- Deliberately NO vector (ANN) index: the corpus is <10k rows and exact scan is
-- both faster and fully deterministic at this size (decision D-04).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS pcs_index_run (
    id              BIGSERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    git_sha         TEXT NOT NULL,
    git_dirty       BOOLEAN NOT NULL,
    embed_model     TEXT NOT NULL,
    embed_revision  TEXT NOT NULL,
    chunker_version TEXT NOT NULL,
    files_indexed   INT,
    chunks_written  INT
);

CREATE TABLE IF NOT EXISTS pcs_document (
    id              BIGSERIAL PRIMARY KEY,
    file_path       TEXT NOT NULL UNIQUE,
    tier            SMALLINT NOT NULL,           -- 1 = pinned, 2 = retrieved
    content_hash    TEXT NOT NULL,               -- sha256 of file bytes
    git_sha         TEXT NOT NULL,
    indexed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_id          BIGINT NOT NULL REFERENCES pcs_index_run(id)
);

CREATE TABLE IF NOT EXISTS pcs_chunk (
    id              BIGSERIAL PRIMARY KEY,
    document_id     BIGINT NOT NULL REFERENCES pcs_document(id) ON DELETE CASCADE,
    chunk_index     INT NOT NULL,
    breadcrumb      TEXT NOT NULL,               -- "docs/lessons-log.md > 2026-05-13 — Correction: ..."
    entry_date      DATE,                        -- for dated log entries; NULL otherwise
    chunk_text      TEXT NOT NULL,               -- exact source text, unmodified
    embed_text      TEXT NOT NULL,               -- breadcrumb + chunk_text; what was embedded
    token_count     INT NOT NULL,
    status          TEXT NOT NULL
                    CHECK (status IN ('current','superseded','deprecated','historical')),
    superseded_by   TEXT,
    embedding       vector(768) NOT NULL,
    tsv             TSVECTOR
                    GENERATED ALWAYS AS (to_tsvector('english', embed_text)) STORED,
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS pcs_chunk_tsv_idx    ON pcs_chunk USING GIN (tsv);
CREATE INDEX IF NOT EXISTS pcs_chunk_status_idx ON pcs_chunk (status);
-- Deliberately NO vector index. See D-04.

CREATE TABLE IF NOT EXISTS pcs_schema_version (
    version     INT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
