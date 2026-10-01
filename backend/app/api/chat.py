from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.rate_limit import chat_rate_limit, limiter
from app.schemas.api import ChatRequest, ChatResponse, ErrorResponse
from app.services.chat_service import handle_chat

router = APIRouter()


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 429: {"model": ErrorResponse},
               502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
@limiter.limit(chat_rate_limit)
def chat(request: Request, body: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    return handle_chat(db, body)
