"""Formats retrieved chunks as the labelled sources the model answers from (FAP §8.1).

The sources go in the **user turn**, so the system prompt stays static (and cacheable).
Labels are short and local to the request ("S1".."Sk"): the model cannot mistype a long ID,
and an invented label is caught at once by the citation checker.
"""

from html import escape

from app.rag.retriever import RetrievedChunk


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def format_sources(hits: list[RetrievedChunk], question: str) -> tuple[str, dict[str, RetrievedChunk]]:
    """Returns the user-turn text and the map from label to chunk for this request."""
    label_map = {h.label: h for h in hits}
    parts = ["<sources>"]
    for h in hits:
        year = h.year if h.year is not None else "unknown"
        parts.append(
            f'<source label="{_attr(h.label)}" document="{_attr(h.document_name)}" '
            f'publisher="{_attr(h.publisher)}" year="{_attr(year)}" section="{_attr(h.section)}">'
        )
        parts.append(escape(h.text, quote=False))
        parts.append("</source>")
    parts.append("</sources>")
    parts.append(f"<question>{escape(question, quote=False)}</question>")
    return "\n".join(parts), label_map
