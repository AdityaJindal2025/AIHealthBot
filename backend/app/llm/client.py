"""The only module that imports `groq` (AP §5.3).

`generate()` (M1 path) returns a strictly validated `AssistantOutput`, and
`generate_grounded()` (M2) a strictly validated `GroundedOutput`; both raise `ModelFailure`
otherwise, through the same call path and error mapping (`_complete`, adjustment A1).
There are no fallbacks and no repair retries: a bad response is a failure that the
caller records (Rule 6).

The model runs on Groq through the official `groq` SDK, using Chat Completions with
`response_format={"type": "json_schema", "strict": true}` (Groq's native structured
output mode). Strict mode is only available on some Groq models, so `MODEL_ID` must
be one of them (for example `openai/gpt-oss-120b`). We read the raw text and validate
it ourselves, so `finish_reason` is checked first and the raw text is kept for the
`failures` row.
"""

import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import groq
import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.llm.errors import ModelFailure
from app.llm.prompts import load_system_prompt
from app.schemas.json_schema import ASSISTANT_OUTPUT_JSON_SCHEMA, GROUNDED_OUTPUT_JSON_SCHEMA
from app.schemas.model_output import AssistantOutput, GroundedOutput, UngroundedOutput

log = logging.getLogger("app.llm")

MAX_TOKENS = 16000
# A grounded answer is at most 8 short claims (observed: 130–480 output tokens). The cap leaves room
# for reasoning tokens while keeping each call small against the provider's token-rate limits.
GROUNDED_MAX_TOKENS = 4000
TIMEOUT_S = 60
MAX_RETRIES = 2
REASONING_EFFORT = "low"


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    content: str  # for assistant turns: the `answer` text only


@dataclass(frozen=True)
class GenerationResult:
    output: AssistantOutput
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None


def _log_http_response(response: httpx.Response) -> None:
    # One line per HTTP attempt, so SDK retries are visible in the logs (EC LLM-16).
    # Only the status and request ID are logged, never headers (they carry the API key).
    level = logging.WARNING if response.status_code >= 400 else logging.INFO
    log.log(
        level,
        "groq_http_response",
        extra={"status_code": response.status_code, "groq_request_id": response.headers.get("x-request-id")},
    )


@lru_cache
def get_client() -> groq.Groq:
    return groq.Groq(
        api_key=get_settings().GROQ_API_KEY or None,
        timeout=TIMEOUT_S,
        max_retries=MAX_RETRIES,
        http_client=groq.DefaultHttpxClient(event_hooks={"response": [_log_http_response]}),
    )


def build_messages(history: list[Turn], user_message: str, history_turns: int) -> list[dict]:
    """Last `history_turns` turns plus the new message, as a valid user/assistant alternation.

    - The window never starts on an assistant turn (EC CONV-03).
    - A user turn with no reply (its request failed) is dropped, so two user turns are
      never sent in a row (EC CONV-04).
    """
    window = history[-history_turns:] if history_turns > 0 else []
    turns: list[Turn] = []
    for turn in window:
        if turn.role == "user" and turns and turns[-1].role == "user":
            turns[-1] = turn  # previous user turn was unanswered
        else:
            turns.append(turn)
    while turns and turns[0].role == "assistant":
        turns.pop(0)
    if turns and turns[-1].role == "user":
        turns.pop()
    messages = [{"role": t.role, "content": t.content} for t in turns]
    messages.append({"role": "user", "content": user_message})
    return messages


def validate_output(raw_text: str | None) -> AssistantOutput:
    """Strict validation of the model's JSON text. Raises ValueError/ValidationError."""
    if raw_text is None:
        raise ValueError("response has no text content")
    data = json.loads(raw_text)
    output = UngroundedOutput.model_validate(data, strict=True)
    if not all(c.source is None for c in output.claims):  # Rule 3, belt and braces
        raise ValueError("claims[].source must be null when answering without retrieval")
    return AssistantOutput.model_validate(output.model_dump())


@dataclass(frozen=True)
class _Completion:
    raw_text: str | None
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None


def _retry_after(e: groq.APIStatusError) -> int | None:
    value = e.response.headers.get("retry-after") if e.response is not None else None
    try:
        return max(1, int(float(value))) if value else None
    except ValueError:
        return None


def _complete(messages: list[dict], schema_name: str, schema: dict, max_tokens: int = MAX_TOKENS) -> _Completion:
    """One strict-schema chat completion. Maps every SDK error and bad finish to `ModelFailure`."""
    model_id = get_settings().MODEL_ID
    start = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - start) * 1000)

    try:
        response = get_client().chat.completions.create(
            model=model_id,
            messages=messages,
            max_completion_tokens=max_tokens,
            reasoning_effort=REASONING_EFFORT,
            # Reasoning goes in a separate field we never use; leave it out of the response.
            include_reasoning=False,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        )
    except groq.RateLimitError as e:
        # The SDK has already retried (max_retries); the provider is still refusing.
        raise ModelFailure("rate_limited", f"status={e.status_code}", model=model_id, latency_ms=elapsed(),
                           retry_after=_retry_after(e)) from e
    except groq.APIStatusError as e:
        raise ModelFailure("api_error", f"status={e.status_code} {e.message}", model=model_id,
                           latency_ms=elapsed()) from e
    except groq.APIConnectionError as e:
        kind = "timeout" if isinstance(e, groq.APITimeoutError) else "connection_error"
        raise ModelFailure("api_error", kind, model=model_id, latency_ms=elapsed()) from e
    except groq.GroqError as e:
        # e.g. no credentials configured (EC LLM-12)
        raise ModelFailure("api_error", f"{type(e).__name__}: {e}", model=model_id,
                           latency_ms=elapsed()) from e
    except Exception as e:  # anything unexpected is still a recorded failure, never a bare 500
        raise ModelFailure("api_error", f"unexpected {type(e).__name__}: {e}", model=model_id,
                           latency_ms=elapsed()) from e

    latency_ms = elapsed()
    served_model = getattr(response, "model", None) or model_id
    if not response.choices:
        raise ModelFailure("schema_invalid", "response has no choices", model=served_model, latency_ms=latency_ms)
    choice = response.choices[0]
    raw_text = choice.message.content
    finish_reason = choice.finish_reason

    # Check finish_reason before reading content (AP §4.2 step 2).
    refusal = getattr(choice.message, "refusal", None)
    if refusal or finish_reason == "content_filter":
        raise ModelFailure("model_refusal", f"finish_reason={finish_reason} refusal={refusal!r}", raw_text,
                           model=served_model, latency_ms=latency_ms)
    if finish_reason == "length":
        raise ModelFailure("truncated_output", f"max_completion_tokens={max_tokens}", raw_text, model=served_model,
                           latency_ms=latency_ms)
    if finish_reason != "stop":
        # Never assume only a few values exist (EC LLM-04).
        raise ModelFailure("schema_invalid", f"unexpected finish_reason={finish_reason!r}", raw_text,
                           model=served_model, latency_ms=latency_ms)

    usage = getattr(response, "usage", None)
    return _Completion(raw_text, served_model, latency_ms, getattr(usage, "prompt_tokens", None),
                       getattr(usage, "completion_tokens", None))


def generate(history: list[Turn], user_message: str) -> GenerationResult:
    """Milestone 1 path (`RAG_ENABLED=false`): answers from the model, every `source` null."""
    settings = get_settings()
    messages = [{"role": "system", "content": load_system_prompt(settings.PROMPT_VERSION)}]
    messages += build_messages(history, user_message, settings.HISTORY_TURNS)
    done = _complete(messages, "assistant_output", ASSISTANT_OUTPUT_JSON_SCHEMA)
    try:
        output = validate_output(done.raw_text)
    except (ValidationError, json.JSONDecodeError, ValueError) as e:
        raise ModelFailure("schema_invalid", str(e)[:2000], done.raw_text, model=done.model,
                           latency_ms=done.latency_ms) from e
    return GenerationResult(output=output, model=done.model, latency_ms=done.latency_ms,
                            input_tokens=done.input_tokens, output_tokens=done.output_tokens)


@dataclass(frozen=True)
class GroundedResult:
    output: GroundedOutput
    model: str
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    raw_text: str | None


def validate_grounded(raw_text: str | None) -> GroundedOutput:
    """Strict validation of the grounded JSON (FAP §8.2). Raises ValueError/ValidationError."""
    if raw_text is None:
        raise ValueError("response has no text content")
    return GroundedOutput.model_validate(json.loads(raw_text), strict=True)


def generate_grounded(history: list[Turn], user_turn: str) -> GroundedResult:
    """Milestone 2 path: `user_turn` holds the labelled sources and the question (FAP §8.1).

    History turns carry the composed answers (with citation markers) of earlier turns; only the
    current turn's sources are sent, so the model can only cite what was retrieved now.
    """
    settings = get_settings()
    messages = [{"role": "system", "content": load_system_prompt(settings.PROMPT_VERSION)}]
    messages += build_messages(history, user_turn, settings.HISTORY_TURNS)
    done = _complete(messages, "grounded_output", GROUNDED_OUTPUT_JSON_SCHEMA, GROUNDED_MAX_TOKENS)
    try:
        output = validate_grounded(done.raw_text)
    except (ValidationError, json.JSONDecodeError, ValueError) as e:
        raise ModelFailure("schema_invalid", str(e)[:2000], done.raw_text, model=done.model,
                           latency_ms=done.latency_ms) from e
    return GroundedResult(output=output, model=done.model, latency_ms=done.latency_ms,
                          input_tokens=done.input_tokens, output_tokens=done.output_tokens, raw_text=done.raw_text)
