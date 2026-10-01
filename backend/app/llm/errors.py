import uuid
from typing import Literal

FailureType = Literal["schema_invalid", "model_refusal", "truncated_output", "api_error"]


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
    ) -> None:
        super().__init__(f"{type}: {detail}" if detail else type)
        self.type: FailureType = type
        self.detail = detail
        self.raw_output = raw_output
        self.model = model
        self.latency_ms = latency_ms
        self.failure_id: uuid.UUID | None = None
