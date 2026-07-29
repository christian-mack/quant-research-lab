"""Deterministic passage/query embedding for the PCS (spec D-03, D4).

Wraps ``BAAI/bge-base-en-v1.5`` pinned to the exact revision in
:mod:`quant_research.context.config`. Embeddings are L2-normalised so cosine
distance (``<=>`` in pgvector) equals ``1 - dot``; the retriever (D5) relies on
that. Passages are embedded verbatim; queries get the bge retrieval instruction
prefix (asymmetric search — the model was trained this way).

``torch``/``sentence_transformers`` are imported lazily inside the constructor so
that merely importing this module (e.g. for the :class:`SupportsEmbedding`
protocol, or in chunker/manifest tests) does not drag in the ~200 MB CPU torch
stack. The indexer and retriever construct an :class:`Embedder` explicitly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol, runtime_checkable

from quant_research.context.config import PCSConfig, get_config

# bge-v1.5 asymmetric retrieval: prefix queries, not passages.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


@runtime_checkable
class SupportsEmbedding(Protocol):
    """Minimal embedder contract the indexer/retriever depend on.

    Tests inject a lightweight fake satisfying this protocol so the DB and
    chunking paths can be exercised without loading torch.
    """

    embed_dim: int

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class Embedder:
    """Real bge-base-en-v1.5 embedder, pinned and CPU-bound for determinism."""

    def __init__(self, config: PCSConfig | None = None) -> None:
        from sentence_transformers import SentenceTransformer  # lazy (torch)

        cfg = config or get_config()
        self.embed_dim: int = cfg.embed_dim
        self._model = SentenceTransformer(
            cfg.embed_model,
            revision=cfg.embed_revision,
            device="cpu",
        )
        self._model.eval()

    def _encode(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        if not texts:
            return []
        vecs = self._model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=32,
        )
        return [v.astype(np.float32).tolist() for v in vecs]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        """Embed indexable passages (breadcrumb-prefixed chunk text), no prefix."""
        return self._encode(list(texts))

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query with the bge retrieval instruction prefix."""
        return self._encode([BGE_QUERY_INSTRUCTION + text])[0]


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """Return a process-wide cached :class:`Embedder` (loads the model once)."""
    return Embedder()
