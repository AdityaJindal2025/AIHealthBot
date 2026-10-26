"""The structured-output contracts (PS §3.3, AP §4.1, FAP §8.2, §11.1).

Milestone 2 changed this file, as M1 anticipated. What changed (FPS §4.6):

1. `Claim.source` widened from `None` to `Source | None`. Grounded claims always carry a
   `Source`; declines and the M1 path (`RAG_ENABLED=false`) still have no claims or null sources.
2. `Source` carries more than the AP §4.1 sketch: `document_id`, `publisher_short`, `year`,
   `section`, `page`, `chunk_id` and `label` (the request-local "S3" that the sources panel shows).
3. In grounded mode the model no longer produces `AssistantOutput`. It produces
   `GroundedOutput` (claims that cite labels), and the backend builds `AssistantOutput` from
   the claims that pass the citation checks, filling `Source` from the registry and the
   retrieved chunk. The model never writes a publisher, year or URL.
4. The M1 model-facing types are kept as `UngroundedClaim` / `UngroundedOutput` (adjustment
   A2): the M1 path and `ASSISTANT_OUTPUT_JSON_SCHEMA` still require `source: null`.

`answer`, `claims` and `claims[].text` are unchanged.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

MAX_GROUNDED_CLAIMS = 8


def _require_all_properties(schema: dict[str, Any]) -> None:
    # Pydantic leaves defaulted fields out of "required". The model-facing schema lists
    # every property as required, so the model must always emit "source": null.
    schema["required"] = list(schema.get("properties", {}).keys())


# --- Milestone 1 model-facing contract (the RAG_ENABLED=false path) -------------------------


class UngroundedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    text: str = Field(min_length=1)
    # JSON Schema: {"type": "null"}. Must be null when answering without retrieval.
    source: None = None


class UngroundedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    answer: str = Field(min_length=1)
    claims: list[UngroundedClaim]


# --- Milestone 2 model-facing contract (FAP §8.2) -----------------------------------------


class GroundedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    text: str = Field(min_length=1)
    # "S1".."Sk": a label from this request's sources. Checked against the request in code (FAP §9).
    source_label: str


class GroundedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    coverage: Literal["covered", "not_covered"]
    claims: list[GroundedClaim]

    @model_validator(mode="after")
    def _claims_match_coverage(self) -> "GroundedOutput":
        if self.coverage == "covered" and not 1 <= len(self.claims) <= MAX_GROUNDED_CLAIMS:
            raise ValueError(f"covered output must have 1 to {MAX_GROUNDED_CLAIMS} claims, got {len(self.claims)}")
        if self.coverage == "not_covered" and self.claims:
            raise ValueError("not_covered output must have no claims")
        return self


# --- API-facing contract ------------------------------------------------------------------


class Source(BaseModel):
    """A real citation, built by the backend from the registry and the retrieved chunk."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    document_name: str
    publisher: str
    publisher_short: str
    # Null only with an unverified development registry; the production index build refuses one.
    year: int | None
    url: HttpUrl | None
    section: str
    page: int | None
    chunk_id: str
    label: str
    excerpt: str


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    text: str = Field(min_length=1)
    source: Source | None = None


class AssistantOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra=_require_all_properties)

    answer: str = Field(min_length=1)
    claims: list[Claim]
