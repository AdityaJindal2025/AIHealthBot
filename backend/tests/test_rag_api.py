"""Grounded chat flow end to end (FAP §11.4, Phase 7). FakeEmbedder + fixture index; the model is mocked."""

import json
import re
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.db.models import CitationEvent, Failure, Message, Retrieval, ScopeEvent
from app.llm import client as llm
from app.llm.errors import ModelFailure
from app.rag import retriever as retriever_module
from app.rag.build_index import build_index
from app.rag.chunker import ChunkSettings
from app.rag.embedder import FakeEmbedder
from app.schemas.model_output import GroundedClaim, GroundedOutput

FIXTURE = Path(__file__).parent / "fixtures" / "corpus"
SALT = "Adults should eat less than 5 g of salt a day."
CHILL = "Cool leftovers quickly and put them in the fridge within 2 hours."


@pytest.fixture
def rag(monkeypatch, db):
    settings = get_settings()
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "PROMPT_VERSION", "v2")
    monkeypatch.setattr(settings, "RETRIEVAL_MIN_SCORE", 0.0)
    build_index(db, corpus_dir=FIXTURE, chunk_settings=ChunkSettings(), embedder=FakeEmbedder(),
                allow_unverified=False)
    return settings


def labels(user_turn: str) -> dict[str, str]:
    """Document title per label in the sources block the model receives."""
    return dict(re.findall(r'<source label="(S\d+)" document="([^"]+)"', user_turn))


def label_of(user_turn: str, title: str) -> str:
    return next(lbl for lbl, doc in labels(user_turn).items() if doc == title)


@pytest.fixture
def model(monkeypatch):
    """`state["answer"]` is a function (user_turn) -> GroundedOutput, or an exception to raise."""
    calls: list[tuple] = []
    state: dict = {}

    def fake(history, user_turn):
        calls.append((history, user_turn))
        answer = state["answer"]
        if isinstance(answer, Exception):
            raise answer
        out = answer(user_turn)
        return llm.GroundedResult(output=out, model="openai/gpt-oss-120b", latency_ms=900, input_tokens=2000,
                                  output_tokens=80, raw_text=out.model_dump_json())

    monkeypatch.setattr(llm, "generate_grounded", fake)
    fake.calls = calls
    fake.state = state
    return fake


def covered(*claims):
    return lambda turn: GroundedOutput(coverage="covered", claims=[
        GroundedClaim(text=text, source_label=label_of(turn, title) if not title.startswith("S") else title)
        for text, title in claims])


def count(db, model_, **where):
    stmt = select(func.count()).select_from(model_)
    for k, v in where.items():
        stmt = stmt.where(getattr(model_, k) == v)
    return db.scalar(stmt)


def post(client, message, **extra):
    return client.post("/api/chat", json={"message": message, **extra})


def test_grounded_answer_one_document(client, db, rag, model):
    model.state["answer"] = covered((SALT, "Gamma Salt Guidance"))
    r = post(client, "How much salt should adults eat a day?")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"]["status"] == "in_scope"
    assert body["grounding"]["status"] == "grounded"
    assert len(body["grounding"]["searched"]) == 5
    claim = body["claims"][0]
    assert claim["source"]["document_id"] == "gamma-salt"
    assert claim["source"]["year"] == 2020 and claim["source"]["url"].startswith("https://example.org/gamma-salt")
    label = claim["source"]["label"]
    assert body["answer"] == f"From Gamma Salt Guidance (Gamma Organization, 2020):\n- {SALT} [{label[1:]}]"
    cited = [s for s in body["sources"] if s["cited"]]
    assert [s["label"] for s in cited] == [label]
    assert body["meta"]["prompt_version"] == "v2" and body["meta"]["claims_dropped"] == 0
    assert body["meta"]["corpus_version"]
    assert count(db, Message) == 2 and count(db, Retrieval) == 1
    retrieval = db.scalars(select(Retrieval)).one()
    assert retrieval.message_id is not None and retrieval.failure_id is None
    assert any(r["cited"] for r in retrieval.results)
    # The model saw labelled sources and the question.
    assert "<question>How much salt should adults eat a day?</question>" in model.calls[0][1]


def test_cross_document_answer_is_split_per_document(client, rag, model):
    model.state["answer"] = covered((SALT, "Gamma Salt Guidance"), (CHILL, "Delta Chilling Advice"))
    body = post(client, "salt a day and cool leftovers in the fridge").json()
    assert body["answer"].startswith("These documents each address this:\n\n")
    assert "Gamma Salt Guidance (Gamma Organization, 2020):" in body["answer"]
    assert "Delta Chilling Advice (Delta Standards Agency, 2020):" in body["answer"]
    assert {c["source"]["document_id"] for c in body["claims"]} == {"gamma-salt", "delta-chill"}


def test_input_guard_decline_skips_retrieval(client, db, rag, model):
    body = post(client, "What should I weigh?").json()
    assert body["scope"] == {"status": "declined", "category": "weight_target", "stage": "input"}
    assert body["grounding"] is None and body["sources"] == []
    assert model.calls == [] and count(db, Retrieval) == 0


def test_restricted_top_hit_declines_without_model(client, db, rag, model):
    body = post(client, "daily energy requirements kcal age", document_id="beta-diet").json()
    assert body["scope"] == {"status": "declined", "category": "calorie_target", "stage": "retrieval"}
    assert body["sources"] == [] and body["claims"] == []
    assert model.calls == []
    event = db.scalars(select(ScopeEvent)).one()
    assert (event.stage, event.rule_id) == ("retrieval", "RET-CAL-01")
    assert count(db, Retrieval) == 1


def test_below_floor_is_not_covered_without_model(client, db, rag, model, monkeypatch):
    monkeypatch.setattr(rag, "RETRIEVAL_MIN_SCORE", 1.01)
    body = post(client, "Is intermittent fasting healthy?").json()
    assert body["scope"]["status"] == "in_scope"
    assert body["grounding"]["status"] == "not_covered"
    assert len(body["grounding"]["searched"]) == 5
    assert body["answer"].startswith("The guidance I searched doesn't cover this. I searched: ")
    assert body["claims"] == [] and all(not s["cited"] for s in body["sources"])
    assert model.calls == [] and count(db, Retrieval) == 1


def test_floor_does_not_apply_to_filtered_requests(client, rag, model, monkeypatch):
    monkeypatch.setattr(rag, "RETRIEVAL_MIN_SCORE", 1.01)
    model.state["answer"] = covered((SALT, "Gamma Salt Guidance"))
    body = post(client, "salt", document_id="gamma-salt").json()
    assert body["grounding"]["status"] == "grounded" and len(model.calls) == 1


def test_model_not_covered(client, db, rag, model):
    model.state["answer"] = lambda turn: GroundedOutput(coverage="not_covered", claims=[])
    body = post(client, "How much salt should adults eat a day?").json()
    assert body["grounding"]["status"] == "not_covered"
    assert body["meta"]["model"] == "openai/gpt-oss-120b"
    assert count(db, Retrieval) == 1


def test_unknown_label_dropped_and_recorded(client, db, rag, model):
    model.state["answer"] = covered((SALT, "Gamma Salt Guidance"), ("Salt is bad.", "S9"))
    body = post(client, "How much salt should adults eat a day?").json()
    assert len(body["claims"]) == 1 and body["meta"]["claims_dropped"] == 1
    event = db.scalars(select(CitationEvent)).one()
    assert (event.reason, event.source_label, event.chunk_id) == ("unknown_label", "S9", None)
    assert event.message_id is not None


def test_every_claim_dropped_is_a_502(client, db, rag, model):
    model.state["answer"] = covered(("Salt should be under 6 g a day.", "Gamma Salt Guidance"))
    r = post(client, "How much salt should adults eat a day?")
    assert r.status_code == 502
    body = r.json()
    assert body["error"] == "model_output_invalid" and body["detail"] == "no_valid_claims"
    failure = db.scalars(select(Failure)).one()
    assert failure.type == "no_valid_claims" and str(failure.id) == body["failure_id"]
    retrieval = db.scalars(select(Retrieval)).one()
    assert retrieval.failure_id == failure.id and retrieval.message_id is None
    event = db.scalars(select(CitationEvent)).one()
    assert event.failure_id == failure.id and event.reason == "unsupported_number"
    assert count(db, Message) == 1  # the user message only


def test_output_guard_catches_composed_text(client, db, rag, model, monkeypatch):
    # A claim that passes the citation checks but leaks a personal target is still caught.
    monkeypatch.setattr("app.services.chat_service.check_claims", _pass_everything)
    model.state["answer"] = covered(("Adults should aim for 1,500 calories a day.", "Gamma Salt Guidance"))
    body = post(client, "How much salt should adults eat a day?").json()
    assert body["scope"] == {"status": "declined", "category": "calorie_target", "stage": "output"}
    event = db.scalars(select(ScopeEvent)).one()
    assert event.stage == "output" and "1,500 calories" in event.raw_output


def _pass_everything(output, label_map, publishers):
    from app.rag.citations import CitationResult, ValidClaim, to_source

    return CitationResult([ValidClaim(c, label_map[c.source_label], to_source(label_map[c.source_label]))
                           for c in output.claims], [])


def test_model_failure_is_a_502_with_retrieval_kept(client, db, rag, model):
    model.state["answer"] = ModelFailure("schema_invalid", "bad json", "{oops", model="m", latency_ms=5)
    r = post(client, "How much salt should adults eat a day?")
    assert r.status_code == 502
    failure = db.scalars(select(Failure)).one()
    assert (failure.type, failure.raw_output) == ("schema_invalid", "{oops")
    assert db.scalars(select(Retrieval)).one().failure_id == failure.id


def test_embedding_error_is_a_502(client, db, rag, model, monkeypatch):
    class Broken:
        def embed_query(self, text):
            raise RuntimeError("model missing")

    monkeypatch.setattr(retriever_module, "get_embedder", lambda: Broken())
    r = post(client, "salt")
    assert r.status_code == 502
    assert r.json()["error"] == "retrieval_failed" and r.json()["detail"] == "embedding_error"
    assert db.scalars(select(Failure)).one().type == "embedding_error"
    assert model.calls == []


def test_unknown_document_is_422_and_writes_nothing(client, db, rag, model):
    r = post(client, "salt", document_id="no-such-doc")
    assert r.status_code == 422 and r.json()["error"] == "unknown_document"
    assert count(db, Message) == 0


def test_filtered_request_cites_only_that_document(client, rag, model):
    model.state["answer"] = lambda turn: GroundedOutput(coverage="covered", claims=[
        GroundedClaim(text="Freeze food at -18°C or below.", source_label=lbl) for lbl in list(labels(turn))[:1]])
    body = post(client, "freezer temperature", document_id="alpha-safety").json()
    assert body["grounding"]["filter_document_id"] == "alpha-safety"
    assert [s["document_id"] for s in body["grounding"]["searched"]] == ["alpha-safety"]
    assert {s["document_id"] for s in body["sources"]} == {"alpha-safety"}


def test_filtered_not_covered_names_only_that_document(client, rag, model):
    model.state["answer"] = lambda turn: GroundedOutput(coverage="not_covered", claims=[])
    body = post(client, "intermittent fasting", document_id="delta-chill").json()
    assert body["answer"] == ("The guidance I searched doesn't cover this. I searched only Delta Chilling Advice "
                              "(Delta Standards Agency, 2020), as you asked.")


def test_index_not_built_is_503_and_writes_nothing(client, db, monkeypatch, model):
    settings = get_settings()
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    monkeypatch.setattr(settings, "PROMPT_VERSION", "v2")
    r = post(client, "salt")
    assert r.status_code == 503 and r.json()["error"] == "index_not_ready"
    assert count(db, Message) == 0


def test_m1_mode_envelope_has_no_m2_fields(client, monkeypatch):
    from app.schemas.model_output import AssistantOutput, Claim

    monkeypatch.setattr(llm, "generate", lambda history, message: llm.GenerationResult(
        output=AssistantOutput(answer="Lentils are high in fibre.", claims=[Claim(text="Lentils are high in fibre.")]),
        model="m", latency_ms=1, input_tokens=1, output_tokens=1))
    body = post(client, "Are lentils healthy?").json()
    assert set(body) == {"conversation_id", "message_id", "answer", "claims", "scope", "meta"}
    assert set(body["meta"]) == {"prompt_version", "model", "latency_ms"}
    assert body["claims"] == [{"text": "Lentils are high in fibre.", "source": None}]


def test_m1_mode_rejects_document_filter(client, db):
    r = post(client, "salt", document_id="gamma-salt")
    assert r.status_code == 422


def test_follow_up_passes_history_and_previous_question(client, rag, model):
    model.state["answer"] = covered((SALT, "Gamma Salt Guidance"))
    first = post(client, "How much salt should adults eat a day?").json()
    post(client, "what about children?", conversation_id=first["conversation_id"])
    history, turn = model.calls[1]
    assert [t.role for t in history] == ["user", "assistant"]
    assert history[1].content == first["answer"]


def test_conversation_history_includes_grounding_and_sources(client, rag, model):
    model.state["answer"] = covered((SALT, "Gamma Salt Guidance"))
    first = post(client, "How much salt should adults eat a day?").json()
    history = client.get(f"/api/conversations/{first['conversation_id']}").json()
    assistant = history["messages"][1]
    assert assistant["grounding"]["status"] == "grounded"
    assert assistant["sources"] == first["sources"]
    assert assistant["claims"] == first["claims"]


def test_documents_endpoint(client, rag):
    docs = client.get("/api/documents").json()["documents"]
    assert [d["document_id"] for d in docs] == ["alpha-safety", "beta-diet", "delta-chill", "epsilon-fats",
                                                "gamma-salt"]
    assert all(d["chunk_count"] > 0 for d in docs)
    assert docs[0]["publisher_short"] == "AFA"


def test_health_reports_index(client, db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    r = client.get("/api/health")
    assert r.status_code == 503 and r.json()["index"]["status"] == "missing"
    # Build the real-corpus index with the fake embedder: the version matches the current settings.
    build_index(db, corpus_dir=settings.CORPUS_DIR, chunk_settings=ChunkSettings.from_settings(settings),
                embedder=FakeEmbedder(), allow_unverified=True)
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["index"]["status"] == "ready" and body["index"]["chunks"] == 209


def test_check_mode_refuses_mismatch(monkeypatch):
    from app.config import check_mode

    settings = get_settings()
    monkeypatch.setattr(settings, "RAG_ENABLED", True)
    with pytest.raises(RuntimeError, match="v2 or later"):
        check_mode(settings)
    monkeypatch.setattr(settings, "RAG_ENABLED", False)
    monkeypatch.setattr(settings, "PROMPT_VERSION", "v2")
    with pytest.raises(RuntimeError, match="needs PROMPT_VERSION v1"):
        check_mode(settings)


def test_grounding_survives_as_json(db, client, rag, model):
    model.state["answer"] = covered((SALT, "Gamma Salt Guidance"))
    post(client, "How much salt should adults eat a day?")
    stored = db.scalars(select(Message).where(Message.role == "assistant")).one()
    assert json.loads(json.dumps(stored.grounding))["status"] == "grounded"


def test_provider_rate_limit_in_grounded_mode_is_503(client, db, rag, model):
    model.state["answer"] = ModelFailure("rate_limited", "status=429", retry_after=20)
    r = post(client, "How much salt should adults eat a day?")
    assert r.status_code == 503 and r.headers["retry-after"] == "20"
    assert r.json()["error"] == "upstream_rate_limited"
    failure = db.scalars(select(Failure)).one()
    assert failure.type == "rate_limited"
    assert db.scalars(select(Retrieval)).one().failure_id == failure.id
