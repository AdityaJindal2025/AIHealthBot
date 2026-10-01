"""The hand-written JSON Schema from AP §4.1.

This exact schema is sent to the API as `output_config.format`. `tests/test_schema.py`
checks that it matches the schema Pydantic generates from `AssistantOutput`, so the
two definitions cannot drift apart.
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
