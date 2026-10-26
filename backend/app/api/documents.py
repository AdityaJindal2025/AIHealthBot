from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import repo
from app.db.session import get_db
from app.schemas.api import DocumentOut, DocumentsOut

router = APIRouter()


@router.get("/documents", response_model=DocumentsOut)
def list_documents(db: Session = Depends(get_db)) -> DocumentsOut:
    """The registry, for the "Search in" filter and the footer (FAP §11.3)."""
    return DocumentsOut(documents=[
        DocumentOut(document_id=d.document_id, title=d.title, publisher=d.publisher,
                    publisher_short=d.publisher_short, year=d.year, url=d.url, chunk_count=n)
        for d, n in repo.list_documents(db)
    ])
