"""Builds the displayed answer from validated claims (FAP §8.3, §10.1).

The answer text is composed by the backend, not written by the model, so "no citation, no
ship" and "never blend sources" are structural: every sentence the user sees is a validated
claim with its citation marker, grouped under the document it came from.

- One document: an attribution line, then the claims as bullets.
- Several documents: a neutral lead line, then one block per document (in order of first
  appearance) with its publisher and year. Blocks are never merged and never ranked, so a
  disagreement shows as two positions side by side (FPS §4.4, Rule 5).

Citation markers use the source label's number (S3 → [3], adjustment A5), so a marker, a
chip and the sources panel always agree.
"""

from app.rag.citations import ValidClaim
from app.schemas.api import SearchedDocument
from app.schemas.model_output import AssistantOutput, Claim

MULTI_DOCUMENT_LEAD = "These documents each address this:"
NOT_COVERED_LEAD = "The guidance I searched doesn't cover this."


def _attribution(name: str, publisher: str, year: int | None) -> str:
    return f"{name} ({publisher}, {year})" if year is not None else f"{name} ({publisher})"


def marker(label: str) -> str:
    return f"[{label.removeprefix('S')}]"


def compose_answer(valid: list[ValidClaim]) -> AssistantOutput:
    if not valid:
        raise ValueError("compose_answer needs at least one validated claim")
    by_doc: dict[str, list[ValidClaim]] = {}
    for v in valid:
        by_doc.setdefault(v.chunk.document_id, []).append(v)

    blocks = []
    for claims in by_doc.values():
        c = claims[0].chunk
        bullets = "\n".join(f"- {v.claim.text.strip()} {marker(v.chunk.label)}" for v in claims)
        heading = _attribution(c.document_name, c.publisher, c.year)
        if len(by_doc) == 1:
            blocks.append(f"From {heading}:\n{bullets}")
        else:
            blocks.append(f"{heading}:\n{bullets}")
    answer = "\n\n".join(blocks) if len(by_doc) == 1 else MULTI_DOCUMENT_LEAD + "\n\n" + "\n\n".join(blocks)
    # Claims keep the grouped order, so claims[i] matches the i-th bullet.
    ordered = [v for claims in by_doc.values() for v in claims]
    return AssistantOutput(answer=answer, claims=[Claim(text=v.claim.text.strip(), source=v.source) for v in ordered])


def compose_not_covered(searched: list[SearchedDocument], *, filtered: bool) -> AssistantOutput:
    """The fixed "not in the corpus" text, naming what was searched (FPS §4.5). Never model-written."""
    names = [_attribution(d.document_name, d.publisher, d.year) for d in searched]
    if filtered and len(names) == 1:
        answer = f"{NOT_COVERED_LEAD} I searched only {names[0]}, as you asked."
    else:
        answer = f"{NOT_COVERED_LEAD} I searched: " + "; ".join(names) + "."
    return AssistantOutput(answer=answer, claims=[])
