import pytest
from pydantic import ValidationError

from app.schemas.api import ChatRequest
from app.schemas.json_schema import ASSISTANT_OUTPUT_JSON_SCHEMA
from app.schemas.model_output import UngroundedOutput


def validate(data):
    return UngroundedOutput.model_validate(data, strict=True)


def test_valid_output_passes():
    out = validate({"answer": "Bananas contain potassium.", "claims": [{"text": "Bananas contain potassium.",
                                                                        "source": None}]})
    assert out.claims[0].source is None


def test_empty_claims_passes():
    assert validate({"answer": "Hello.", "claims": []}).claims == []


def test_non_null_source_fails():
    with pytest.raises(ValidationError):
        validate({"answer": "a", "claims": [{"text": "b", "source": "https://example.com"}]})


def test_missing_source_defaults_to_none():
    assert validate({"answer": "a", "claims": [{"text": "b"}]}).claims[0].source is None


def test_extra_top_level_field_fails():
    with pytest.raises(ValidationError):
        validate({"answer": "a", "claims": [], "confidence": 0.9})


def test_extra_claim_field_fails():
    with pytest.raises(ValidationError):
        validate({"answer": "a", "claims": [{"text": "b", "source": None, "url": "x"}]})


def test_missing_claims_fails():
    with pytest.raises(ValidationError):
        validate({"answer": "a"})


@pytest.mark.parametrize("data", [
    {"answer": "", "claims": []},
    {"answer": "a", "claims": [{"text": "", "source": None}]},
])
def test_empty_strings_fail(data):
    with pytest.raises(ValidationError):
        validate(data)


def _strip(schema: dict, defs: dict) -> dict:
    """Resolve $refs and drop annotation keys Pydantic adds (title, default, minLength)."""
    if "$ref" in schema:
        return _strip(defs[schema["$ref"].split("/")[-1]], defs)
    out = {}
    for key, value in schema.items():
        if key in ("title", "default", "minLength", "description", "$defs"):
            continue
        if key == "properties":
            out[key] = {k: _strip(v, defs) for k, v in value.items()}
        elif key == "items":
            out[key] = _strip(value, defs)
        else:
            out[key] = value
    return out


def test_generated_schema_matches_hand_written_schema():
    generated = UngroundedOutput.model_json_schema()
    assert _strip(generated, generated.get("$defs", {})) == ASSISTANT_OUTPUT_JSON_SCHEMA


def test_schema_source_is_null_and_closed_at_both_levels():
    claim = ASSISTANT_OUTPUT_JSON_SCHEMA["properties"]["claims"]["items"]
    assert claim["properties"]["source"] == {"type": "null"}
    assert "source" in claim["required"]
    assert claim["additionalProperties"] is False
    assert ASSISTANT_OUTPUT_JSON_SCHEMA["additionalProperties"] is False


class TestChatRequest:
    def test_strips_whitespace_and_rejects_empty(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="   \n")

    def test_boundary_2000_ok_2001_fails(self):
        assert len(ChatRequest(message="a" * 2000).message) == 2000
        with pytest.raises(ValidationError):
            ChatRequest(message="a" * 2001)

    def test_emoji_counts_as_one_character(self):
        assert ChatRequest(message="🥑" * 2000).message

    def test_control_characters_removed(self):
        assert ChatRequest(message="rice\x00 is\tgood\nok").message == "rice is\tgood\nok"

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="hi", foo=1)


# --- Milestone 2 contract (FAP §11.1, Phase 5) -------------------------------------------

from app.schemas.api import ChatResponse  # noqa: E402
from app.schemas.json_schema import GROUNDED_OUTPUT_JSON_SCHEMA  # noqa: E402
from app.schemas.model_output import Claim, GroundedOutput, Source  # noqa: E402

SOURCE = {
    "document_id": "who-healthy-diet", "document_name": "Healthy diet (Fact sheet N°394)",
    "publisher": "World Health Organization", "publisher_short": "WHO", "year": 2020,
    "url": "https://www.example.org/healthy-diet", "section": "FOR ADULTS", "page": 1,
    "chunk_id": "who-healthy-diet#0014-0019.p1", "label": "S1", "excerpt": "Less than 10% of total energy…",
}


def grounded(data):
    return GroundedOutput.model_validate(data, strict=True)


def test_grounded_schema_matches_pydantic():
    generated = GroundedOutput.model_json_schema()
    assert _strip(generated, generated.get("$defs", {})) == GROUNDED_OUTPUT_JSON_SCHEMA


def test_grounded_covered_with_claims_passes():
    out = grounded({"coverage": "covered", "claims": [{"text": "WHO recommends…", "source_label": "S1"}]})
    assert out.claims[0].source_label == "S1"


def test_grounded_not_covered_without_claims_passes():
    assert grounded({"coverage": "not_covered", "claims": []}).claims == []


@pytest.mark.parametrize("data", [
    {"coverage": "covered", "claims": []},
    {"coverage": "not_covered", "claims": [{"text": "x", "source_label": "S1"}]},
    {"coverage": "covered", "claims": [{"text": f"c{i}", "source_label": "S1"} for i in range(9)]},
    {"coverage": "covered", "claims": [{"text": "x", "source_label": "S1", "source": "WHO"}]},
    {"coverage": "partly", "claims": []},
    {"coverage": "covered", "claims": [{"text": "", "source_label": "S1"}]},
])
def test_grounded_invalid_outputs_fail(data):
    with pytest.raises(ValidationError):
        grounded(data)


def test_claim_with_full_source_passes():
    claim = Claim.model_validate({"text": "WHO recommends…", "source": SOURCE})
    assert claim.source.year == 2020 and str(claim.source.url).startswith("https://")


@pytest.mark.parametrize("field, value", [("year", "2020"), ("url", "not a url"), ("label", None)])
def test_source_rejects_bad_values(field, value):
    with pytest.raises(ValidationError):
        Source.model_validate({**SOURCE, field: value}, strict=field == "year")


def test_source_rejects_extra_fields():
    with pytest.raises(ValidationError):
        Source.model_validate({**SOURCE, "confidence": 1})


def test_m1_shaped_response_still_validates():
    data = {"conversation_id": "7f6c4f9e-1f2a-4d2b-9d4e-111111111111",
            "message_id": "7f6c4f9e-1f2a-4d2b-9d4e-222222222222", "answer": "a",
            "claims": [{"text": "b", "source": None}], "scope": {"status": "in_scope"},
            "meta": {"prompt_version": "v1"}}
    response = ChatResponse.model_validate(data)
    assert response.grounding is None and response.sources == []


def test_chat_request_accepts_document_id():
    assert ChatRequest(message="hi", document_id="fsa-chill").document_id == "fsa-chill"
    with pytest.raises(ValidationError):
        ChatRequest(message="hi", document_id="")
