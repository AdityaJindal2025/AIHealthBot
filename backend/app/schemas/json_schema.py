"""The hand-written JSON Schemas sent to the model as `response_format` (strict mode).

`tests/test_schema.py` checks each against the schema Pydantic generates from its model
(`UngroundedOutput`, `GroundedOutput`), so the two definitions cannot drift apart. Both stay
within the keywords Groq's strict mode is known to accept (`type`, `properties`, `required`,
`additionalProperties`, `enum`); claim counts and label format are enforced in code (A1).
"""

ASSISTANT_OUTPUT_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source": {"type": "null"},
                },
                "required": ["text", "source"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer", "claims"],
    "additionalProperties": False,
}


GROUNDED_OUTPUT_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "coverage": {"type": "string", "enum": ["covered", "not_covered"]},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source_label": {"type": "string"},
                },
                "required": ["text", "source_label"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["coverage", "claims"],
    "additionalProperties": False,
}
