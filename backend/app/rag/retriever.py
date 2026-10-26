"""Retrieval across all documents or filtered to one (FPS §4.2, FAP §7).

`retrieve()` embeds the query, takes the top candidates from the vector store and selects
up to k chunks:

- **filtered** (a `document_id` given, or exactly one document named in the message):
  only that document, no per-document cap
- **all documents**: in score order, at most `RETRIEVAL_MAX_PER_DOC` per document, so one
  large document (kitchen-companion is ~47% of the corpus) cannot fill every slot

Restricted chunks (calorie or weight targets, FAP §10.3) never reach the model: if the top
hit is restricted the caller declines; any lower restricted hit is withheld and recorded.

The result holds plain snapshots, not ORM rows, so it can be stored with the message and
history still shows what was retrieved after the index is rebuilt.
"""

import re
from dataclasses import asdict, dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Document, IndexMeta
from app.rag.embedder import get_embedder
from app.rag.store import Hit, get_store

FOLLOW_UP_MARKERS = ("what about", "and ", "how about", "is that", "what if", "same for", "and?")
FOLLOW_UP_MAX_WORDS = 6


class RetrievalError(Exception):
    def __init__(self, type: Literal["embedding_error", "retrieval_error"], detail: str) -> None:
        super().__init__(f"{type}: {detail}")
        self.type = type
        self.detail = detail


@dataclass(frozen=True)
class RetrievedChunk:
    label: str  # "S1".."Sk" for hits; "" for withheld chunks
    rank: int  # 1-based rank among the candidates
    chunk_id: str
    document_id: str
    document_name: str
    publisher: str
    publisher_short: str
    year: int | None
    url: str | None
    section: str
    section_path: tuple[str, ...]
    page_start: int | None
    page_end: int | None
    kind: str
    text: str
    score: float
    restricted_category: str | None = None
    restricted_rule_id: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["section_path"] = list(self.section_path)
        return data


@dataclass
class RetrievalResult:
    mode: Literal["all", "filtered"]
    query_text: str
    filter_document_id: str | None
    filter_source: Literal["explicit", "detected"] | None
    k: int
    corpus_version: str
    hits: list[RetrievedChunk] = field(default_factory=list)
    withheld: list[RetrievedChunk] = field(default_factory=list)
    top_score: float | None = None
    # Set when the best match is itself restricted: the caller declines (stage=retrieval).
    restricted_top: str | None = None
    restricted_top_rule_id: str | None = None


def _normalise(text: str) -> str:
    return " ".join(text.lower().replace("’", "'").split())


def build_query(message: str, previous_user_message: str | None) -> str:
    """Short or follow-up messages ("what about for vegans?") carry the previous question with them."""
    if not previous_user_message:
        return message
    text = _normalise(message)
    if len(text.split()) < FOLLOW_UP_MAX_WORDS or text.startswith(FOLLOW_UP_MARKERS):
        return f"{previous_user_message.strip()} {message.strip()}"
    return message


def detect_document(message: str, documents: list[Document]) -> str | None:
    """The one document the message names by alias, or None if it names none or several."""
    text = _normalise(message)
    named = {
        doc.document_id
        for doc in documents
        for alias in doc.aliases
        if re.search(rf"(?<![a-z0-9]){re.escape(_normalise(alias))}(?![a-z0-9])", text)
    }
    return named.pop() if len(named) == 1 else None


def retrieve(
    db: Session,
    message: str,
    *,
    previous_user_message: str | None = None,
    document_id: str | None = None,
    k: int | None = None,
    max_per_doc: int | None = None,
) -> RetrievalResult:
    settings = get_settings()
    k = k or settings.RETRIEVAL_K
    max_per_doc = max_per_doc or settings.RETRIEVAL_MAX_PER_DOC

    try:
        documents = {d.document_id: d for d in db.scalars(select(Document))}
        corpus_version = db.scalar(select(IndexMeta.corpus_version)) or ""
    except Exception as e:
        raise RetrievalError("retrieval_error", f"{type(e).__name__}: {e}") from e

    filter_source: Literal["explicit", "detected"] | None = None
    if document_id is not None:
        filter_source = "explicit"
    else:
        document_id = detect_document(message, list(documents.values()))
        filter_source = "detected" if document_id else None

    query_text = build_query(message, previous_user_message)
    try:
        query_vec = get_embedder().embed_query(query_text)
    except Exception as e:
        raise RetrievalError("embedding_error", f"{type(e).__name__}: {e}") from e
    try:
        candidates = get_store(db).search(query_vec, settings.RETRIEVAL_CANDIDATES, document_id=document_id)
    except Exception as e:
        raise RetrievalError("retrieval_error", f"{type(e).__name__}: {e}") from e

    result = RetrievalResult(
        mode="filtered" if document_id else "all",
        query_text=query_text,
        filter_document_id=document_id,
        filter_source=filter_source,
        k=k,
        corpus_version=corpus_version,
        top_score=candidates[0].score if candidates else None,
    )
    if candidates and candidates[0].chunk.restricted_category:
        result.restricted_top = candidates[0].chunk.restricted_category
        result.restricted_top_rule_id = candidates[0].chunk.restricted_rule_id

    per_doc: dict[str, int] = {}
    for rank, hit in enumerate(candidates, start=1):
        if hit.chunk.restricted_category:
            result.withheld.append(_snapshot(hit, rank, "", documents))
            continue
        if len(result.hits) >= k:
            continue  # keep scanning only to record withheld chunks that outrank nothing we kept
        if not document_id and per_doc.get(hit.chunk.document_id, 0) >= max_per_doc:
            continue
        per_doc[hit.chunk.document_id] = per_doc.get(hit.chunk.document_id, 0) + 1
        result.hits.append(_snapshot(hit, rank, f"S{len(result.hits) + 1}", documents))
    # When all k slots filled, only restricted chunks that outranked the last kept hit were withheld;
    # the rest would not have been shown anyway.
    if len(result.hits) >= k:
        last_rank = result.hits[-1].rank
        result.withheld = [w for w in result.withheld if w.rank < last_rank]
    return result


def _snapshot(hit: Hit, rank: int, label: str, documents: dict[str, Document]) -> RetrievedChunk:
    c = hit.chunk
    doc = documents.get(c.document_id) or c.document
    return RetrievedChunk(
        label=label,
        rank=rank,
        chunk_id=c.chunk_id,
        document_id=c.document_id,
        document_name=doc.title,
        publisher=doc.publisher,
        publisher_short=doc.publisher_short,
        year=doc.year,
        url=doc.url,
        section=c.section,
        section_path=tuple(c.section_path),
        page_start=c.page_start,
        page_end=c.page_end,
        kind=c.kind,
        text=c.text,
        score=round(hit.score, 6),
        restricted_category=c.restricted_category,
        restricted_rule_id=c.restricted_rule_id,
    )
