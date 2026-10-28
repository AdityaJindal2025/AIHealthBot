"""Application settings, read from environment variables (AP §5.4)."""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/corpus, wherever the app is run from (/app/corpus in the Docker image).
DEFAULT_CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    GROQ_API_KEY: str = ""
    # Must be a Groq model that supports strict structured outputs.
    MODEL_ID: str = "openai/gpt-oss-120b"
    # v1 answers from model memory (M1); v2+ answers only from retrieved chunks (M2).
    PROMPT_VERSION: str = "v2"
    # Grounded answers (M2). False restores the M1 path exactly, with no redeploy (FAP §11.4).
    # Must match PROMPT_VERSION: see check_mode() (adjustment A6).
    RAG_ENABLED: bool = True
    DATABASE_URL: str = "sqlite:///./dev.db"
    # Comma-separated list of exact origins. Never "*" (EC SEC-06).
    CORS_ORIGINS: str = "http://localhost:3000"
    RATE_LIMIT: str = "20/minute"
    # When true, the client IP is the right-most X-Forwarded-For entry (added by
    # Railway's proxy), not the proxy's own address (EC OPS-01, OPS-02).
    TRUST_PROXY: bool = False
    LOG_LEVEL: str = "INFO"

    MAX_MESSAGE_CHARS: int = 2000
    MAX_USER_TURNS: int = 50
    HISTORY_TURNS: int = 10

    # Milestone 2 corpus (FAP §4). Unverified registry entries are for local development only.
    CORPUS_DIR: str = str(DEFAULT_CORPUS_DIR)
    ALLOW_UNVERIFIED_REGISTRY: bool = False

    # Chunking (FAP §5.2). Token counts use the embedder's tokenizer and include the context header.
    CHUNK_TARGET_TOKENS: int = 350
    CHUNK_MAX_TOKENS: int = 480
    CHUNK_MIN_TOKENS: int = 60

    # Embeddings (FAP §6.1). "fake" selects the deterministic test embedder.
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # Retrieval (FAP §7.1). k, the per-document cap and the score floor come from calibration run
    # evals/retrieval_runs/20261026T035839Z (bge-small-en-v1.5); see README "Retrieval parameters".
    RETRIEVAL_CANDIDATES: int = 20
    RETRIEVAL_K: int = 6
    RETRIEVAL_MAX_PER_DOC: int = 2
    # Cosine floor for "not covered", applied in all-documents mode only. Calibrated for the bge
    # model; it must be re-calibrated if EMBEDDING_MODEL changes.
    RETRIEVAL_MIN_SCORE: float = 0.73

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        return normalise_database_url(v)

    @property
    def cors_origins(self) -> list[str]:
        # Strip trailing slashes so "https://x.vercel.app/" matches the browser's Origin (EC OPS-04).
        return [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()]


def check_mode(settings: "Settings") -> None:
    """Refuse to boot when the answer mode and the prompt disagree (adjustment A6).

    The v1 prompt asks for `source: null`; v2+ expects labelled sources. Running either with the
    wrong path would fail every request, so it fails at startup instead.
    """
    version = int(settings.PROMPT_VERSION.removeprefix("v")) if settings.PROMPT_VERSION[1:].isdigit() else 0
    if settings.RAG_ENABLED and version < 2:
        raise RuntimeError(f"RAG_ENABLED=true needs PROMPT_VERSION v2 or later, got {settings.PROMPT_VERSION}")
    if not settings.RAG_ENABLED and version != 1:
        raise RuntimeError(f"RAG_ENABLED=false needs PROMPT_VERSION v1, got {settings.PROMPT_VERSION}")


def normalise_database_url(url: str) -> str:
    """Railway provides postgres:// or postgresql://. Both must use the psycopg (v3) driver (EC DB-01)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
