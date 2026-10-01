"""Request and response envelopes between the backend and the frontend (AP §4.3)."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.model_output import Claim

ScopeCategory = Literal["calorie_target", "weight_target", "medical_advice"]
# "model" = the model declined by itself and the output guard recognised the referral (EC SCOPE-12).
ScopeStage = Literal["input", "output", "model"]

# Control characters except \t and \n. Postgres rejects \x00 in text columns (EC IN-06).
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class ChatRequest(BaseModel):
    # Unknown fields are rejected with 422 (EC IN-08 decision).
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=2000)

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


class ChatResponse(BaseModel):
    conversation_id: UUID
    message_id: UUID
    answer: str
    claims: list[Claim]
    scope: ScopeInfo
    meta: Meta


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
    created_at: datetime


class ConversationOut(BaseModel):
    id: UUID
    messages: list[MessageOut]
