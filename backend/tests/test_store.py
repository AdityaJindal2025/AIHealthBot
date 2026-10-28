from pathlib import Path

import pytest

from app.rag.build_index import build_index
from app.rag.chunker import ChunkSettings
from app.rag.embedder import FakeEmbedder
from app.rag.store import MemoryStore, get_store

FIXTURE = Path(__file__).parent / "fixtures" / "corpus"
EMBEDDER = FakeEmbedder()


@pytest.fixture
def indexed(db):
    build_index(db, corpus_dir=FIXTURE, chunk_settings=ChunkSettings(), embedder=EMBEDDER, allow_unverified=False)
    return db


def test_sqlite_uses_memory_store(indexed):
    assert isinstance(get_store(indexed), MemoryStore)


def test_ranks_the_matching_chunk_first(indexed):
    hits = MemoryStore(indexed).search(EMBEDDER.embed_query("how much salt should adults eat a day"), 3)
    assert hits[0].chunk.document_id == "gamma-salt"
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert all(-1.0 <= h.score <= 1.0 for h in hits)


def test_document_filter_returns_only_that_document(indexed):
    hits = MemoryStore(indexed).search(EMBEDDER.embed_query("salt"), 10, document_id="alpha-safety")
    assert hits and {h.chunk.document_id for h in hits} == {"alpha-safety"}


def test_n_limits_results_and_unknown_filter_returns_nothing(indexed):
    store = MemoryStore(indexed)
    assert len(store.search(EMBEDDER.embed_query("food"), 2)) == 2
    assert store.search(EMBEDDER.embed_query("food"), 5, document_id="no-such-doc") == []


def test_empty_index_returns_nothing(db):
    assert MemoryStore(db).search(EMBEDDER.embed_query("food"), 5) == []


def test_reloads_after_rebuild(indexed):
    store = MemoryStore(indexed)
    before = {h.chunk.chunk_id for h in store.search(EMBEDDER.embed_query("food"), 50)}
    build_index(indexed, corpus_dir=FIXTURE, chunk_settings=ChunkSettings(target_tokens=40, min_tokens=10),
                embedder=EMBEDDER, allow_unverified=False)
    after = {h.chunk.chunk_id for h in store.search(EMBEDDER.embed_query("food"), 50)}
    assert before != after
