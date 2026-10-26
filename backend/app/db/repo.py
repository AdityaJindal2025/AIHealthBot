"""Small data-access functions. Every function commits its own write."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CitationEvent,
    Conversation,
    Document,
    Failure,
    IndexedChunk,
    IndexMeta,
    Message,
    Retrieval,
    ScopeEvent,
    utcnow,
)


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
    grounding: dict[str, Any] | None = None,
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
        grounding=grounding,
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


# --- Milestone 2: index (FAP §6, §11.3)


def get_index_meta(db: Session) -> IndexMeta | None:
    return db.scalar(select(IndexMeta))


def list_documents(db: Session) -> list[tuple[Document, int]]:
    """Every registry document with its chunk count, ordered by document_id."""
    counts = (
        select(IndexedChunk.document_id, func.count().label("n"))
        .group_by(IndexedChunk.document_id)
        .subquery()
    )
    stmt = (
        select(Document, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.document_id == Document.document_id)
        .order_by(Document.document_id)
    )
    return [(doc, int(n)) for doc, n in db.execute(stmt).all()]


def get_chunks(db: Session, chunk_ids: list[str]) -> list[IndexedChunk]:
    """Chunks in the order given. Raises KeyError if any ID is not in the index."""
    if not chunk_ids:
        return []
    rows = {c.chunk_id: c for c in db.scalars(select(IndexedChunk).where(IndexedChunk.chunk_id.in_(chunk_ids)))}
    missing = [i for i in chunk_ids if i not in rows]
    if missing:
        raise KeyError(f"chunks not in the index: {missing}")
    return [rows[i] for i in chunk_ids]


# --- Milestone 2: retrieval records (FAP §9, §14)


def record_retrieval(
    db: Session,
    *,
    message_id: uuid.UUID | None,
    failure_id: uuid.UUID | None,
    query: str,
    filter_document_id: str | None,
    k: int,
    results: list[dict[str, Any]],
    withheld: list[dict[str, Any]],
    top_score: float | None,
    corpus_version: str,
) -> Retrieval:
    """Owned by the assistant message, or by the failure when the turn ended in a 502 (A3)."""
    if (message_id is None) == (failure_id is None):
        raise ValueError("a retrieval belongs to exactly one of message_id or failure_id")
    row = Retrieval(message_id=message_id, failure_id=failure_id, query=query, filter_document_id=filter_document_id,
                    k=k, results=results, withheld=withheld or None, top_score=top_score,
                    corpus_version=corpus_version)
    db.add(row)
    db.commit()
    return row


def record_citation_events(
    db: Session,
    *,
    message_id: uuid.UUID | None,
    failure_id: uuid.UUID | None,
    events: list[dict[str, Any]],
) -> None:
    """One row per dropped claim: {claim_text, source_label, chunk_id, reason}."""
    if not events:
        return
    db.add_all(CitationEvent(message_id=message_id, failure_id=failure_id, **e) for e in events)
    db.commit()


def retrievals_for_messages(db: Session, message_ids: list[uuid.UUID]) -> dict[uuid.UUID, Retrieval]:
    if not message_ids:
        return {}
    rows = db.scalars(select(Retrieval).where(Retrieval.message_id.in_(message_ids)))
    return {r.message_id: r for r in rows if r.message_id is not None}
