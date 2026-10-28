"""Exact cosine search over the chunk index (FAP §6.2).

`PgVectorStore` uses pgvector's `<=>` (cosine distance) on Postgres. `MemoryStore` runs the
same exact search in NumPy for SQLite (local development and tests). Neither uses an ANN
index: ~200 chunks scan in milliseconds, results are deterministic, and a document filter
never loses results the way a filtered HNSW search can.

Both rank by score, then by `chunk_id`, so they return the same order for the same vectors.
"""

from collections.abc import Collection
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from sqlalchemy import Float, select
from sqlalchemy.orm import Session, defer

from app.db import repo
from app.db.models import IndexedChunk, IndexMeta


@dataclass(frozen=True)
class Hit:
    chunk: IndexedChunk
    score: float  # cosine similarity in [-1, 1]


class VectorStore(Protocol):
    def search(self, query_vec: np.ndarray, n: int, *, document_id: str | None = None,
               document_ids: Collection[str] | None = None) -> list[Hit]: ...


class PgVectorStore:
    def __init__(self, db: Session) -> None:
        self.db = db

    def search(self, query_vec: np.ndarray, n: int, *, document_id: str | None = None,
               document_ids: Collection[str] | None = None) -> list[Hit]:
        distance = IndexedChunk.embedding.op("<=>", return_type=Float)(np.asarray(query_vec, dtype=np.float32))
        stmt = (
            select(IndexedChunk, distance.label("distance"))
            .options(defer(IndexedChunk.embedding))
            .order_by(distance, IndexedChunk.chunk_id)
            .limit(n)
        )
        if document_id is not None:
            stmt = stmt.where(IndexedChunk.document_id == document_id)
        if document_ids is not None:
            stmt = stmt.where(IndexedChunk.document_id.in_(list(document_ids)))
        return [Hit(chunk, 1.0 - float(dist)) for chunk, dist in self.db.execute(stmt).all()]


@dataclass(frozen=True)
class _Matrix:
    corpus_version: str
    chunk_ids: list[str]
    document_ids: np.ndarray
    vectors: np.ndarray  # (n, dims), rows normalised


# One matrix per database URL, reloaded when `index_meta.corpus_version` changes.
_CACHE: dict[str, _Matrix] = {}


def invalidate_memory_cache() -> None:
    _CACHE.clear()


class MemoryStore:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _matrix(self) -> _Matrix | None:
        version = self.db.scalar(select(IndexMeta.corpus_version))
        if version is None:
            return None
        key = str(self.db.get_bind().url)
        cached = _CACHE.get(key)
        if cached is not None and cached.corpus_version == version:
            return cached
        rows = self.db.execute(
            select(IndexedChunk.chunk_id, IndexedChunk.document_id, IndexedChunk.embedding)
            .order_by(IndexedChunk.chunk_id)
        ).all()
        vectors = np.stack([r.embedding for r in rows]) if rows else np.zeros((0, 384), np.float32)
        matrix = _Matrix(version, [r.chunk_id for r in rows], np.array([r.document_id for r in rows]), vectors)
        _CACHE[key] = matrix
        return matrix

    def search(self, query_vec: np.ndarray, n: int, *, document_id: str | None = None,
               document_ids: Collection[str] | None = None) -> list[Hit]:
        matrix = self._matrix()
        if matrix is None or not matrix.chunk_ids:
            return []
        scores = matrix.vectors @ np.asarray(query_vec, dtype=np.float32)
        candidates = np.arange(len(matrix.chunk_ids))
        if document_id is not None:
            candidates = candidates[matrix.document_ids == document_id]
        if document_ids is not None:
            candidates = candidates[np.isin(matrix.document_ids[candidates], list(document_ids))]
        ranked = sorted(candidates, key=lambda i: (-float(scores[i]), matrix.chunk_ids[i]))[:n]
        chunks = repo.get_chunks(self.db, [matrix.chunk_ids[i] for i in ranked])
        return [Hit(chunk, float(scores[i])) for chunk, i in zip(chunks, ranked, strict=True)]


def get_store(db: Session) -> VectorStore:
    if db.get_bind().dialect.name == "postgresql":
        return PgVectorStore(db)
    return MemoryStore(db)
