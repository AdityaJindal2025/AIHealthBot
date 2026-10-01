"""Orchestrates input guard -> model -> validate -> output guard -> persist (AP §5.2)."""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import repo
from app.db.models import Message
from app.failures import record_failure
from app.guards.decline import build_decline
from app.guards.input_guard import check_input
from app.guards.matching import GuardResult
from app.guards.output_guard import check_output, detect_model_decline
from app.llm import client as llm
from app.llm.errors import ModelFailure
from app.schemas.api import ChatRequest, ChatResponse, Meta, ScopeInfo
from app.schemas.model_output import AssistantOutput

log = logging.getLogger("app.chat")


class ChatError(Exception):
    """An error with its HTTP status and `ErrorResponse` body."""

    def __init__(self, status_code: int, error: str, *, failure_id: uuid.UUID | None = None,
                 detail: str | None = None) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.error = error
        self.failure_id = failure_id
        self.detail = detail


@dataclass
class _History:
    model_turns: list[llm.Turn]
    previous_user_text: str | None
    previous_decline_category: str | None


def _history_from(messages: list[Message]) -> _History:
    """Build what the guards and the model see from stored messages.

    Declined exchanges (the blocked question and its decline) are left out of the history
    sent to the model, so it never sees a blocked question (EC CONV-05, SCOPE-09 decision).
    The input guard gets the previous decline's category instead.
    """
    turns: list[llm.Turn] = []
    for msg in messages:
        if msg.role == "assistant" and msg.status == "declined":
            if turns and turns[-1].role == "user":
                turns.pop()
            continue
        turns.append(llm.Turn(role=msg.role, content=msg.content))  # type: ignore[arg-type]

    last = messages[-1] if messages else None
    previous_decline = last.scope_category if last and last.role == "assistant" and last.status == "declined" else None
    previous_user = None
    if previous_decline is None:
        previous_user = next((m.content for m in reversed(messages) if m.role == "user"), None)
    return _History(turns, previous_user, previous_decline)


def handle_chat(db: Session, req: ChatRequest) -> ChatResponse:
    settings = get_settings()
    started = time.monotonic()
    ctx: dict[str, Any] = {"prompt_version": settings.PROMPT_VERSION}
    try:
        response = _handle(db, req, ctx)
        ctx.update(scope_status=response.scope.status, scope_category=response.scope.category,
                   scope_stage=response.scope.stage, conversation_id=str(response.conversation_id))
        return response
    except ChatError as e:
        ctx.update(http_status=e.status_code, error=e.error)
        raise
    finally:
        ctx["total_ms"] = int((time.monotonic() - started) * 1000)
        log.info("chat_request", extra=ctx)


def _handle(db: Session, req: ChatRequest, ctx: dict[str, Any]) -> ChatResponse:
    settings = get_settings()

    # 1. Load or create the conversation.
    if req.conversation_id is not None:
        conv = repo.get_conversation(db, req.conversation_id)
        if conv is None:
            raise ChatError(404, "conversation_not_found")
        # One "turn" is one user message (EC CONV-01 decision).
        if repo.count_user_messages(db, conv.id) >= settings.MAX_USER_TURNS:
            raise ChatError(422, "conversation_turn_limit",
                            detail=f"This conversation has reached {settings.MAX_USER_TURNS} messages. "
                                   "Start a new chat to continue.")
        history = _history_from(repo.recent_turns(db, conv.id, n=settings.HISTORY_TURNS * 3))
    else:
        conv = repo.create_conversation(db)
        history = _History([], None, None)
    ctx["conversation_id"] = str(conv.id)

    # 2. Save the user message.
    repo.add_message(db, conv.id, role="user", content=req.message)

    # 3. Input guard. The model is not called for a decline.
    verdict = check_input(
        req.message,
        previous_user_text=history.previous_user_text,
        previous_decline_category=history.previous_decline_category,  # type: ignore[arg-type]
    )
    if not verdict.allowed:
        return _decline(db, conv.id, verdict, stage="input", raw_output=None, meta=Meta(
            prompt_version=settings.PROMPT_VERSION))

    # 4. Model call. Failures are recorded, never hidden (Rule 6).
    try:
        result = llm.generate(history.model_turns, req.message)
    except ModelFailure as failure:
        failure.failure_id = record_failure(
            db,
            type=failure.type,
            detail=failure.detail,
            raw_output=failure.raw_output,
            context={
                "message": req.message,
                "prompt_version": settings.PROMPT_VERSION,
                "model": failure.model or settings.MODEL_ID,
                "latency_ms": failure.latency_ms,
                "history_turns": len(history.model_turns),
            },
            conversation_id=conv.id,
        )
        ctx.update(failure_type=failure.type, failure_id=str(failure.failure_id) if failure.failure_id else None)
        raise ChatError(502, "model_output_invalid", failure_id=failure.failure_id, detail=failure.type) from failure

    ctx.update(model=result.model, latency_ms=result.latency_ms, input_tokens=result.input_tokens,
               output_tokens=result.output_tokens)
    meta = Meta(prompt_version=settings.PROMPT_VERSION, model=result.model, latency_ms=result.latency_ms)
    usage = {"model": result.model, "latency_ms": result.latency_ms, "input_tokens": result.input_tokens,
             "output_tokens": result.output_tokens}

    # 5. Output guard. A leak is discarded and the raw output kept in scope_events (AP §6.3).
    verdict = check_output(result.output)
    if not verdict.allowed:
        return _decline(db, conv.id, verdict, stage="output", raw_output=result.output.model_dump_json(),
                        meta=meta, usage=usage)

    # 5b. The model declined by itself: keep its answer, report it as declined (EC SCOPE-12).
    verdict = detect_model_decline(result.output, req.message)
    if not verdict.allowed:
        return _persist_assistant(db, conv.id, result.output, meta, usage, verdict=verdict, stage="model")

    # 6. In scope.
    return _persist_assistant(db, conv.id, result.output, meta, usage)


def _decline(db: Session, conversation_id: uuid.UUID, verdict: GuardResult, *, stage: str,
             raw_output: str | None, meta: Meta, usage: dict[str, Any] | None = None) -> ChatResponse:
    assert verdict.category is not None
    output = build_decline(verdict.category)
    return _persist_assistant(db, conversation_id, output, meta, usage or {}, verdict=verdict, stage=stage,
                              raw_output=raw_output)


def _persist_assistant(db: Session, conversation_id: uuid.UUID, output: AssistantOutput, meta: Meta,
                       usage: dict[str, Any], *, verdict: GuardResult | None = None, stage: str | None = None,
                       raw_output: str | None = None) -> ChatResponse:
    declined = verdict is not None and not verdict.allowed
    settings = get_settings()
    try:
        msg = repo.add_message(
            db,
            conversation_id,
            role="assistant",
            content=output.answer,
            claims=[c.model_dump() for c in output.claims],
            status="declined" if declined else "ok",
            scope_category=verdict.category if declined else None,
            scope_stage=stage if declined else None,
            prompt_version=settings.PROMPT_VERSION,
            model=usage.get("model"),
            latency_ms=usage.get("latency_ms"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )
        if declined:
            repo.record_scope_event(
                db,
                conversation_id=conversation_id,
                message_id=msg.id,
                stage=stage or "input",
                category=verdict.category,  # type: ignore[arg-type]
                rule_id=verdict.rule_id or "",
                matched_rules=verdict.matched_rules,
                raw_output=raw_output,
            )
    except SQLAlchemyError:
        db.rollback()
        # The answer would otherwise be lost silently (EC DB-05).
        log.exception("assistant_message_not_saved", extra={
            "conversation_id": str(conversation_id), "output": output.model_dump_json(), "raw_output": raw_output})
        raise

    return ChatResponse(
        conversation_id=conversation_id,
        message_id=msg.id,
        answer=output.answer,
        claims=output.claims,
        scope=ScopeInfo(status="declined", category=verdict.category, stage=stage) if declined  # type: ignore[arg-type]
        else ScopeInfo(status="in_scope"),
        meta=meta,
    )
