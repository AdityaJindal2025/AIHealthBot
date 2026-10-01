import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from app.llm import client as llm
from app.llm.errors import ModelFailure
from app.schemas.json_schema import ASSISTANT_OUTPUT_JSON_SCHEMA

VALID = {"answer": "Lentils are high in fibre.", "claims": [{"text": "Lentils are high in fibre.", "source": None}]}


def fake_response(text: str | None, stop_reason: str = "end_turn", category: str | None = None):
    content = [SimpleNamespace(type="thinking", thinking="")]
    if text is not None:
        content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        stop_details=SimpleNamespace(type="refusal", category=category, explanation=None) if category else None,
        model="claude-opus-5",
        usage=SimpleNamespace(input_tokens=120, output_tokens=45),
    )


@pytest.fixture
def sdk(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    return fake.messages.create


def test_valid_output_returns_result(sdk):
    sdk.return_value = fake_response(json.dumps(VALID))
    result = llm.generate([], "Are lentils high in fibre?")
    assert result.output.claims[0].source is None
    assert (result.model, result.input_tokens, result.output_tokens) == ("claude-opus-5", 120, 45)
    kwargs = sdk.call_args.kwargs
    assert kwargs["output_config"]["format"]["schema"] == ASSISTANT_OUTPUT_JSON_SCHEMA
    assert kwargs["output_config"]["effort"] == "low"
    assert kwargs["max_tokens"] == 16000
    assert kwargs["system"].startswith("You are a general-information assistant")
    assert "fallbacks" not in kwargs  # no server-side fallbacks in M1 (AP §5.3)


def test_refusal(sdk):
    sdk.return_value = fake_response(None, "refusal", category="cyber")
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert e.value.type == "model_refusal" and "cyber" in e.value.detail


def test_truncated(sdk):
    sdk.return_value = fake_response('{"answer": "cut', "max_tokens")
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert e.value.type == "truncated_output"
    assert e.value.raw_output == '{"answer": "cut'


@pytest.mark.parametrize("stop_reason", ["stop_sequence", "pause_turn", None, "something_new"])
def test_unexpected_stop_reason_is_a_failure(sdk, stop_reason):
    sdk.return_value = fake_response(json.dumps(VALID), stop_reason)
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
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize("exc", [
    anthropic.RateLimitError("rate", response=httpx.Response(429, request=_req()), body=None),
    anthropic.APIStatusError("boom", response=httpx.Response(529, request=_req()), body=None),
    anthropic.NotFoundError("model", response=httpx.Response(404, request=_req()), body=None),
    anthropic.APIConnectionError(request=_req()),
    anthropic.APITimeoutError(request=_req()),
    anthropic.AnthropicError("no credentials"),
    RuntimeError("unexpected"),
])
def test_sdk_errors_become_api_error(sdk, exc):
    sdk.side_effect = exc
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert e.value.type == "api_error"


def test_status_code_in_detail(sdk):
    sdk.side_effect = anthropic.NotFoundError("model", response=httpx.Response(404, request=_req()), body=None)
    with pytest.raises(ModelFailure) as e:
        llm.generate([], "q")
    assert "404" in e.value.detail


def turns(n):
    return [llm.Turn(role="user" if i % 2 == 0 else "assistant", content=f"t{i}") for i in range(n)]


def test_only_last_10_turns_are_sent(sdk):
    sdk.return_value = fake_response(json.dumps(VALID))
    llm.generate(turns(24), "new question")
    messages = sdk.call_args.kwargs["messages"]
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


def test_only_client_module_imports_anthropic():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    pattern = re.compile(r"^\s*(?:import anthropic|from anthropic\b)", re.M)
    offenders = [p.relative_to(app_dir).as_posix() for p in app_dir.rglob("*.py") if pattern.search(p.read_text())]
    assert offenders == ["llm/client.py"]


def test_missing_prompt_version_raises():
    from app.llm.prompts import load_system_prompt

    with pytest.raises(FileNotFoundError):
        load_system_prompt("v999")
    with pytest.raises(ValueError):
        load_system_prompt("../etc/passwd")
