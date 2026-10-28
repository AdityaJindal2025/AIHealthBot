import sys

import numpy as np
import pytest

from app.rag.embedder import EMBEDDING_DIMS, BgeEmbedder, EmbedderUnavailable, FakeEmbedder, get_embedder


def test_fake_embedder_is_deterministic_and_normalised():
    e = FakeEmbedder()
    a = e.embed_documents(["Keep your fridge at 5°C", "Salt intake"])
    b = e.embed_documents(["Keep your fridge at 5°C", "Salt intake"])
    assert a.shape == (2, EMBEDDING_DIMS) and a.dtype == np.float32
    assert np.array_equal(a, b)
    assert np.allclose(np.linalg.norm(a, axis=1), 1.0)
    assert np.allclose(np.linalg.norm(e.embed_query("anything")), 1.0)


def test_fake_embedder_ranks_shared_words_higher():
    e = FakeEmbedder()
    q = e.embed_query("fridge temperature")
    docs = e.embed_documents(["the fridge temperature should be low", "eat more whole grains"])
    assert docs[0] @ q > docs[1] @ q


def test_fake_embedder_handles_empty_input():
    e = FakeEmbedder()
    assert e.embed_documents([]).shape == (0, EMBEDDING_DIMS)
    assert np.allclose(np.linalg.norm(e.embed_query("°!")), 1.0)


def test_bge_embedder_without_extra_gives_a_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)  # makes the import fail
    with pytest.raises(EmbedderUnavailable, match=r"embed` extra"):
        BgeEmbedder()


def test_get_embedder_uses_setting():
    # conftest sets EMBEDDING_MODEL=fake
    assert get_embedder().model_id == "fake"
