import pytest
from pydantic import ValidationError

from app.schemas.api import ChatRequest
from app.schemas.json_schema import ASSISTANT_OUTPUT_JSON_SCHEMA
from app.schemas.model_output import AssistantOutput


def validate(data):
    return AssistantOutput.model_validate(data, strict=True)


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
    generated = AssistantOutput.model_json_schema()
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
