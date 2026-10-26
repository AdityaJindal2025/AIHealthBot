from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.rate_limit import chat_rate_limit, limiter
from app.schemas.api import ChatRequest, ChatResponse, ErrorResponse
from app.services.chat_service import handle_chat

router = APIRouter()

# Fields Milestone 2 added to the envelope. With RAG_ENABLED=false they are left out, so the
# response is exactly the M1 envelope (FAP §11.4: "restores M1 behaviour exactly").
M2_FIELDS: dict[str, Any] = {"grounding": True, "sources": True, "meta": {"claims_dropped", "corpus_version"}}


def envelope(response: ChatResponse) -> ChatResponse | JSONResponse:
    if get_settings().RAG_ENABLED:
        return response
    return JSONResponse(content=response.model_dump(mode="json", exclude=M2_FIELDS))


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 429: {"model": ErrorResponse},
               502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@limiter.limit(chat_rate_limit)
def chat(request: Request, body: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse | JSONResponse:
    return envelope(handle_chat(db, body))
