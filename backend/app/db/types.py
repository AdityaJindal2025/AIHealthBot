"""Column types that differ between Postgres and SQLite."""

from typing import Any

import numpy as np
from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, TypeDecorator

EMBEDDING_DIMS = 384


class EmbeddingType(TypeDecorator):
    """`vector(384)` on Postgres (pgvector), a JSON list elsewhere (FAP §6.2).

    Values come back as float32 NumPy arrays on both engines.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(EMBEDDING_DIMS))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        values = np.asarray(value, dtype=np.float32)
        if values.shape != (EMBEDDING_DIMS,):
            raise ValueError(f"embedding must have shape ({EMBEDDING_DIMS},), got {values.shape}")
        if dialect.name == "postgresql":
            return values
        return [float(v) for v in values]

    def process_result_value(self, value: Any, dialect: Any) -> np.ndarray | None:
        if value is None:
            return None
        return np.asarray(value, dtype=np.float32)
