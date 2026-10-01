"""The structured-output contract the model must produce (PS §3.3, AP §4.1).

This file changes only in Milestone 2 (`source: None` -> `source: Source | None`).
Any earlier change needs a written reason in the PR.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _require_all_properties(schema: dict[str, Any]) -> None:
    # Pydantic leaves defaulted fields out of "required". The model-facing schema lists
    # every property as required, so the model must always emit "source": null.
    schema["required"] = list(schema.get("properties", {}).keys())


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    text: str = Field(min_length=1)
    # JSON Schema: {"type": "null"}. Must be null in M1 (Rule 3).
    source: None = None


class AssistantOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    answer: str = Field(min_length=1)
    claims: list[Claim]
