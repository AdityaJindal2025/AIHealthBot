import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.chat import M2_FIELDS
from app.config import get_settings
from app.db import repo
from app.db.models import Message, Retrieval
from app.db.session import get_db
from app.schemas.api import ConversationOut, ErrorResponse, Grounding, MessageOut, Meta, RetrievedSource, ScopeInfo
from app.schemas.model_output import Claim
from app.services.chat_service import ChatError

router = APIRouter()


def _sources(retrieval: Retrieval | None, declined: bool) -> list[RetrievedSource]:
    """From the stored snapshot, so history still shows what was retrieved after a rebuild."""
    if retrieval is None or declined:
        return []
    return [RetrievedSource(label=r["label"], chunk_id=r["chunk_id"], document_id=r["document_id"],
                            document_name=r["document_name"], publisher=r["publisher"],
                            publisher_short=r["publisher_short"], year=r["year"], url=r["url"],
                            section=r["section"], page=r["page_start"], text=r["text"], score=r["score"],
                            cited=r["cited"])
            for r in retrieval.results]


def _message_out(msg: Message, retrieval: Retrieval | None = None) -> MessageOut:
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
        meta=Meta(prompt_version=msg.prompt_version or "", model=msg.model, latency_ms=msg.latency_ms,
                  corpus_version=retrieval.corpus_version if retrieval else None),
        grounding=Grounding.model_validate(msg.grounding) if msg.grounding else None,
        sources=_sources(retrieval, declined),
        created_at=msg.created_at,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationOut,
            responses={404: {"model": ErrorResponse}})
def get_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db)) -> ConversationOut | JSONResponse:
    conv = repo.get_conversation(db, conversation_id)
    if conv is None:
        raise ChatError(404, "conversation_not_found")
    messages = repo.list_messages(db, conv.id)
    retrievals = repo.retrievals_for_messages(db, [m.id for m in messages if m.role == "assistant"])
    out = ConversationOut(id=conv.id, messages=[_message_out(m, retrievals.get(m.id)) for m in messages])
    if get_settings().RAG_ENABLED:
        return out
    return JSONResponse(content=out.model_dump(mode="json", exclude={"messages": {"__all__": M2_FIELDS}}))
