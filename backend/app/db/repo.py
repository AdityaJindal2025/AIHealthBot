"""Small data-access functions. Every function commits its own write."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Failure, Message, ScopeEvent, utcnow


def create_conversation(db: Session) -> Conversation:
    conv = Conversation()
    db.add(conv)
    db.commit()
    return conv


def get_conversation(db: Session, conversation_id: uuid.UUID) -> Conversation | None:
    return db.get(Conversation, conversation_id)


def count_user_messages(db: Session, conversation_id: uuid.UUID) -> int:
    stmt = select(func.count()).where(Message.conversation_id == conversation_id, Message.role == "user")
    return db.scalar(stmt) or 0


def add_message(
    db: Session,
    conversation_id: uuid.UUID,
    *,
    role: str,
    content: str,
    claims: list[dict[str, Any]] | None = None,
    status: str = "ok",
    scope_category: str | None = None,
    scope_stage: str | None = None,
    prompt_version: str | None = None,
    model: str | None = None,
    latency_ms: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> Message:
    next_seq = (
        db.scalar(select(func.max(Message.seq)).where(Message.conversation_id == conversation_id)) or 0
    ) + 1
    msg = Message(
        conversation_id=conversation_id,
        seq=next_seq,
        role=role,
        content=content,
        claims=claims,
        status=status,
        scope_category=scope_category,
        scope_stage=scope_stage,
        prompt_version=prompt_version,
        model=model,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    db.add(msg)
    conv = db.get(Conversation, conversation_id)
    if conv is not None:
        conv.updated_at = utcnow()  # EC DB-10
    db.commit()
    return msg


def list_messages(db: Session, conversation_id: uuid.UUID) -> list[Message]:
    stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.seq)
    return list(db.scalars(stmt))


def recent_turns(db: Session, conversation_id: uuid.UUID, n: int = 10) -> list[Message]:
    """The last `n` messages in chronological order."""
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.seq.desc())
        .limit(n)
    )
    return list(reversed(list(db.scalars(stmt))))


def record_failure(
    db: Session,
    *,
    type: str,
    error_detail: str | None,
    raw_output: str | None,
    request_context: dict[str, Any] | None,
    conversation_id: uuid.UUID | None,
) -> Failure:
    row = Failure(
        conversation_id=conversation_id,
        type=type,
        error_detail=error_detail,
        raw_output=raw_output,
        request_context=request_context,
    )
    db.add(row)
    db.commit()
    return row


def record_scope_event(
    db: Session,
    *,
    conversation_id: uuid.UUID | None,
    message_id: uuid.UUID | None,
    stage: str,
    category: str,
    rule_id: str,
    matched_rules: list[str] | None = None,
    raw_output: str | None = None,
) -> ScopeEvent:
    row = ScopeEvent(
        conversation_id=conversation_id,
        message_id=message_id,
        stage=stage,
        category=category,
        rule_id=rule_id,
        matched_rules=matched_rules,
        raw_output=raw_output,
    )
    db.add(row)
    db.commit()
    return row
