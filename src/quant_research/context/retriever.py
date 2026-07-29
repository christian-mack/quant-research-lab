"""Hybrid retrieval: semantic + lexical, fused by RRF (spec §5.2, D5).

Two locked design constraints (operator, D5):

1. **Status filter runs INSIDE both retrieval SQLs, before fusion.** Default
   queries add ``status = 'current'`` to the semantic *and* lexical candidate
   SQL, so a superseded chunk never enters the candidate pool. Fusing first and
   filtering after would let a superseded chunk (e.g. the ~$10,885 misread, which
   sits right next to its 2026-05-13 correction in embedding space) outrank and
   crowd out its own current replacement.

2. **Superseded recall arrives labeled.** ``include_superseded=True`` admits
   ``status IN ('current', 'superseded')`` and nothing else — the "show me the
   stale version of this" correction-pair intent. A returned superseded chunk
   renders a ``[SUPERSEDED by {pointer}]`` prefix (§4.4 point 4) in the ``text``
   an agent actually reads — not merely as a column. Archived recall of
   ``historical``/``deprecated`` content is a deliberately separate, deferred
   capability (YAGNI until a golden query needs it).

Every result carries inline provenance (breadcrumb, file_path, entry_date,
status, git SHA, score) so an agent never needs a second call to answer "where
from, which commit, current or not".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from quant_research.context.config import PCSConfig, get_config
from quant_research.context.embedder import SupportsEmbedding, get_embedder

CANDIDATE_LIMIT = 30  # per-arm candidate depth (§5.2)
RRF_K = 60  # Reciprocal Rank Fusion constant (§5.2)
DEFAULT_TOP_K = 8

# include_superseded admits only current + superseded, so superseded is the only
# non-current status the retriever can return; it is always labeled in the payload.
_NON_CURRENT_LABEL = {"superseded": "SUPERSEDED"}


@dataclass(frozen=True)
class SearchResult:
    """One retrieved chunk with inline provenance (§5.2)."""

    chunk_id: int
    breadcrumb: str
    file_path: str
    entry_date: date | None
    status: str
    superseded_by: str | None
    git_sha: str
    score: float
    chunk_text: str
    text: str  # agent-facing payload; carries the [SUPERSEDED by ...] prefix when stale


def _status_clause(include_superseded: bool) -> str:
    """Status filter applied INSIDE each candidate SQL (locked constraint 1).

    Default: current only. ``include_superseded`` widens to current + superseded
    (the correction-pair intent) — never historical/deprecated.
    """
    if include_superseded:
        return " AND status IN ('current', 'superseded')"
    return " AND status = 'current'"


def _normalize_lexical_query(query: str) -> str:
    """Prepare a query for ``websearch_to_tsquery`` (D-05 identifier hygiene).

    Compound program identifiers use punctuation that tsquery treats as operators
    (``ORB+Opt3``, ``R(q)``). Hyphenated terms (``per-contract``) and low-signal
    question words can over-constrain ``websearch_to_tsquery`` to zero hits.
    """
    q = query.replace("+", " ")
    q = q.replace("(", " ").replace(")", " ")
    q = q.replace("-", " ")
    stop = {
        "what", "is", "the", "a", "an", "are", "was", "were", "when", "why", "how",
        "does", "do", "did", "which", "who", "where", "has", "have", "had", "and", "or",
        # query scaffolding absent from the corpus — keeps tsquery from zeroing out
        "graded", "figure", "figures", "current", "happened", "trusted", "abandoned",
    }
    tokens = [t for t in q.split() if t.lower().strip("?.,'\"") not in stop]
    return " ".join(tokens) if tokens else query


def semantic_candidates(
    conn: psycopg.Connection,
    query_embedding: list[float],
    *,
    limit: int = CANDIDATE_LIMIT,
    include_superseded: bool = False,
) -> list[int]:
    """Return chunk ids by ascending cosine distance, status-filtered in SQL."""
    sql = (
        "SELECT id FROM pcs_chunk WHERE embedding IS NOT NULL"
        + _status_clause(include_superseded)
        + " ORDER BY embedding <=> %s LIMIT %s"
    )
    vec = np.asarray(query_embedding, dtype=np.float32)
    with conn.cursor() as cur:
        cur.execute(sql, (vec, limit))
        return [row[0] for row in cur.fetchall()]


def lexical_candidates(
    conn: psycopg.Connection,
    query: str,
    *,
    limit: int = CANDIDATE_LIMIT,
    include_superseded: bool = False,
) -> list[int]:
    """Return chunk ids by descending ts_rank_cd, status-filtered in SQL."""
    sql = (
        "SELECT id FROM pcs_chunk "
        "WHERE tsv @@ websearch_to_tsquery('english', %s)"
        + _status_clause(include_superseded)
        + " ORDER BY ts_rank_cd(tsv, websearch_to_tsquery('english', %s)) DESC LIMIT %s"
    )
    with conn.cursor() as cur:
        cur.execute(sql, (query, query, limit))
        return [row[0] for row in cur.fetchall()]


def rrf_fuse(*ranked_lists: list[int], k: int = RRF_K) -> dict[int, float]:
    """Reciprocal Rank Fusion: score(d) = Σ 1 / (k + rank_i(d)), rank 1-based."""
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, chunk_id in enumerate(ranked, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return scores


def _render_text(breadcrumb: str, chunk_text: str, status: str, superseded_by: str | None) -> str:
    """Prefix non-current chunks with a stale-content label (§4.4 point 4)."""
    label = _NON_CURRENT_LABEL.get(status)
    if label is None:
        return f"{breadcrumb}\n\n{chunk_text}"
    prefix = f"[{label} by {superseded_by}]" if superseded_by else f"[{label}]"
    return f"{prefix} {breadcrumb}\n\n{chunk_text}"


def _fetch_rows(conn: psycopg.Connection, chunk_ids: list[int]) -> dict[int, tuple]:
    if not chunk_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT c.id, c.breadcrumb, d.file_path, c.entry_date, c.status, "
            "c.superseded_by, d.git_sha, c.chunk_text "
            "FROM pcs_chunk c JOIN pcs_document d ON d.id = c.document_id "
            "WHERE c.id = ANY(%s)",
            (chunk_ids,),
        )
        return {row[0]: row for row in cur.fetchall()}


def search(
    query: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    include_superseded: bool = False,
    config: PCSConfig | None = None,
    embedder: SupportsEmbedding | None = None,
) -> list[SearchResult]:
    """Hybrid search: semantic + lexical candidates, RRF-fused, provenance-inline.

    The status filter is applied inside both candidate SQLs (locked constraint 1),
    so superseded chunks are absent from the candidate pool by default — not merely
    trimmed from the final ``top_k``.
    """
    config = config or get_config()
    embedder = embedder or get_embedder()
    query_embedding = embedder.embed_query(query)

    with psycopg.connect(config.dsn()) as conn:
        register_vector(conn)
        semantic = semantic_candidates(
            conn, query_embedding, include_superseded=include_superseded
        )
        lexical = lexical_candidates(
            conn, _normalize_lexical_query(query), include_superseded=include_superseded
        )
        fused = rrf_fuse(semantic, lexical)
        if not fused:
            return []
        ranked_ids = sorted(fused, key=lambda cid: (-fused[cid], cid))[:top_k]
        rows = _fetch_rows(conn, ranked_ids)

    results: list[SearchResult] = []
    for chunk_id in ranked_ids:
        row = rows.get(chunk_id)
        if row is None:
            continue
        _id, breadcrumb, file_path, entry_date, status, superseded_by, git_sha, chunk_text = row
        results.append(
            SearchResult(
                chunk_id=_id,
                breadcrumb=breadcrumb,
                file_path=file_path,
                entry_date=entry_date,
                status=status,
                superseded_by=superseded_by,
                git_sha=git_sha,
                score=fused[chunk_id],
                chunk_text=chunk_text,
                text=_render_text(breadcrumb, chunk_text, status, superseded_by),
            )
        )
    return results
