"""App factory: CORS, logging, request IDs, error shapes, routers under /api."""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import chat, conversations, documents, health
from app.config import check_mode, get_settings
from app.llm.prompts import load_system_prompt
from app.logging_config import configure_logging, request_id_var
from app.rate_limit import limiter
from app.services.chat_service import ChatError

log = logging.getLogger("app")


def _error(status_code: int, error: str, *, failure_id: uuid.UUID | None = None, detail: str | None = None,
           headers: dict[str, str] | None = None) -> JSONResponse:
    body = {"error": error, "failure_id": str(failure_id) if failure_id else None, "detail": detail}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Fail at startup, not on the first request (EC LLM-17, OPS-08).
    load_system_prompt(settings.PROMPT_VERSION)
    check_mode(settings)
    if not settings.GROQ_API_KEY:
        # Refuse to boot without a key rather than failing every request (EC LLM-12).
        raise RuntimeError("GROQ_API_KEY is not set")
    log.info("startup", extra={"model": settings.MODEL_ID, "prompt_version": settings.PROMPT_VERSION,
                               "rag_enabled": settings.RAG_ENABLED, "cors_origins": settings.cors_origins})
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(title="Nutrition Assistant API", version="0.1.0", lifespan=lifespan)
    app.state.limiter = limiter

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        log.debug("http_request", extra={"path": request.url.path, "status_code": response.status_code,
                                         "duration_ms": int((time.monotonic() - start) * 1000)})
        return response

    # Every error uses the ErrorResponse shape (EC FE-07).
    @app.exception_handler(ChatError)
    async def chat_error_handler(_: Request, exc: ChatError) -> JSONResponse:
        return _error(exc.status_code, exc.error, failure_id=exc.failure_id, detail=exc.detail)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        return _error(422, "invalid_request", detail=f"{loc}: {first.get('msg', 'invalid')}" if loc else None)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        return _error(429, "rate_limited", detail=f"Limit: {exc.detail}", headers={"Retry-After": "60"})

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(exc.status_code, "not_found" if exc.status_code == 404 else "http_error",
                      detail=str(exc.detail))

    @app.exception_handler(SQLAlchemyError)
    async def db_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        log.exception("database_error", exc_info=exc)
        return _error(503, "database_unavailable")  # EC DB-02

    app.include_router(health.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    return app


app = create_app()
