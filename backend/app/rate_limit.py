"""Per-IP rate limit on /api/chat (AP §12)."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import get_settings


def client_ip(request: Request) -> str:
    """Behind Railway's proxy the socket address is the proxy's, so every user would share one bucket.

    With TRUST_PROXY on, use the right-most X-Forwarded-For entry: the one Railway's proxy
    appended. Left-most entries can be set by the client (EC OPS-01, OPS-02).
    """
    if get_settings().TRUST_PROXY:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            entries = [e.strip() for e in forwarded.split(",") if e.strip()]
            if entries:
                return entries[-1]
    return get_remote_address(request)


limiter = Limiter(key_func=client_ip)


def chat_rate_limit() -> str:
    return get_settings().RATE_LIMIT
