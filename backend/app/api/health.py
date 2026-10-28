from functools import lru_cache

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import repo
from app.db.session import get_db
from app.rag.build_index import expected_corpus_version
from app.rag.chunker import ChunkSettings
from app.rag.embedder import EMBEDDING_DIMS

router = APIRouter()


@lru_cache
def _expected_version(corpus_dir: str, chunk_settings: ChunkSettings, model_id: str) -> str:
    return expected_corpus_version(corpus_dir, chunk_settings, model_id, EMBEDDING_DIMS)


def index_status(db: Session) -> dict:
    """`ready` only when the stored index matches the current corpus, chunker settings and model."""
    settings = get_settings()
    meta = repo.get_index_meta(db)
    if meta is None:
        return {"status": "missing", "chunks": 0, "corpus_version": None}
    try:
        expected = _expected_version(settings.CORPUS_DIR, ChunkSettings.from_settings(settings),
                                     settings.EMBEDDING_MODEL)
    except OSError:
        expected = None
    status = "ready" if meta.corpus_version == expected else "stale"
    return {"status": status, "chunks": meta.chunk_count, "corpus_version": meta.corpus_version}


@router.get("/health")
def health(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "db": "error"})
    if not get_settings().RAG_ENABLED:
        return JSONResponse(content={"status": "ok", "db": "ok"})
    # Railway's health check keeps failing until the index is built, so a broken build never
    # takes traffic (FAP §15).
    index = index_status(db)
    ok = index["status"] == "ready"
    return JSONResponse(status_code=200 if ok else 503,
                        content={"status": "ok" if ok else "degraded", "db": "ok", "index": index})
