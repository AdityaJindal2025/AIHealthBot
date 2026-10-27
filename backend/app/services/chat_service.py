"""Orchestrates input guard -> (retrieve) -> model -> validate -> output guard -> persist.

Two paths share the guards and persistence:

- **Grounded** (`RAG_ENABLED=true`, FAP §11.4): retrieve → restricted-chunk decline → score
  floor → model over labelled sources → citation checks → composed answer → output guard.
- **M1** (`RAG_ENABLED=false`, AP §5.2): unchanged, answers from the model with `source: null`.
"""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import repo
from app.db.models import Document, Message
from app.failures import record_failure
from app.guards.decline import build_decline
from app.guards.input_guard import check_input
from app.guards.matching import GuardResult
from app.guards.output_guard import check_output, detect_model_decline
from app.llm import client as llm
from app.llm.errors import ModelFailure
from app.rag.citations import PublisherInfo, check_claims
from app.rag.composer import compose_answer, compose_not_covered
from app.rag.context import format_sources
from app.rag.retriever import RetrievalError, RetrievalResult, RetrievedChunk, retrieve
from app.schemas.api import (
    ChatRequest,
    ChatResponse,
    Grounding,
    Meta,
    RetrievedSource,
    ScopeInfo,
    SearchedDocument,
)
from app.schemas.model_output import AssistantOutput

log = logging.getLogger("app.chat")


class ChatError(Exception):
    """An error with its HTTP status and `ErrorResponse` body."""

    def __init__(self, status_code: int, error: str, *, failure_id: uuid.UUID | None = None,
                 detail: str | None = None, retry_after: int | None = None) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.error = error
        self.failure_id = failure_id
        self.detail = detail
        self.retry_after = retry_after


UPSTREAM_RATE_LIMITED = "upstream_rate_limited"
DEFAULT_RETRY_AFTER_S = 30


def _model_error(failure: ModelFailure) -> ChatError:
    """502 for a bad or missing model answer; 503 + Retry-After when the provider is rate limiting."""
    if failure.type == "rate_limited":
        return ChatError(503, UPSTREAM_RATE_LIMITED, failure_id=failure.failure_id, detail=failure.type,
                         retry_after=failure.retry_after or DEFAULT_RETRY_AFTER_S)
    return ChatError(502, "model_output_invalid", failure_id=failure.failure_id, detail=failure.type)


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

    # 0. Grounded mode needs an index, and a filter must name a registry document. Checked before
    #    anything is written, so a rejected request leaves no rows.
    documents: dict[str, Document] = {}
    if settings.RAG_ENABLED:
        if repo.get_index_meta(db) is None:
            raise ChatError(503, "index_not_ready", detail="The document index is being built. Try again shortly.")
        documents = {d.document_id: d for d, _ in repo.list_documents(db)}
        if req.document_id is not None and req.document_id not in documents:
            raise ChatError(422, "unknown_document", detail=f"No document with id {req.document_id!r}.")
    elif req.document_id is not None:
        raise ChatError(422, "unknown_document", detail="Document filters need grounded mode.")

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

    if settings.RAG_ENABLED:
        return _handle_grounded(db, conv.id, req, history, documents, ctx)

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
        raise _model_error(failure) from failure

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
                       raw_output: str | None = None, grounding: Grounding | None = None,
                       sources: list[RetrievedSource] | None = None) -> ChatResponse:
    declined = verdict is not None and not verdict.allowed
    settings = get_settings()
    try:
        msg = repo.add_message(
            db,
            conversation_id,
            role="assistant",
            content=output.answer,
            claims=[c.model_dump(mode="json") for c in output.claims],
            status="declined" if declined else "ok",
            scope_category=verdict.category if declined else None,
            scope_stage=stage if declined else None,
            prompt_version=settings.PROMPT_VERSION,
            model=usage.get("model"),
            latency_ms=usage.get("latency_ms"),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            grounding=grounding.model_dump(mode="json") if grounding else None,
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
        grounding=grounding,
        sources=sources or [],
    )


# --- Grounded path (FAP §11.4) ---------------------------------------------------------------


def _searched(documents: dict[str, Document], filter_document_id: str | None) -> list[SearchedDocument]:
    """What was searched, from the registry, never from the model (FAP §10.1)."""
    ids = [filter_document_id] if filter_document_id else sorted(documents)
    return [SearchedDocument(document_id=d.document_id, document_name=d.title, publisher=d.publisher, year=d.year,
                             url=d.url) for d in (documents[i] for i in ids)]


def _sources(hits: list[RetrievedChunk], cited: set[str]) -> list[RetrievedSource]:
    return [RetrievedSource(label=h.label, chunk_id=h.chunk_id, document_id=h.document_id,
                            document_name=h.document_name, publisher=h.publisher,
                            publisher_short=h.publisher_short, year=h.year, url=h.url, section=h.section,
                            page=h.page_start, text=h.text, score=h.score, cited=h.chunk_id in cited)
            for h in hits]


def _record_retrieval(db: Session, retrieval: RetrievalResult, cited: set[str], *,
                      message_id: uuid.UUID | None = None, failure_id: uuid.UUID | None = None) -> None:
    if message_id is None and failure_id is None:
        return  # the failure row itself could not be written (EC DB-06); the log has everything
    repo.record_retrieval(
        db, message_id=message_id, failure_id=failure_id, query=retrieval.query_text,
        filter_document_id=retrieval.filter_document_id, k=retrieval.k,
        results=[{**h.to_dict(), "cited": h.chunk_id in cited} for h in retrieval.hits],
        withheld=[w.to_dict() for w in retrieval.withheld], top_score=retrieval.top_score,
        corpus_version=retrieval.corpus_version,
    )


def _citation_events(dropped) -> list[dict[str, Any]]:
    return [{"claim_text": d.claim.text, "source_label": d.claim.source_label, "chunk_id": d.chunk_id,
             "reason": d.reason} for d in dropped]


def _handle_grounded(db: Session, conversation_id: uuid.UUID, req: ChatRequest, history: "_History",
                     documents: dict[str, Document], ctx: dict[str, Any]) -> ChatResponse:
    settings = get_settings()
    base_context = {"message": req.message, "prompt_version": settings.PROMPT_VERSION,
                    "document_id": req.document_id}

    def fail(type_: str, detail: str, raw_output: str | None, retrieval: RetrievalResult | None,
             extra: dict[str, Any] | None = None, dropped=None, status: int = 502,
             error: str = "model_output_invalid", retry_after: int | None = None) -> ChatError:
        failure_id = record_failure(db, type=type_, detail=detail, raw_output=raw_output,
                                    context={**base_context, **(extra or {})}, conversation_id=conversation_id)
        if retrieval is not None:
            _record_retrieval(db, retrieval, set(), failure_id=failure_id)
        if dropped and failure_id is not None:
            repo.record_citation_events(db, message_id=None, failure_id=failure_id, events=_citation_events(dropped))
        ctx.update(failure_type=type_, failure_id=str(failure_id) if failure_id else None)
        return ChatError(status, error, failure_id=failure_id, detail=type_, retry_after=retry_after)

    # 4. Retrieve. The previous question rides along for short follow-ups (FAP §7.3).
    try:
        retrieval = retrieve(db, req.message, previous_user_message=history.previous_user_text,
                             document_id=req.document_id)
    except RetrievalError as e:
        raise fail(e.type, e.detail, None, None, error="retrieval_failed") from e
    ctx.update(top_score=retrieval.top_score, filter_document_id=retrieval.filter_document_id,
               corpus_version=retrieval.corpus_version)
    meta = Meta(prompt_version=settings.PROMPT_VERSION, corpus_version=retrieval.corpus_version)
    searched = _searched(documents, retrieval.filter_document_id)
    filtered = retrieval.mode == "filtered"

    # 5. The best match is itself a calorie or weight target: decline, model not called (FAP §10.3).
    if retrieval.restricted_top:
        verdict = GuardResult(allowed=False, category=retrieval.restricted_top,  # type: ignore[arg-type]
                              rule_id=retrieval.restricted_top_rule_id,
                              matched_rules=[retrieval.restricted_top_rule_id or ""])
        response = _decline(db, conversation_id, verdict, stage="retrieval", raw_output=None, meta=meta)
        _record_retrieval(db, retrieval, set(), message_id=response.message_id)
        return response

    # 6. Nothing close enough: not covered, model not called. The floor applies in all-documents
    #    mode only; a filtered request's scores are limited to one document (FAP §7.4).
    below_floor = retrieval.top_score is None or (not filtered and retrieval.top_score < settings.RETRIEVAL_MIN_SCORE)
    if not retrieval.hits or below_floor:
        return _not_covered(db, conversation_id, retrieval, searched, filtered, meta, {}, ctx)

    # 7. The model answers from the labelled sources only.
    user_turn, label_map = format_sources(retrieval.hits, req.message)
    try:
        result = llm.generate_grounded(history.model_turns, user_turn)
    except ModelFailure as failure:
        extra = {"model": failure.model or settings.MODEL_ID, "latency_ms": failure.latency_ms,
                 "history_turns": len(history.model_turns)}
        if failure.type == "rate_limited":
            raise fail(failure.type, failure.detail, None, retrieval, extra, status=503,
                       error=UPSTREAM_RATE_LIMITED,
                       retry_after=failure.retry_after or DEFAULT_RETRY_AFTER_S) from failure
        raise fail(failure.type, failure.detail, failure.raw_output, retrieval, extra) from failure
    usage = {"model": result.model, "latency_ms": result.latency_ms, "input_tokens": result.input_tokens,
             "output_tokens": result.output_tokens}
    ctx.update(model=result.model, latency_ms=result.latency_ms, input_tokens=result.input_tokens,
               output_tokens=result.output_tokens)
    meta = meta.model_copy(update={"model": result.model, "latency_ms": result.latency_ms})

    # 8. The model says the sources don't answer it.
    if result.output.coverage == "not_covered":
        return _not_covered(db, conversation_id, retrieval, searched, filtered, meta, usage, ctx)

    # 9. Citation checks. Dropped claims are recorded; no valid claim left is a failure (Rule 6).
    publishers = [PublisherInfo(d.document_id, d.publisher, tuple(d.publisher_aliases)) for d in documents.values()]
    citations = check_claims(result.output, label_map, publishers)
    ctx["claims_dropped"] = len(citations.dropped)
    if not citations.valid:
        reasons = ", ".join(sorted({d.reason for d in citations.dropped}))
        raise fail("no_valid_claims", f"all {len(citations.dropped)} claims dropped: {reasons}", result.raw_text,
                   retrieval, {"model": result.model}, dropped=citations.dropped)

    # 10. Compose, then the output guard over every composed claim (M1 rules still apply).
    output = compose_answer(citations.valid)
    meta = meta.model_copy(update={"claims_dropped": len(citations.dropped)})
    cited = {v.chunk.chunk_id for v in citations.valid}
    verdict = check_output(output)
    if not verdict.allowed:
        response = _decline(db, conversation_id, verdict, stage="output", raw_output=output.model_dump_json(),
                            meta=meta, usage=usage)
        _record_retrieval(db, retrieval, cited, message_id=response.message_id)
        repo.record_citation_events(db, message_id=response.message_id, failure_id=None,
                                    events=_citation_events(citations.dropped))
        return response

    # 11. Rule 2 in code: a claim without a citation never ships.
    if any(c.source is None for c in output.claims):
        raise fail("missing_citation", "composed claim without a source", output.model_dump_json(), retrieval)

    grounding = Grounding(status="grounded", filter_document_id=retrieval.filter_document_id, searched=searched,
                          top_score=retrieval.top_score)
    ctx["grounding_status"] = "grounded"
    response = _persist_assistant(db, conversation_id, output, meta, usage, grounding=grounding,
                                  sources=_sources(retrieval.hits, cited))
    _record_retrieval(db, retrieval, cited, message_id=response.message_id)
    repo.record_citation_events(db, message_id=response.message_id, failure_id=None,
                                events=_citation_events(citations.dropped))
    return response


def _not_covered(db: Session, conversation_id: uuid.UUID, retrieval: RetrievalResult,
                 searched: list[SearchedDocument], filtered: bool, meta: Meta, usage: dict[str, Any],
                 ctx: dict[str, Any]) -> ChatResponse:
    """"We don't have guidance on that": in scope, but the documents don't answer it (FPS §4.5)."""
    output = compose_not_covered(searched, filtered=filtered)
    grounding = Grounding(status="not_covered", filter_document_id=retrieval.filter_document_id, searched=searched,
                          top_score=retrieval.top_score)
    ctx["grounding_status"] = "not_covered"
    response = _persist_assistant(db, conversation_id, output, meta, usage, grounding=grounding,
                                  sources=_sources(retrieval.hits, set()))
    _record_retrieval(db, retrieval, set(), message_id=response.message_id)
    return response
