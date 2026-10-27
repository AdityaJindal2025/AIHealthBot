import uuid
from typing import Literal

# `rate_limited`: the provider refused the call (429) before the model ran. It is recorded like any
# failure, but the client gets 503 + Retry-After, not 502: it says nothing about answer quality.
FailureType = Literal["schema_invalid", "model_refusal", "truncated_output", "api_error", "rate_limited"]


class ModelFailure(Exception):
    """A model call that did not produce a valid `AssistantOutput`.

    `failure_id` is set once the failure has been written to the `failures` table.
    """

    def __init__(
        self,
        type: FailureType,
        detail: str | None = None,
        raw_output: str | None = None,
        *,
        model: str | None = None,
        latency_ms: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(f"{type}: {detail}" if detail else type)
        self.type: FailureType = type
        self.detail = detail
        self.raw_output = raw_output
        self.model = model
        self.latency_ms = latency_ms
        self.retry_after = retry_after  # seconds, from the provider's Retry-After header
        self.failure_id: uuid.UUID | None = None
