"""Application settings, read from environment variables (AP §5.4)."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ANTHROPIC_API_KEY: str = ""
    MODEL_ID: str = "claude-opus-5"
    PROMPT_VERSION: str = "v1"
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

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        return normalise_database_url(v)

    @property
    def cors_origins(self) -> list[str]:
        # Strip trailing slashes so "https://x.vercel.app/" matches the browser's Origin (EC OPS-04).
        return [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()]


def normalise_database_url(url: str) -> str:
    """Railway provides postgres:// or postgresql://. Both must use the psycopg (v3) driver (EC DB-01)."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
