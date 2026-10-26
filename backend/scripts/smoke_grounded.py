"""Retrieve, ask the real model, check citations and print the composed answer (Phase 6 exit gate).

Checks that the Groq strict-mode API accepts the grounded schema (adjustment A1) and shows the
whole answer layer on real data. Needs a built index (`python -m app.rag.build_index`) and the
`embed` extra. Costs one API call per question.

    cd backend && PROMPT_VERSION=v2 python scripts/smoke_grounded.py
    cd backend && PROMPT_VERSION=v2 python scripts/smoke_grounded.py "How long can egg salad stay in the fridge?"
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import repo  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.llm.client import generate_grounded  # noqa: E402
from app.llm.errors import ModelFailure  # noqa: E402
from app.rag.citations import PublisherInfo, check_claims  # noqa: E402
from app.rag.composer import compose_answer  # noqa: E402
from app.rag.context import format_sources  # noqa: E402
from app.rag.retriever import retrieve  # noqa: E402

DEFAULT_QUESTIONS = ["How long can egg salad stay in the fridge?", "What do the guidelines say about salt?"]


def ask(db, question: str) -> bool:
    print(f"\n=== Q: {question}")
    retrieval = retrieve(db, question)
    print(f"top_score={retrieval.top_score:.4f} mode={retrieval.mode} restricted_top={retrieval.restricted_top}")
    for h in retrieval.hits:
        print(f"  {h.label} {h.score:.4f} {h.chunk_id}")
    if retrieval.restricted_top:
        print("-> declined at retrieval (restricted top hit); the model is not called")
        return True
    user_turn, label_map = format_sources(retrieval.hits, question)
    try:
        result = generate_grounded([], user_turn)
    except ModelFailure as e:
        print(f"FAILED: {e.type}: {e.detail}")
        if e.raw_output:
            print(f"raw output:\n{e.raw_output}")
        return False
    print(json.dumps(result.output.model_dump(), indent=2))
    print(f"served_by={result.model} latency_ms={result.latency_ms} "
          f"tokens in/out={result.input_tokens}/{result.output_tokens}")
    if result.output.coverage == "not_covered":
        print("-> model says the sources do not cover it")
        return True
    publishers = [PublisherInfo(d.document_id, d.publisher, tuple(d.publisher_aliases))
                  for d, _ in repo.list_documents(db)]
    citations = check_claims(result.output, label_map, publishers)
    for d in citations.dropped:
        print(f"DROPPED ({d.reason}): {d.claim.text!r} -> {d.claim.source_label}")
    if not citations.valid:
        print("FAILED: no valid claims")
        return False
    print("\n" + compose_answer(citations.valid).answer)
    return True


def main() -> int:
    settings = get_settings()
    print(f"model={settings.MODEL_ID} prompt={settings.PROMPT_VERSION} embedding={settings.EMBEDDING_MODEL}")
    questions = [" ".join(sys.argv[1:])] if sys.argv[1:] else DEFAULT_QUESTIONS
    db = SessionLocal()
    try:
        if repo.get_index_meta(db) is None:
            print("No index: run `python -m app.rag.build_index` first")
            return 1
        ok = all([ask(db, q) for q in questions])
    finally:
        db.close()
    print("\nOK" if ok else "\nFAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
