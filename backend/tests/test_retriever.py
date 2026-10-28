from pathlib import Path

import pytest
from sqlalchemy import update

from app.db.models import Document, IndexedChunk
from app.rag import retriever as retriever_module
from app.rag.build_index import build_index
from app.rag.chunker import ChunkSettings
from app.rag.embedder import FakeEmbedder
from app.rag.retriever import RetrievalError, build_query, detect_document, retrieve

FIXTURE = Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture
def indexed(db):
    build_index(db, corpus_dir=FIXTURE, chunk_settings=ChunkSettings(target_tokens=40, min_tokens=10),
                embedder=FakeEmbedder(), allow_unverified=False)
    return db


def _doc(doc_id, aliases):
    return Document(document_id=doc_id, title=doc_id, publisher="p", publisher_short="p", aliases=aliases,
                    publisher_aliases=[])


DOCS = [_doc("eatwell-guide", ["eatwell guide", "eatwell"]), _doc("fsa-chill", ["fsa chill guidance"]),
        _doc("who-healthy-diet", ["who healthy diet", "healthy diet fact sheet"])]


@pytest.mark.parametrize("message, expected", [
    ("According to the Eatwell Guide, how much salt?", "eatwell-guide"),
    ("what does eatwell say", "eatwell-guide"),
    ("Compare the Eatwell Guide and the healthy diet fact sheet on sugar", None),
    ("How much salt should I eat?", None),
    ("Is sweatwell a word?", None),  # word boundaries
])
def test_detect_document(message, expected):
    assert detect_document(message, DOCS) == expected


PROTEIN = "How much protein do adults need?"
RICE = "How long can cooked rice be kept in the fridge?"


@pytest.mark.parametrize("message, previous, expected", [
    ("what about for vegans?", PROTEIN, f"{PROTEIN} what about for vegans?"),
    ("And for children?", "How much salt should adults eat?", "How much salt should adults eat? And for children?"),
    (RICE, "Something else", RICE),
    ("what about for vegans?", None, "what about for vegans?"),
])
def test_build_query(message, previous, expected):
    assert build_query(message, previous) == expected


def test_all_documents_mode_caps_each_document(indexed):
    result = retrieve(indexed, "fridge freezer food store cook", k=6, max_per_doc=2)
    assert result.mode == "all" and result.filter_document_id is None
    counts: dict[str, int] = {}
    for h in result.hits:
        counts[h.document_id] = counts.get(h.document_id, 0) + 1
    assert max(counts.values()) <= 2
    assert [h.label for h in result.hits] == [f"S{i}" for i in range(1, len(result.hits) + 1)]
    assert result.top_score is not None and result.corpus_version


def test_filtered_mode_returns_only_that_document_without_cap(indexed):
    result = retrieve(indexed, "fridge freezer food", document_id="alpha-safety", k=6, max_per_doc=1)
    assert result.mode == "filtered" and result.filter_source == "explicit"
    assert result.hits and {h.document_id for h in result.hits} == {"alpha-safety"}
    assert len(result.hits) > 1  # the cap does not apply


def test_alias_in_message_filters(indexed):
    result = retrieve(indexed, "What does the alpha guide say about the fridge?")
    assert result.filter_document_id == "alpha-safety" and result.filter_source == "detected"


def test_two_aliases_do_not_filter(indexed):
    result = retrieve(indexed, "Compare the alpha guide and the beta guide")
    assert result.mode == "all"


def test_explicit_document_wins_over_alias(indexed):
    result = retrieve(indexed, "What does the alpha guide say?", document_id="gamma-salt")
    assert result.filter_document_id == "gamma-salt"
    assert {h.document_id for h in result.hits} == {"gamma-salt"}


def test_follow_up_query_includes_previous_message(indexed):
    result = retrieve(indexed, "what about for vegans?", previous_user_message="How much salt a day?")
    assert result.query_text == "How much salt a day? what about for vegans?"


def test_restricted_top_hit_is_flagged(indexed):
    result = retrieve(indexed, "daily energy requirements kcal age", document_id="beta-diet")
    assert result.restricted_top == "calorie_target"
    assert result.restricted_top_rule_id == "RET-CAL-01"
    assert all(h.restricted_category is None for h in result.hits)


def test_lower_restricted_hit_is_withheld_and_labels_stay_contiguous(indexed):
    # "energy" ranks the restricted beta chunk below the sugar chunk for this query.
    result = retrieve(indexed, "free sugars total energy intake adults", document_id="beta-diet", k=6)
    assert result.restricted_top is None
    assert [w.chunk_id for w in result.withheld] and all(w.restricted_category for w in result.withheld)
    assert all(h.restricted_category is None for h in result.hits)
    assert [h.label for h in result.hits] == [f"S{i}" for i in range(1, len(result.hits) + 1)]


def test_snapshot_carries_registry_metadata(indexed):
    hit = retrieve(indexed, "salt", document_id="gamma-salt").hits[0]
    assert (hit.document_name, hit.publisher, hit.year, hit.url) == (
        "Gamma Salt Guidance", "Gamma Organization", 2020, "https://example.org/gamma-salt")
    assert hit.to_dict()["section_path"] == ["Salt"]


def test_store_error_becomes_retrieval_error(indexed, monkeypatch):
    class Broken:
        def search(self, *a, **kw):
            raise RuntimeError("connection lost")

    monkeypatch.setattr(retriever_module, "get_store", lambda db: Broken())
    with pytest.raises(RetrievalError) as err:
        retrieve(indexed, "salt")
    assert err.value.type == "retrieval_error"


def test_embedding_error_becomes_retrieval_error(indexed, monkeypatch):
    class Broken:
        def embed_query(self, text):
            raise RuntimeError("model missing")

    monkeypatch.setattr(retriever_module, "get_embedder", lambda: Broken())
    with pytest.raises(RetrievalError) as err:
        retrieve(indexed, "salt")
    assert err.value.type == "embedding_error"


def test_withheld_only_counts_chunks_that_outranked_the_last_hit(indexed):
    # Mark every chunk restricted except gamma's: nothing is shown but gamma, and restricted chunks
    # ranked below a full result set are not reported as withheld.
    indexed.execute(update(IndexedChunk).where(IndexedChunk.document_id != "gamma-salt")
                    .values(restricted_category="calorie_target", restricted_rule_id="RET-CAL-01"))
    indexed.commit()
    result = retrieve(indexed, "salt adults", k=1)
    assert [h.document_id for h in result.hits] == ["gamma-salt"]
    assert all(w.rank < result.hits[0].rank for w in result.withheld)
