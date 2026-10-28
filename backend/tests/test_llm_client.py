import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import groq
import httpx
import pytest

from app.llm import client as llm
from app.llm.errors import ModelFailure
from app.schemas.json_schema import ASSISTANT_OUTPUT_JSON_SCHEMA

VALID = {"answer": "Lentils are high in fibre.", "claims": [{"text": "Lentils are high in fibre.", "source": None}]}
MODEL = "openai/gpt-oss-120b"


def fake_response(text: str | None, finish_reason: str | None = "stop", refusal: str | None = None, choices=True):
    message = SimpleNamespace(role="assistant", content=text, reasoning=None)
    if refusal is not None:
        message.refusal = refusal
    return SimpleNamespace(
        choices=[SimpleNamespace(index=0, finish_reason=finish_reason, message=message)] if choices else [],
        model=MODEL,
        usage=SimpleNamespace(prompt_tokens=120, completion_tokens=45),
    )


@pytest.fixture
def sdk(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    return fake.chat.completions.create


def test_valid_output_returns_result(sdk):
    sdk.return_value = fake_response(json.dumps(VALID))
    result = llm.generate([], "Are lentils high in fibre?")
    assert result.output.claims[0].source is None
    assert (result.model, result.input_tokens, result.output_tokens) == (MODEL, 120, 45)
    kwargs = sdk.call_args.kwargs
    assert kwargs["model"] == MODEL
    fmt = kwargs["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == ASSISTANT_OUTPUT_JSON_SCHEMA
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["include_reasoning"] is False
    assert kwargs["max_completion_tokens"] == 16000
    system = kwargs["messages"][0]
    assert system["role"] == "system" and system["content"].startswith("You are a general-information assistant")


def test_refusal_field(sdk):
    sdk.return_value = fake_response(None, "stop", refusal="I can't help with that.")
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert e.value.type == "model_refusal" and "can't help" in e.value.detail


def test_content_filter_is_a_refusal(sdk):
    sdk.return_value = fake_response(None, "content_filter")
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert e.value.type == "model_refusal"


def test_no_choices_is_a_failure(sdk):
    sdk.return_value = fake_response(None, choices=False)
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert e.value.type == "schema_invalid"


def test_truncated(sdk):
    sdk.return_value = fake_response('{"answer": "cut', "length")
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert e.value.type == "truncated_output"
    assert e.value.raw_output == '{"answer": "cut'


@pytest.mark.parametrize("finish_reason", ["tool_calls", "function_call", None, "something_new"])
def test_unexpected_finish_reason_is_a_failure(sdk, finish_reason):
    sdk.return_value = fake_response(json.dumps(VALID), finish_reason)
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert e.value.type == "schema_invalid"


@pytest.mark.parametrize("text", [
    json.dumps({"answer": "a", "claims": [{"text": "b", "source": "x"}]}),
    json.dumps({"answer": "", "claims": []}),
    json.dumps({"answer": "a", "claims": [{"text": "", "source": None}]}),
    json.dumps({"answer": "a", "claims": [], "extra": 1}),
    "not json at all",
    None,
])
def test_schema_invalid_keeps_raw_output(sdk, text):
    sdk.return_value = fake_response(text)
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert e.value.type == "schema_invalid"
    assert e.value.raw_output == text


def _req():
    return httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")


def test_rate_limit_is_its_own_failure_type_with_retry_after(sdk):
    response = httpx.Response(429, request=_req(), headers={"retry-after": "17"})
    sdk.side_effect = groq.RateLimitError("Rate limit reached on tokens per day (TPD)", response=response, body=None)
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert (e.value.type, e.value.retry_after) == ("rate_limited", 17)
    assert "tokens per day (TPD)" in e.value.detail  # which limit was hit is kept for the failure log


def test_rate_limit_without_retry_after_header(sdk):
    sdk.side_effect = groq.RateLimitError("rate", response=httpx.Response(429, request=_req()), body=None)
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert (e.value.type, e.value.retry_after) == ("rate_limited", None)


@pytest.mark.parametrize("exc", [
    groq.APIStatusError("boom", response=httpx.Response(503, request=_req()), body=None),
    groq.NotFoundError("model", response=httpx.Response(404, request=_req()), body=None),
    groq.BadRequestError("schema", response=httpx.Response(400, request=_req()), body=None),
    groq.APIConnectionError(request=_req()),
    groq.APITimeoutError(request=_req()),
    groq.GroqError("no credentials"),
    RuntimeError("unexpected"),
])
def test_sdk_errors_become_api_error(sdk, exc):
    sdk.side_effect = exc
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert e.value.type == "api_error"


def test_status_code_in_detail(sdk):
    sdk.side_effect = groq.NotFoundError("model", response=httpx.Response(404, request=_req()), body=None)
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert "404" in e.value.detail


def turns(n):
    return [llm.Turn(role="user" if i % 2 == 0 else "assistant", content=f"t{i}") for i in range(n)]


def test_only_last_10_turns_are_sent(sdk):
    sdk.return_value = fake_response(json.dumps(VALID))
    llm.generate(turns(24), "new question")
    messages = sdk.call_args.kwargs["messages"][1:]  # after the system message
    assert [m["content"] for m in messages] == [f"t{i}" for i in range(14, 24)] + ["new question"]


class TestBuildMessages:
    def test_window_never_starts_on_assistant(self):
        msgs = llm.build_messages(turns(11), "q", history_turns=10)  # window starts at t1 (assistant)
        assert msgs[0]["role"] == "user"

    def test_unanswered_user_turn_is_dropped(self):
        history = [llm.Turn("user", "a"), llm.Turn("assistant", "b"), llm.Turn("user", "failed")]
        msgs = llm.build_messages(history, "retry", history_turns=10)
        assert [m["content"] for m in msgs] == ["a", "b", "retry"]

    def test_consecutive_user_turns_keep_the_latest(self):
        history = [llm.Turn("user", "old"), llm.Turn("user", "newer"), llm.Turn("assistant", "ans")]
        msgs = llm.build_messages(history, "q", history_turns=10)
        assert [m["content"] for m in msgs] == ["newer", "ans", "q"]

    def test_roles_alternate(self):
        msgs = llm.build_messages(turns(9), "q", history_turns=10)
        roles = [m["role"] for m in msgs]
        assert all(a != b for a, b in zip(roles, roles[1:], strict=False))


def test_only_client_module_imports_groq():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    pattern = re.compile(r"^\s*(?:import groq|from groq\b)", re.M)
    offenders = [p.relative_to(app_dir).as_posix() for p in app_dir.rglob("*.py") if pattern.search(p.read_text())]
    assert offenders == ["llm/client.py"]


def test_missing_prompt_version_raises():
    from app.llm.prompts import load_system_prompt

    with pytest.raises(FileNotFoundError):
        load_system_prompt("v999")
    with pytest.raises(ValueError):
        load_system_prompt("../etc/passwd")


# --- Milestone 2: generate_grounded (FAP §8.2) -------------------------------------------

from app.schemas.json_schema import GROUNDED_OUTPUT_JSON_SCHEMA  # noqa: E402

GROUNDED = {"coverage": "covered", "claims": [{"text": "WHO recommends less than 5 g of salt a day.",
                                               "source_label": "S1"}]}


@pytest.fixture
def v2(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "PROMPT_VERSION", "v2")


def test_grounded_valid_output(sdk, v2):
    sdk.return_value = fake_response(json.dumps(GROUNDED))
    result = llm.generate_grounded([], "<sources>…</sources>\n<question>salt?</question>")
    assert result.output.claims[0].source_label == "S1"
    assert result.raw_text == json.dumps(GROUNDED)
    kwargs = sdk.call_args.kwargs
    assert kwargs["response_format"]["json_schema"]["schema"] == GROUNDED_OUTPUT_JSON_SCHEMA
    assert kwargs["response_format"]["json_schema"]["name"] == "grounded_output"
    assert kwargs["messages"][0]["content"].startswith("You answer questions about food, nutrition and food safety")
    assert kwargs["messages"][-1] == {"role": "user", "content": "<sources>…</sources>\n<question>salt?</question>"}


def test_grounded_not_covered(sdk, v2):
    sdk.return_value = fake_response(json.dumps({"coverage": "not_covered", "claims": []}))
    assert llm.generate_grounded([], "q").output.coverage == "not_covered"


@pytest.mark.parametrize("response, failure_type", [
    (fake_response(None, "stop", refusal="no"), "model_refusal"),
    (fake_response(json.dumps(GROUNDED), "length"), "truncated_output"),
    (fake_response(json.dumps(GROUNDED), "tool_calls"), "schema_invalid"),
    (fake_response("{not json"), "schema_invalid"),
    (fake_response(json.dumps({"coverage": "covered", "claims": []})), "schema_invalid"),
    (fake_response(json.dumps({"coverage": "covered", "claims": [{"text": "x", "source_label": "S1",
                                                                  "source": "WHO"}]})), "schema_invalid"),
])
def test_grounded_failures(sdk, v2, response, failure_type):
    sdk.return_value = response
    with pytest.raises(ModelFailure) as e:
        llm.generate_grounded([], "q")
    assert e.value.type == failure_type


def test_grounded_api_error(sdk, v2):
    sdk.side_effect = groq.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))
    with pytest.raises(ModelFailure) as e:
        llm.generate_grounded([], "q")
    assert e.value.type == "api_error"


def test_grounded_call_uses_smaller_token_cap(sdk, v2):
    sdk.return_value = fake_response(json.dumps(GROUNDED))
    llm.generate_grounded([], "q")
    assert sdk.call_args.kwargs["max_completion_tokens"] == llm.GROUNDED_MAX_TOKENS < llm.MAX_TOKENS
