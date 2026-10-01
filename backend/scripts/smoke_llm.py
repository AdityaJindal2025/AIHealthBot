"""Send one question to the real API and print the validated output (IP Phase 4 exit gate).

Checks the key, the model ID (EC LLM-10) and that the API accepts the `source: null`
schema (EC LLM-09). Costs one API call.

    cd backend && python scripts/smoke_llm.py "How much fibre is in oats?"
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.llm.client import generate  # noqa: E402
from app.llm.errors import ModelFailure  # noqa: E402


def main() -> int:
    question = " ".join(sys.argv[1:]) or "How much fibre is in a cup of cooked oats?"
    settings = get_settings()
    print(f"model={settings.MODEL_ID} prompt={settings.PROMPT_VERSION}\nQ: {question}\n")
    try:
        result = generate([], question)
    except ModelFailure as e:
        print(f"FAILED: {e.type}: {e.detail}")
        if e.raw_output:
            print(f"raw output:\n{e.raw_output}")
        return 1
    print(json.dumps(result.output.model_dump(), indent=2))
    print(f"\nserved_by={result.model} latency_ms={result.latency_ms} "
          f"tokens in/out={result.input_tokens}/{result.output_tokens}")
    assert all(c.source is None for c in result.output.claims), "a claim has a non-null source"
    print("OK: schema valid, every source is null")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
