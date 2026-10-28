"""SQLAlchemy tables (AP §7)."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.db.types import EmbeddingType


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC timestamps on both engines. SQLite drops tzinfo, so it is re-attached (EC DB-04)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    pass


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.seq", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), nullable=False)
    # Position within the conversation. Breaks created_at ties so history never
    # comes back assistant-before-user (EC DB-03).
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    claims: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")  # ok | declined
    scope_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope_stage: Mapped[str | None] = mapped_column(String(16), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Milestone 2: grounding status, filter and searched documents (FAP §11.2). Null on declines and in M1.
    grounding: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Failure(Base):
    __tablename__ = "failures"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"), nullable=True)
    # schema_invalid | model_refusal | truncated_output | api_error, and in M2:
    # no_valid_claims | missing_citation | retrieval_error | embedding_error | rate_limited (provider 429)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ScopeEvent(Base):
    __tablename__ = "scope_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    stage: Mapped[str] = mapped_column(String(16), nullable=False)  # input | output | model
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # Primary rule ID. Every matched rule is kept in matched_rules (EC SCOPE-27).
    rule_id: Mapped[str] = mapped_column(String(32), nullable=False)
    matched_rules: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    raw_output: Mapped[str | None] = mapped_column(Text, nullable=True)  # output stage only
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


# --- Milestone 2: retrieval (FAP §14). Additive only, so the M1 image still runs on this schema.


class Document(Base):
    """The document registry, loaded from `corpus/documents.json` at index build time."""

    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str] = mapped_column(Text, nullable=False)
    publisher_short: Mapped[str] = mapped_column(String(64), nullable=False)
    # Null only while unverified, which the production build refuses.
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    publisher_aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    verified_by: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    verified_on: Mapped[str] = mapped_column(String(32), nullable=False, default="")


class IndexedChunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_document", "document_id"),)

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.document_id"), nullable=False)
    section_path: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    section: Mapped[str] = mapped_column(Text, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ordinals: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # prose | list | table | mixed
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embed_text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    restricted_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    restricted_rule_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # vector(384) on Postgres, JSON on SQLite. No ANN index: exact search over ~200 rows (FAP §1).
    embedding: Mapped[Any] = mapped_column(EmbeddingType, nullable=False)
    corpus_version: Mapped[str] = mapped_column(String(32), nullable=False)

    document: Mapped[Document] = relationship(lazy="joined")


class IndexMeta(Base):
    """One row: the index currently in `chunks`. Replaced in the same transaction as the chunks."""

    __tablename__ = "index_meta"

    corpus_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    dims: Mapped[int] = mapped_column(Integer, nullable=False)
    chunker_settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    built_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Retrieval(Base):
    """What was retrieved for one assistant turn. Linked to the assistant message, or to the
    failure when the turn ended in a 502 and no assistant message exists (adjustment A3)."""

    __tablename__ = "retrievals"
    __table_args__ = (
        CheckConstraint("(message_id IS NULL) <> (failure_id IS NULL)", name="ck_retrievals_one_owner"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    failure_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("failures.id"), nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    filter_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    k: Mapped[int] = mapped_column(Integer, nullable=False)
    # [{label, chunk_id, score, rank, cited, ...chunk snapshot}] so history survives an index rebuild.
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    withheld: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    top_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    corpus_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class CitationEvent(Base):
    """A claim dropped by the citation checker (FAP §9). Recorded, never silent."""

    __tablename__ = "citation_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    failure_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("failures.id"), nullable=True)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_label: Mapped[str] = mapped_column(String(16), nullable=False)
    chunk_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # unknown_label | unsupported_number | publisher_mismatch | blended_attribution
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
