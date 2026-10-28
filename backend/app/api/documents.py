from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import repo
from app.db.session import get_db
from app.rag.themes import get_themes
from app.schemas.api import DocumentOut, DocumentsOut, ThemeOut, ThemesOut

router = APIRouter()


@router.get("/documents", response_model=DocumentsOut)
def list_documents(db: Session = Depends(get_db)) -> DocumentsOut:
    """The registry, for the "Search in" filter and the footer (FAP §11.3)."""
    return DocumentsOut(documents=[
        DocumentOut(document_id=d.document_id, title=d.title, publisher=d.publisher,
                    publisher_short=d.publisher_short, year=d.year, url=d.url, chunk_count=n)
        for d, n in repo.list_documents(db)
    ])


@router.get("/themes", response_model=ThemesOut)
def list_themes(db: Session = Depends(get_db)) -> ThemesOut:
    """The themes for the "Select theme" filter: named groups of registry documents. Empty in M1 mode
    (`RAG_ENABLED=false`), where themed requests are refused, so the frontend hides the filter."""
    if not get_settings().RAG_ENABLED:
        return ThemesOut(themes=[])
    known = {d.document_id for d, _ in repo.list_documents(db)}
    return ThemesOut(themes=[ThemeOut(theme_id=t.theme_id, name=t.name, description=t.description,
                                      document_ids=list(t.document_ids)) for t in get_themes(known)])
