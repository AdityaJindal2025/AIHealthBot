import logging
import uuid

import pytest
from sqlalchemy import func, select

from app.db.models import Failure, Message, ScopeEvent
from app.llm import client as llm
from app.llm.errors import ModelFailure
from app.schemas.model_output import AssistantOutput, Claim

GOOD = AssistantOutput(answer="Lentils are high in fibre and protein.",
                       claims=[Claim(text="Lentils are high in fibre."), Claim(text="Lentils contain protein.")])


def result(output=GOOD):
    return llm.GenerationResult(output=output, model="openai/gpt-oss-120b", latency_ms=1234, input_tokens=100,
                                output_tokens=50)


@pytest.fixture
def generate(monkeypatch):
    calls = []
    state = {"next": result()}

    def fake(history, message):
        calls.append((history, message))
        if isinstance(state["next"], Exception):
            raise state["next"]
        return state["next"]

    monkeypatch.setattr(llm, "generate", fake)
    fake.calls = calls
    fake.state = state
    return fake


def count(db, model, **where):
    stmt = select(func.count()).select_from(model)
    for k, v in where.items():
        stmt = stmt.where(getattr(model, k) == v)
    return db.scalar(stmt)


def post(client, message, conversation_id=None):
    body = {"message": message}
    if conversation_id:
        body["conversation_id"] = str(conversation_id)
    return client.post("/api/chat", json=body)


def test_in_scope(client, db, generate):
    r = post(client, "Are lentils healthy?")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == {"status": "in_scope", "category": None, "stage": None}
    assert body["meta"] == {"prompt_version": "v1", "model": "openai/gpt-oss-120b", "latency_ms": 1234}
    assert all(c["source"] is None for c in body["claims"])
    assert count(db, Message) == 2
    stored = db.scalars(select(Message).where(Message.role == "assistant")).one()
    assert (stored.prompt_version, stored.model, stored.input_tokens) == ("v1", "openai/gpt-oss-120b", 100)


def test_input_guard_decline_does_not_call_model(client, db, generate):
    r = post(client, "What should I weigh?")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == {"status": "declined", "category": "weight_target", "stage": "input"}
    assert body["claims"] == []
    assert generate.calls == []
    assert count(db, Message) == 2
    event = db.scalars(select(ScopeEvent)).one()
    assert (event.stage, event.rule_id, event.raw_output) == ("input", "IN-WT-02", None)


def test_output_guard_catch_keeps_raw_output(client, db, generate):
    leak = AssistantOutput(answer="You should aim for 1,500 calories a day.", claims=[])
    generate.state["next"] = result(leak)
    r = post(client, "Tell me about eating less")
    body = r.json()
    assert r.status_code == 200
    assert body["scope"] == {"status": "declined", "category": "calorie_target", "stage": "output"}
    assert "1,500" not in body["answer"]
    event = db.scalars(select(ScopeEvent)).one()
    assert event.stage == "output" and "1,500 calories" in event.raw_output
    assert count(db, Message) == 2


def test_model_self_decline_reported_as_declined(client, db, generate):
    generate.state["next"] = result(AssistantOutput(
        answer="I can't give personal calorie targets. A registered dietitian can help.", claims=[]))
    body = post(client, "roughly how much food per day for me").json()
    assert body["scope"]["status"] == "declined" and body["scope"]["stage"] == "model"
    assert db.scalars(select(ScopeEvent)).one().rule_id == "OUT-MODEL-01"


@pytest.mark.parametrize("ftype", ["schema_invalid", "model_refusal", "truncated_output", "api_error"])
def test_model_failure_returns_502_and_records(client, db, generate, ftype):
    generate.state["next"] = ModelFailure(ftype, "detail", raw_output='{"bad":')
    r = post(client, "Is fish healthy?")
    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "model_output_invalid" and body["detail"] == ftype
    failure = db.get(Failure, uuid.UUID(body["failure_id"]))
    assert failure.type == ftype and failure.raw_output == '{"bad":'
    assert failure.request_context["message"] == "Is fish healthy?"
    assert count(db, Message) == 1 and count(db, Message, role="user") == 1


def test_failure_not_recorded_still_502(client, db, generate, monkeypatch):
    from app.db import repo

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(repo, "record_failure", boom)
    generate.state["next"] = ModelFailure("schema_invalid", "x")
    r = post(client, "Is fish healthy?")
    assert r.status_code == 502 and r.json()["failure_id"] is None


@pytest.mark.parametrize("message", ["", "   \n", "a" * 2001])
def test_invalid_message_422_writes_nothing(client, db, generate, message):
    r = post(client, message)
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_request"
    assert count(db, Message) == 0


def test_exactly_2000_chars_accepted(client, generate):
    assert post(client, "a" * 2000).status_code == 200


@pytest.mark.parametrize("body", [{}, {"message": None}, {"message": 123}, {"message": "hi", "extra": 1},
                                  {"message": "hi", "conversation_id": "abc"}])
def test_malformed_bodies_422(client, body):
    assert client.post("/api/chat", json=body).status_code == 422


def test_unknown_conversation_404(client, db, generate):
    r = post(client, "hi", conversation_id=uuid.uuid4())
    assert r.status_code == 404 and r.json()["error"] == "conversation_not_found"
    assert count(db, Message) == 0


def test_follow_up_passes_history(client, generate):
    first = post(client, "How much protein is in tofu?").json()
    post(client, "What about tempeh?", first["conversation_id"])
    history, message = generate.calls[-1]
    assert message == "What about tempeh?"
    assert [(t.role, t.content) for t in history] == [("user", "How much protein is in tofu?"),
                                                      ("assistant", GOOD.answer)]


def test_declined_exchange_left_out_of_model_history(client, generate):
    first = post(client, "What should I weigh?").json()
    post(client, "Is quinoa a complete protein?", first["conversation_id"])
    history, _ = generate.calls[-1]
    assert history == []


def test_follow_up_after_decline_stays_declined(client, generate):
    first = post(client, "How many calories should I eat a day?").json()
    body = post(client, "OK, just a rough number then", first["conversation_id"]).json()
    assert body["scope"]["status"] == "declined" and body["scope"]["category"] == "calorie_target"
    assert generate.calls == []


def test_turn_cap(client, generate, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "MAX_USER_TURNS", 2)
    cid = post(client, "q1").json()["conversation_id"]
    assert post(client, "q2", cid).status_code == 200
    r = post(client, "q3", cid)
    assert r.status_code == 422 and r.json()["error"] == "conversation_turn_limit"


def test_get_conversation_ordered(client, generate):
    cid = post(client, "How much protein is in tofu?").json()["conversation_id"]
    post(client, "What should I weigh?", cid)
    r = client.get(f"/api/conversations/{cid}")
    assert r.status_code == 200
    msgs = r.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[1]["scope"]["status"] == "in_scope" and msgs[1]["claims"][0]["source"] is None
    assert msgs[3]["scope"] == {"status": "declined", "category": "weight_target", "stage": "input"}
    assert msgs[0]["claims"] is None


def test_get_unknown_conversation_404(client):
    r = client.get(f"/api/conversations/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["error"] == "conversation_not_found"


def test_rate_limit_returns_json_429(client, generate, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "RATE_LIMIT", "3/minute")
    codes = [post(client, "Is rice healthy?").status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429
    r = post(client, "Is rice healthy?")
    assert r.json()["error"] == "rate_limited"


def test_rate_limit_uses_rightmost_forwarded_ip(monkeypatch):
    from starlette.requests import Request

    from app.config import get_settings
    from app.rate_limit import client_ip

    monkeypatch.setattr(get_settings(), "TRUST_PROXY", True)
    scope = {"type": "http", "headers": [(b"x-forwarded-for", b"6.6.6.6, 1.2.3.4")], "client": ("10.0.0.1", 1)}
    assert client_ip(Request(scope)) == "1.2.3.4"


def test_api_key_never_logged(client, generate, caplog):
    generate.state["next"] = ModelFailure("api_error", "status=401 Invalid API Key gsk_test-not-a-real-key")
    with caplog.at_level(logging.INFO):
        post(client, "Is fish healthy?")
    from app.logging_config import RedactingJsonFormatter

    fmt = RedactingJsonFormatter("%(message)s")
    rendered = "\n".join(fmt.format(r) for r in caplog.records)
    assert "gsk_test-not-a-real-key" not in rendered


def test_provider_rate_limit_is_503_with_retry_after(client, db, generate):
    generate.state["next"] = ModelFailure("rate_limited", "status=429", retry_after=12)
    r = post(client, "Are lentils healthy?")
    assert r.status_code == 503
    assert r.headers["retry-after"] == "12"
    body = r.json()
    assert body["error"] == "upstream_rate_limited" and body["detail"] == "rate_limited"
    failure = db.scalars(select(Failure)).one()  # still recorded, never hidden (Rule 6)
    assert failure.type == "rate_limited" and str(failure.id) == body["failure_id"]


def test_provider_rate_limit_without_header_gets_default_retry_after(client, generate):
    generate.state["next"] = ModelFailure("rate_limited", "status=429")
    r = post(client, "Are lentils healthy?")
    assert r.status_code == 503 and r.headers["retry-after"] == "30"
