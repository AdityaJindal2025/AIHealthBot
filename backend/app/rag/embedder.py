"""Text embeddings (FAP §6.1).

`BgeEmbedder` runs `BAAI/bge-small-en-v1.5` locally through sentence-transformers. It is
imported lazily: torch is only installed with the `embed` extra (Docker image and the
retrieval-eval CI job), so unit tests and the API test suite run without it, using
`FakeEmbedder`.

Every vector is L2-normalised float32, so cosine similarity is a dot product.
"""

import hashlib
import re
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.config import get_settings

EMBEDDING_DIMS = 384
BGE_MODEL_ID = "BAAI/bge-small-en-v1.5"
# BGE's retrieval instruction: added to queries only, never to documents.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class EmbedderUnavailable(RuntimeError):
    pass


class Embedder(Protocol):
    model_id: str
    dims: int

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...

    def embed_query(self, text: str) -> np.ndarray: ...


def _normalise(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return matrix / np.where(norms == 0, 1, norms)


class BgeEmbedder:
    dims = EMBEDDING_DIMS

    def __init__(self, model_id: str = BGE_MODEL_ID) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise EmbedderUnavailable(
                "sentence-transformers is not installed: install the backend with the `embed` extra "
                "(pip install '.[embed]'), or set EMBEDDING_MODEL=fake for tests"
            ) from e
        self.model_id = model_id
        self._model = SentenceTransformer(model_id, device="cpu")
        self._model.max_seq_length = 512
        model = self._model
        dims = (getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension)()
        if dims != EMBEDDING_DIMS:
            raise EmbedderUnavailable(f"{model_id} has {dims} dimensions; the index column has {EMBEDDING_DIMS}")

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        vectors = self._model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        return _normalise(vectors)

    def embed_query(self, text: str) -> np.ndarray:
        vector = self._model.encode([BGE_QUERY_INSTRUCTION + text], normalize_embeddings=True,
                                    show_progress_bar=False)
        return _normalise(vector)[0]


class FakeEmbedder:
    """Deterministic hashed bag-of-words. Shared words give a positive similarity, which is
    enough to test ranking, filters and caps without downloading a model."""

    model_id = "fake"
    dims = EMBEDDING_DIMS

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dims, dtype=np.float32)
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            digest = hashlib.sha256(word.encode()).digest()
            index = int.from_bytes(digest[:4], "little") % self.dims
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        if not vector.any():
            vector[0] = 1.0
        return _normalise(vector)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return np.stack([self._vector(t) for t in texts]) if texts else np.zeros((0, self.dims), np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self._vector(text)


@lru_cache
def get_embedder(model_id: str | None = None) -> Embedder:
    model_id = model_id or get_settings().EMBEDDING_MODEL
    if model_id == "fake":
        return FakeEmbedder()
    return BgeEmbedder(model_id)
