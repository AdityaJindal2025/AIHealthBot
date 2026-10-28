import os

# Settings are read at import time, so the test environment is set before any app import.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["GROQ_API_KEY"] = "gsk_test-not-a-real-key"
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
# The M1 suite runs the M1 path; grounded tests switch it on with the `rag` fixture.
os.environ["PROMPT_VERSION"] = "v1"
os.environ["RAG_ENABLED"] = "false"
os.environ["MODEL_ID"] = "openai/gpt-oss-120b"
# Milestone 2: tests never download a model and may use the unverified dev registry.
os.environ["EMBEDDING_MODEL"] = "fake"
os.environ["ALLOW_UNVERIFIED_REGISTRY"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db.models import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.rag.store import invalidate_memory_cache  # noqa: E402
from app.rate_limit import limiter  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    limiter.reset()
    invalidate_memory_cache()
    yield


@pytest.fixture
def db():
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c
