import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import func, select

from app.db import repo
from app.db.models import Document, IndexedChunk, IndexMeta
from app.rag import build_index as build_module
from app.rag.build_index import BuildError, build_index, compute_corpus_version
from app.rag.chunker import ChunkSettings
from app.rag.corpus import CorpusError
from app.rag.embedder import FakeEmbedder

FIXTURE = Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture
def corpus_dir(tmp_path):
    target = tmp_path / "corpus"
    shutil.copytree(FIXTURE, target)
    return target


def _build(db, corpus_dir, **kw):
    kw.setdefault("chunk_settings", ChunkSettings())
    kw.setdefault("embedder", FakeEmbedder())
    kw.setdefault("allow_unverified", False)
    return build_index(db, corpus_dir=corpus_dir, **kw)


def test_first_build_writes_documents_chunks_and_meta(db, corpus_dir):
    result = _build(db, corpus_dir)
    assert result.built
    meta = repo.get_index_meta(db)
    assert meta.corpus_version == result.corpus_version
    assert meta.chunk_count == result.chunk_count == db.scalar(select(func.count()).select_from(IndexedChunk))
    assert meta.embedding_model == "fake" and meta.dims == 384
    assert meta.chunker_settings["max_tokens"] == 480
    docs = repo.list_documents(db)
    assert [d.document_id for d, _ in docs] == ["alpha-safety", "beta-diet", "delta-chill", "epsilon-fats",
                                                "gamma-salt"]
    assert sum(n for _, n in docs) == result.chunk_count

    chunk = db.get(IndexedChunk, "alpha-safety#0003-0006")
    assert chunk.kind == "list" and chunk.section == "Fridge"
    assert isinstance(chunk.embedding, np.ndarray) and chunk.embedding.shape == (384,)
    assert chunk.document.publisher == "Alpha Food Agency"


def test_restricted_chunks_are_stored_with_their_rule(db, corpus_dir):
    _build(db, corpus_dir)
    tagged = db.scalars(select(IndexedChunk).where(IndexedChunk.restricted_category.is_not(None))).all()
    assert [(c.document_id, c.restricted_category, c.restricted_rule_id) for c in tagged] == [
        ("beta-diet", "calorie_target", "RET-CAL-01"),
    ]


def test_if_changed_skips_a_current_index(db, corpus_dir):
    first = _build(db, corpus_dir)
    second = _build(db, corpus_dir, if_changed=True)
    assert not second.built
    assert second.corpus_version == first.corpus_version


def test_changing_a_setting_or_the_corpus_rebuilds(db, corpus_dir):
    first = _build(db, corpus_dir)
    changed = _build(db, corpus_dir, chunk_settings=ChunkSettings(target_tokens=300), if_changed=True)
    assert changed.built and changed.corpus_version != first.corpus_version

    blocks = (corpus_dir / "blocks.jsonl").read_text().replace("Cook poultry", "Always cook poultry")
    (corpus_dir / "blocks.jsonl").write_text(blocks)
    again = _build(db, corpus_dir, chunk_settings=ChunkSettings(target_tokens=300), if_changed=True)
    assert again.built and again.corpus_version != changed.corpus_version
    assert db.scalar(select(func.count()).select_from(IndexMeta)) == 1


def test_version_depends_on_embedding_model(corpus_dir):
    class Other(FakeEmbedder):
        model_id = "other-model"

    s = ChunkSettings()
    assert compute_corpus_version(corpus_dir, s, FakeEmbedder()) != compute_corpus_version(corpus_dir, s, Other())


def test_removed_document_is_deleted(db, corpus_dir):
    _build(db, corpus_dir)
    # Swap gamma-salt for a new document, keeping 5 documents.
    blocks = (corpus_dir / "blocks.jsonl").read_text().replace('"gamma-salt"', '"zeta-salt"')
    (corpus_dir / "blocks.jsonl").write_text(blocks)
    entries = json.loads((corpus_dir / "documents.json").read_text())
    for e in entries:
        if e["document_id"] == "gamma-salt":
            e["document_id"] = "zeta-salt"
    (corpus_dir / "documents.json").write_text(json.dumps(entries))
    _build(db, corpus_dir)
    assert db.get(Document, "gamma-salt") is None
    assert db.get(Document, "zeta-salt") is not None


def test_failure_mid_build_leaves_previous_index(db, corpus_dir, monkeypatch):
    first = _build(db, corpus_dir)
    count = first.chunk_count

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(build_module, "_index_meta", boom)  # fails after the old chunks were deleted
    with pytest.raises(RuntimeError, match="disk full"):
        _build(db, corpus_dir, chunk_settings=ChunkSettings(target_tokens=300))
    assert repo.get_index_meta(db).corpus_version == first.corpus_version
    assert db.scalar(select(func.count()).select_from(IndexedChunk)) == count


def test_wrong_embedding_shape_fails_before_any_write(db, corpus_dir):
    class Broken(FakeEmbedder):
        model_id = "broken"

        def embed_documents(self, texts):
            return np.zeros((len(texts), 10), np.float32)

    with pytest.raises(BuildError, match="shape"):
        _build(db, corpus_dir, embedder=Broken())
    assert repo.get_index_meta(db) is None


def test_unverified_registry_refused_in_production_mode(db, corpus_dir):
    entries = json.loads((corpus_dir / "documents.json").read_text())
    entries[0]["verified_by"] = ""
    (corpus_dir / "documents.json").write_text(json.dumps(entries))
    with pytest.raises(CorpusError):
        _build(db, corpus_dir)
    assert repo.get_index_meta(db) is None
    _build(db, corpus_dir, allow_unverified=True)  # local development


def test_cli_builds_then_skips(monkeypatch, capsys):
    # The CLI uses the app's own settings and session (in-memory SQLite and the fake embedder in tests).
    assert build_module.main(["--if-changed"]) == 0
    assert "built index" in capsys.readouterr().out
    assert build_module.main(["--if-changed"]) == 0
    assert "nothing to do" in capsys.readouterr().out
