"""Failure recorder (Rule 6): every model or schema failure becomes a `failures` row."""

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db import repo

log = logging.getLogger("app.failures")


def record_failure(
    db: Session,
    *,
    type: str,
    detail: str | None,
    raw_output: str | None,
    context: dict[str, Any] | None,
    conversation_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """Write the failure row and log it at ERROR.

    If the database write itself fails, the full failure is still logged and `None` is
    returned, so the caller can answer 502 with `failure_id: null` (EC DB-06).
    """
    log_fields = {
        "failure_type": type,
        "error_detail": detail,
        "conversation_id": str(conversation_id) if conversation_id else None,
        "request_context": context,
    }
    try:
        row = repo.record_failure(
            db,
            type=type,
            error_detail=detail,
            raw_output=raw_output,
            request_context=context,
            conversation_id=conversation_id,
        )
    except Exception:
        db.rollback()
        log.exception(
            "model_failure_not_recorded", extra={**log_fields, "raw_output": raw_output}
        )
        return None
    log.error("model_failure", extra={**log_fields, "failure_id": str(row.id)})
    return row.id
