import json
from pathlib import Path

import pytest

from app.config import DEFAULT_CORPUS_DIR
from app.rag.build_index import build_index
from app.rag.chunker import ChunkSettings
from app.rag.corpus import load_corpus
from app.rag.embedder import FakeEmbedder
from app.rag.retriever import retrieve
from app.rag.themes import Theme, ThemeError, load_themes

FIXTURE = Path(__file__).parent / "fixtures" / "corpus"
FIXTURE_DOCS = {"alpha-safety", "beta-diet", "delta-chill", "epsilon-fats", "gamma-salt"}


def test_real_themes_are_valid_and_cover_every_document():
    registry = set(load_corpus(DEFAULT_CORPUS_DIR, allow_unverified=False).documents)
    themes = load_themes(DEFAULT_CORPUS_DIR, registry)
    assert len(themes) == 5
    assert {d for t in themes for d in t.document_ids} == registry
    # Two themes over the same documents would search identically.
    assert len({frozenset(t.document_ids) for t in themes}) == 5


def test_fixture_themes_load():
    themes = load_themes(FIXTURE, FIXTURE_DOCS)
    assert [t.theme_id for t in themes] == ["safety", "diet"]
    assert themes[0].document_ids == ("alpha-safety", "delta-chill")


def test_missing_file_means_no_themes(tmp_path):
    assert load_themes(tmp_path, FIXTURE_DOCS) == []


def _write(tmp_path, entries):
    (tmp_path / "themes.json").write_text(json.dumps(entries))
    return tmp_path


@pytest.mark.parametrize("entries, message", [
    ([{"theme_id": "a", "name": "A", "description": "", "document_ids": ["nope"]}], "unknown document_ids ['nope']"),
    ([{"theme_id": "a", "name": "A", "description": "", "document_ids": []}], "non-empty list"),
    ([{"theme_id": "A b", "name": "A", "description": "", "document_ids": ["beta-diet"]}], "lowercase-hyphenated"),
    ([{"theme_id": "a", "name": "A", "description": "", "document_ids": ["beta-diet"]}] * 2, "duplicate theme_id"),
    ([{"theme_id": "a", "name": "A", "document_ids": ["beta-diet"]}], "needs exactly the fields"),
    ([{"theme_id": "a", "name": " ", "description": "", "document_ids": ["beta-diet"]}], "name is empty"),
])
def test_invalid_themes_are_refused(tmp_path, entries, message):
    with pytest.raises(ThemeError) as err:
        load_themes(_write(tmp_path, entries), FIXTURE_DOCS)
    assert any(message in p for p in err.value.problems)


def test_invalid_json_is_refused(tmp_path):
    (tmp_path / "themes.json").write_text("{not json")
    with pytest.raises(ThemeError):
        load_themes(tmp_path, FIXTURE_DOCS)


@pytest.fixture
def indexed(db):
    build_index(db, corpus_dir=FIXTURE, chunk_settings=ChunkSettings(target_tokens=40, min_tokens=10),
                embedder=FakeEmbedder(), allow_unverified=False)
    return db


def test_theme_mode_searches_only_the_theme_documents(indexed):
    theme = Theme("safety", "Food safety", "", ("alpha-safety", "delta-chill"))
    result = retrieve(indexed, "fridge freezer food store cook salt", k=6, max_per_doc=2, theme=theme)
    assert result.mode == "theme" and result.theme_id == "safety" and result.filter_document_id is None
    assert result.hits and {h.document_id for h in result.hits} <= {"alpha-safety", "delta-chill"}
    # Two documents, k=6: the per-document cap rises to 3 so the slots can still fill.
    counts: dict[str, int] = {}
    for h in result.hits:
        counts[h.document_id] = counts.get(h.document_id, 0) + 1
    assert max(counts.values()) <= 3


def test_theme_ignores_a_document_named_in_the_message(indexed):
    theme = Theme("diet", "Diet", "", ("beta-diet", "gamma-salt"))
    result = retrieve(indexed, "What does the alpha guide say about salt?", theme=theme)
    assert result.mode == "theme"
    assert {h.document_id for h in result.hits} <= {"beta-diet", "gamma-salt"}


def test_explicit_document_wins_over_theme(indexed):
    theme = Theme("diet", "Diet", "", ("beta-diet", "gamma-salt"))
    result = retrieve(indexed, "salt", document_id="alpha-safety", theme=theme)
    assert result.mode == "filtered" and result.theme_id is None
    assert {h.document_id for h in result.hits} == {"alpha-safety"}
