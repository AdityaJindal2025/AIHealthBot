"""PgVectorStore against a real Postgres with pgvector, compared with MemoryStore (FAP §6.2).

Runs only when PG_TEST_DATABASE_URL is set (the `postgres` CI job starts a pgvector
service container). The database must already be migrated (`alembic upgrade head`).
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db.models import Base
from app.db.session import engine as sqlite_engine
from app.db.session import make_engine
from app.rag.build_index import build_index
from app.rag.chunker import ChunkSettings
from app.rag.embedder import FakeEmbedder
from app.rag.store import MemoryStore, PgVectorStore

PG_URL = os.environ.get("PG_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="PG_TEST_DATABASE_URL not set")

FIXTURE = Path(__file__).parent / "fixtures" / "corpus"
EMBEDDER = FakeEmbedder()
QUERIES = ["how much salt a day", "fridge temperature", "freeze food", "cook poultry", "free sugars energy",
           "olive oil fats", "leftovers within 2 days"]


@pytest.fixture
def pg_session():
    pg = make_engine(PG_URL)
    with pg.begin() as conn:
        for table in ("citation_events", "retrievals", "chunks", "index_meta", "documents"):
            conn.execute(text(f"DELETE FROM {table}"))
    session = sessionmaker(bind=pg, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()
    pg.dispose()


def _build(session):
    build_index(session, corpus_dir=FIXTURE, chunk_settings=ChunkSettings(), embedder=EMBEDDER,
                allow_unverified=False)


def test_pgvector_matches_memory_store(pg_session, db):
    Base.metadata.create_all(sqlite_engine)
    _build(pg_session)
    _build(db)
    for query in QUERIES:
        q = EMBEDDER.embed_query(query)
        pg_hits = PgVectorStore(pg_session).search(q, 6)
        mem_hits = MemoryStore(db).search(q, 6)
        assert [h.chunk.chunk_id for h in pg_hits] == [h.chunk.chunk_id for h in mem_hits], query
        for a, b in zip(pg_hits, mem_hits, strict=True):
            assert a.score == pytest.approx(b.score, abs=1e-5)


def test_pgvector_document_filter(pg_session):
    _build(pg_session)
    hits = PgVectorStore(pg_session).search(EMBEDDER.embed_query("salt"), 10, document_id="alpha-safety")
    assert hits and {h.chunk.document_id for h in hits} == {"alpha-safety"}
