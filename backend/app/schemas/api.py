"""Request and response envelopes between the backend and the frontend (AP §4.3).

Milestone 2 additions (FAP §11.2) are all optional, so an M1 frontend still renders an M2
response: `ChatRequest.document_id`, `grounding`, `sources`, two `Meta` fields and the
`retrieval` scope stage.
"""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.model_output import Claim

ScopeCategory = Literal["calorie_target", "weight_target", "medical_advice"]
# "model" = the model declined by itself and the output guard recognised the referral (EC SCOPE-12).
# "retrieval" = the best-matching chunk is itself a calorie or weight target (FAP §10.3).
ScopeStage = Literal["input", "output", "model", "retrieval"]

# Control characters except \t and \n. Postgres rejects \x00 in text columns (EC IN-06).
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class ChatRequest(BaseModel):
    # Unknown fields are rejected with 422 (EC IN-08 decision).
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=2000)
    # Restrict retrieval to one registry document (FAP §7.2). Unknown IDs get a 422 from the service.
    document_id: str | None = Field(default=None, min_length=1, max_length=64)
    # Restrict retrieval to a theme's documents (`corpus/themes.json`). Not combined with document_id.
    theme_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("message", mode="before")
    @classmethod
    def _clean(cls, v: object) -> object:
        if isinstance(v, str):
            return _CONTROL_CHARS.sub("", v.replace("\r\n", "\n")).strip()
        return v


class ScopeInfo(BaseModel):
    status: Literal["in_scope", "declined"]
    category: ScopeCategory | None = None
    stage: ScopeStage | None = None


class Meta(BaseModel):
    prompt_version: str
    model: str | None = None
    latency_ms: int | None = None
    # Milestone 2: claims removed by the citation checker (reported, never hidden) and the index used.
    claims_dropped: int | None = None
    corpus_version: str | None = None


class SearchedDocument(BaseModel):
    document_id: str
    document_name: str
    publisher: str
    year: int | None = None
    url: str | None = None


class Grounding(BaseModel):
    """Null on declines. On a not-covered answer `searched` names what was searched (FPS §4.5)."""

    status: Literal["grounded", "not_covered"]
    filter_document_id: str | None = None
    theme_id: str | None = None
    searched: list[SearchedDocument]
    top_score: float | None = None


class RetrievedSource(BaseModel):
    """One retrieved chunk, as the sources panel shows it. `cited` marks chunks a claim cites."""

    label: str
    chunk_id: str
    document_id: str
    document_name: str
    publisher: str
    publisher_short: str
    year: int | None = None
    url: str | None = None
    section: str
    page: int | None = None
    text: str
    score: float
    cited: bool


class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    answer: str
    claims: list[Claim]
    scope: ScopeInfo
    meta: Meta
    grounding: Grounding | None = None
    sources: list[RetrievedSource] = []


class ErrorResponse(BaseModel):
    """One error shape for every non-2xx status, so the frontend has one parser (EC FE-07)."""

    error: str
    failure_id: UUID | None = None
    detail: str | None = None


class MessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    claims: list[Claim] | None = None
    scope: ScopeInfo | None = None
    meta: Meta | None = None
    grounding: Grounding | None = None
    sources: list[RetrievedSource] = []
    created_at: datetime


class ConversationOut(BaseModel):
    id: UUID
    messages: list[MessageOut]


class DocumentOut(BaseModel):
    document_id: str
    title: str
    publisher: str
    publisher_short: str
    year: int | None = None
    url: str | None = None
    chunk_count: int


class DocumentsOut(BaseModel):
    documents: list[DocumentOut]


class ThemeOut(BaseModel):
    theme_id: str
    name: str
    description: str
    document_ids: list[str]


class ThemesOut(BaseModel):
    themes: list[ThemeOut]
