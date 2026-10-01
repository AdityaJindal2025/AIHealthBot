"""The only module that imports `anthropic` (AP §5.3).

`generate()` either returns a strictly validated `AssistantOutput` or raises `ModelFailure`.
There are no server-side fallbacks and no repair retries: a bad response is a failure
that the caller records (Rule 6).

Why `messages.create` + `output_config.format` instead of `messages.parse`: in the
installed SDK, `parse()` parses the text inside the call, so a truncated or refused
response raises a parse error before `stop_reason` can be checked and the raw text is
lost. Using the documented raw-schema path lets us check `stop_reason` first and keep
the raw text for the `failures` row (IP Risks: "fall back to messages.create with
output_config.format + Pydantic validation").
"""

import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import anthropic
import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.llm.errors import ModelFailure
from app.llm.prompts import load_system_prompt
from app.schemas.json_schema import ASSISTANT_OUTPUT_JSON_SCHEMA
from app.schemas.model_output import AssistantOutput

log = logging.getLogger("app.llm")

MAX_TOKENS = 16000
TIMEOUT_S = 60
MAX_RETRIES = 2


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
        "anthropic_http_response",
        extra={"status_code": response.status_code, "anthropic_request_id": response.headers.get("request-id")},
    )


@lru_cache
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=get_settings().ANTHROPIC_API_KEY or None,
        timeout=TIMEOUT_S,
        max_retries=MAX_RETRIES,
        http_client=anthropic.DefaultHttpxClient(event_hooks={"response": [_log_http_response]}),
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


def _first_text(response: anthropic.types.Message) -> str | None:
    for block in response.content:
        if block.type == "text":
            return block.text
    return None


def validate_output(raw_text: str | None) -> AssistantOutput:
    """Strict validation of the model's JSON text. Raises ValueError/ValidationError."""
    if raw_text is None:
        raise ValueError("response has no text content block")
    data = json.loads(raw_text)
    output = AssistantOutput.model_validate(data, strict=True)
    if not all(c.source is None for c in output.claims):  # Rule 3, belt and braces
        raise ValueError("claims[].source must be null in Milestone 1")
    return output


def generate(history: list[Turn], user_message: str) -> GenerationResult:
    settings = get_settings()
    model_id = settings.MODEL_ID
    messages = build_messages(history, user_message, settings.HISTORY_TURNS)

    start = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - start) * 1000)

    try:
        response = get_client().messages.create(
            model=model_id,
            max_tokens=MAX_TOKENS,
            system=load_system_prompt(settings.PROMPT_VERSION),
            messages=messages,
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": ASSISTANT_OUTPUT_JSON_SCHEMA},
            },
        )
    except anthropic.RateLimitError as e:
        raise ModelFailure("api_error", f"rate_limited status={e.status_code}", model=model_id,
                           latency_ms=elapsed()) from e
    except anthropic.APIStatusError as e:
        raise ModelFailure("api_error", f"status={e.status_code} {e.message}", model=model_id,
                           latency_ms=elapsed()) from e
    except anthropic.APIConnectionError as e:
        kind = "timeout" if isinstance(e, anthropic.APITimeoutError) else "connection_error"
        raise ModelFailure("api_error", kind, model=model_id, latency_ms=elapsed()) from e
    except anthropic.AnthropicError as e:
        # e.g. no credentials configured (EC LLM-12)
        raise ModelFailure("api_error", f"{type(e).__name__}: {e}", model=model_id,
                           latency_ms=elapsed()) from e
    except Exception as e:  # anything unexpected is still a recorded failure, never a bare 500
        raise ModelFailure("api_error", f"unexpected {type(e).__name__}: {e}", model=model_id,
                           latency_ms=elapsed()) from e

    latency_ms = elapsed()
    served_model = getattr(response, "model", None) or model_id
    raw_text = _first_text(response)

    # Check stop_reason before reading content (AP §4.2 step 2).
    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        raise ModelFailure("model_refusal", f"category={category}", raw_text, model=served_model,
                           latency_ms=latency_ms)
    if response.stop_reason == "max_tokens":
        raise ModelFailure("truncated_output", f"max_tokens={MAX_TOKENS}", raw_text, model=served_model,
                           latency_ms=latency_ms)
    if response.stop_reason != "end_turn":
        # Never assume only three values exist (EC LLM-04).
        raise ModelFailure("schema_invalid", f"unexpected stop_reason={response.stop_reason!r}", raw_text,
                           model=served_model, latency_ms=latency_ms)

    try:
        output = validate_output(raw_text)
    except (ValidationError, json.JSONDecodeError, ValueError) as e:
        raise ModelFailure("schema_invalid", str(e)[:2000], raw_text, model=served_model,
                           latency_ms=latency_ms) from e

    usage = getattr(response, "usage", None)
    return GenerationResult(
        output=output,
        model=served_model,
        latency_ms=latency_ms,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )
