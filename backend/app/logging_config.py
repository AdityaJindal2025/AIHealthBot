"""Structured JSON logging with a request ID on every line (AP §12). Never logs the API key."""

import contextvars
import logging
import re
import sys

from pythonjsonlogger.json import JsonFormatter

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_SECRET = re.compile(r"gsk_[A-Za-z0-9_\-]+")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class RedactingJsonFormatter(JsonFormatter):
    """Last line of defence: scrub anything that looks like a Groq key (EC SEC-02)."""

    def format(self, record: logging.LogRecord) -> str:
        return _SECRET.sub("gsk_[REDACTED]", super().format(record))


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        RedactingJsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s", rename_fields={"levelname": "level"})
    )
    handler.addFilter(RequestContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # httpx logs full request lines at INFO; our own hook in llm/client.py covers what we need.
    logging.getLogger("httpx").setLevel(logging.WARNING)
