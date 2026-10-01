import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import repo
from app.db.models import Message
from app.db.session import get_db
from app.schemas.api import ConversationOut, ErrorResponse, MessageOut, Meta, ScopeInfo
from app.schemas.model_output import Claim
from app.services.chat_service import ChatError

router = APIRouter()


def _message_out(msg: Message) -> MessageOut:
    if msg.role == "user":
        return MessageOut(id=msg.id, role="user", content=msg.content, created_at=msg.created_at)
    declined = msg.status == "declined"
    return MessageOut(
        id=msg.id,
        role="assistant",
        content=msg.content,
        claims=[Claim.model_validate(c) for c in (msg.claims or [])],
        scope=ScopeInfo(status="declined", category=msg.scope_category, stage=msg.scope_stage)  # type: ignore[arg-type]
        if declined else ScopeInfo(status="in_scope"),
        meta=Meta(prompt_version=msg.prompt_version or "", model=msg.model, latency_ms=msg.latency_ms),
        created_at=msg.created_at,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationOut,
            responses={404: {"model": ErrorResponse}})
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)) -> ConversationOut:
    conv = repo.get_conversation(db, conversation_id)
    if conv is None:
        raise ChatError(404, "conversation_not_found")
    return ConversationOut(id=conv.id, messages=[_message_out(m) for m in repo.list_messages(db, conv.id)])
