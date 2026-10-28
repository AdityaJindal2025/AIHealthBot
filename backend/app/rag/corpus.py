"""Loads and validates the corpus and the document registry (FPS §3, FAP §4.1).

`load_corpus()` either returns a `Corpus` or raises `CorpusError` listing **every**
problem found, so one run shows everything that needs fixing. The index build calls it
and fails on any error; nothing is skipped or repaired silently.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

BLOCKS_FILE = "blocks.jsonl"
REGISTRY_FILE = "documents.json"

MIN_DOCUMENTS = 5  # FPS §6 Rule 6
MAX_DOCUMENTS = 7

BlockType = Literal["heading", "paragraph", "list_item", "table"]
BLOCK_TYPES = ("heading", "paragraph", "list_item", "table")

REGISTRY_FIELDS = {
    "document_id", "title", "publisher", "publisher_short", "year", "url",
    "aliases", "publisher_aliases", "verified_by", "verified_on",
}


class CorpusError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__(f"{len(problems)} corpus problem(s):\n" + "\n".join(f"- {p}" for p in problems))
        self.problems = problems


@dataclass(frozen=True)
class Block:
    document_id: str
    ordinal: int
    type: BlockType
    text: str
    heading_path: tuple[str, ...]
    level: int | None = None
    page: int | None = None
    header: tuple[str, ...] | None = None
    rows: tuple[tuple[str, ...], ...] | None = None
    caption: str | None = None


@dataclass(frozen=True)
class DocumentEntry:
    document_id: str
    title: str
    publisher: str
    publisher_short: str
    year: int | None
    url: str | None
    aliases: tuple[str, ...]
    publisher_aliases: tuple[str, ...]
    verified_by: str
    verified_on: str

    @property
    def verified(self) -> bool:
        return bool(self.verified_by.strip())


@dataclass(frozen=True)
class Corpus:
    documents: dict[str, DocumentEntry]
    # Blocks per document, in ordinal order.
    blocks_by_doc: dict[str, list[Block]] = field(default_factory=dict)

    @property
    def block_count(self) -> int:
        return sum(len(b) for b in self.blocks_by_doc.values())


def corpus_digest(corpus_dir: str | Path, *parts: str) -> str:
    """Hash of the corpus files plus anything else that decides the index (settings, model)."""
    h = hashlib.sha256()
    for name in (BLOCKS_FILE, REGISTRY_FILE):
        h.update((Path(corpus_dir) / name).read_bytes())
    for part in parts:
        h.update(b"\0" + part.encode())
    return h.hexdigest()[:16]


def load_corpus(corpus_dir: str | Path, *, allow_unverified: bool) -> Corpus:
    corpus_dir = Path(corpus_dir)
    problems: list[str] = []
    documents = _load_registry(corpus_dir / REGISTRY_FILE, allow_unverified, problems)
    blocks_by_doc = _load_blocks(corpus_dir / BLOCKS_FILE, problems)

    for doc_id in sorted(set(blocks_by_doc) - set(documents)):
        problems.append(f"{doc_id}: has blocks but no registry entry")
    for doc_id in sorted(set(documents) - set(blocks_by_doc)):
        problems.append(f"{doc_id}: registry entry has no blocks")
    if not MIN_DOCUMENTS <= len(blocks_by_doc) <= MAX_DOCUMENTS:
        problems.append(f"corpus has {len(blocks_by_doc)} documents; it must have {MIN_DOCUMENTS} to {MAX_DOCUMENTS}")

    if problems:
        raise CorpusError(problems)
    return Corpus(documents=documents, blocks_by_doc=blocks_by_doc)


def _load_registry(path: Path, allow_unverified: bool, problems: list[str]) -> dict[str, DocumentEntry]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        problems.append(f"{path.name}: cannot read: {e}")
        return {}
    if not isinstance(raw, list):
        problems.append(f"{path.name}: must be a JSON list of entries")
        return {}

    documents: dict[str, DocumentEntry] = {}
    for i, entry in enumerate(raw):
        where = f"{path.name}[{i}]"
        if not isinstance(entry, dict):
            problems.append(f"{where}: must be an object")
            continue
        doc_id = entry.get("document_id")
        where = f"{path.name}: {doc_id or f'entry {i}'}"
        missing = REGISTRY_FIELDS - entry.keys()
        extra = entry.keys() - REGISTRY_FIELDS
        if missing:
            problems.append(f"{where}: missing fields {sorted(missing)}")
            continue
        if extra:
            problems.append(f"{where}: unknown fields {sorted(extra)}")
        if not isinstance(doc_id, str) or not doc_id:
            problems.append(f"{where}: document_id must be a non-empty string")
            continue
        if doc_id in documents:
            problems.append(f"{where}: duplicate document_id")
            continue

        for name in ("title", "publisher", "publisher_short"):
            if not isinstance(entry[name], str) or not entry[name].strip():
                problems.append(f"{where}: {name} must be a non-empty string")
        for name in ("aliases", "publisher_aliases"):
            value = entry[name]
            if not isinstance(value, list) or not all(isinstance(a, str) and a == a.lower() and a for a in value):
                problems.append(f"{where}: {name} must be a list of non-empty lowercase strings")

        year, url = entry["year"], entry["url"]
        # bool is an int subclass; a year of `true` is still wrong.
        year_ok = isinstance(year, int) and not isinstance(year, bool) and 1900 <= year <= 2100
        url_ok = isinstance(url, str) and url.startswith("https://") and len(url) > len("https://")
        verified = isinstance(entry["verified_by"], str) and bool(entry["verified_by"].strip())
        if year is not None and not year_ok:
            problems.append(f"{where}: year must be an integer year, got {year!r}")
        if url is not None and not url_ok:
            problems.append(f"{where}: url must be an https:// URL, got {url!r}")
        if not allow_unverified:
            # Production: every citation needs a real year and link, checked by a person (FPS §3.3).
            if not verified:
                problems.append(f"{where}: not verified (verified_by is empty)")
            if year is None:
                problems.append(f"{where}: year is missing")
            if url is None:
                problems.append(f"{where}: url is missing")

        documents[doc_id] = DocumentEntry(
            document_id=doc_id,
            title=str(entry["title"]),
            publisher=str(entry["publisher"]),
            publisher_short=str(entry["publisher_short"]),
            year=year if year_ok else None,
            url=url if url_ok else None,
            aliases=tuple(entry["aliases"]) if isinstance(entry["aliases"], list) else (),
            publisher_aliases=tuple(entry["publisher_aliases"]) if isinstance(entry["publisher_aliases"], list) else (),
            verified_by=str(entry["verified_by"] or ""),
            verified_on=str(entry["verified_on"] or ""),
        )
    return documents


def _load_blocks(path: Path, problems: list[str]) -> dict[str, list[Block]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        problems.append(f"{path.name}: cannot read: {e}")
        return {}

    blocks_by_doc: dict[str, list[Block]] = {}
    for lineno, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        where = f"{path.name}:{lineno}"
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as e:
            problems.append(f"{where}: invalid JSON: {e}")
            continue
        block = _parse_block(raw, where, problems)
        if block is not None:
            blocks_by_doc.setdefault(block.document_id, []).append(block)

    for doc_id, blocks in blocks_by_doc.items():
        blocks.sort(key=lambda b: b.ordinal)
        seen: set[int] = set()
        for b in blocks:
            if b.ordinal in seen:
                problems.append(f"{doc_id}: duplicate ordinal {b.ordinal}")
            seen.add(b.ordinal)
        expected = set(range(len(seen)))
        for missing in sorted(expected - seen):
            problems.append(f"{doc_id}: missing ordinal {missing} (ordinals must run 0..n-1 without gaps)")
        for out_of_range in sorted(seen - expected):
            problems.append(f"{doc_id}: ordinal {out_of_range} is out of range (ordinals must run 0..n-1)")
    return blocks_by_doc


def _parse_block(raw: object, where: str, problems: list[str]) -> Block | None:
    if not isinstance(raw, dict):
        problems.append(f"{where}: block must be an object")
        return None
    doc_id, ordinal, btype, text = raw.get("document_id"), raw.get("ordinal"), raw.get("type"), raw.get("text")
    heading_path = raw.get("heading_path")
    ok = True
    if not isinstance(doc_id, str) or not doc_id:
        problems.append(f"{where}: document_id must be a non-empty string")
        ok = False
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
        problems.append(f"{where}: ordinal must be a non-negative integer")
        ok = False
    if btype not in BLOCK_TYPES:
        problems.append(f"{where}: unknown block type {btype!r}")
        ok = False
    if not isinstance(text, str):
        problems.append(f"{where}: text must be a string")
        ok = False
    if not isinstance(heading_path, list) or not all(isinstance(h, str) for h in heading_path):
        problems.append(f"{where}: heading_path must be a list of strings")
        ok = False
    page = raw.get("page")
    if page is not None and (not isinstance(page, int) or isinstance(page, bool)):
        problems.append(f"{where}: page must be an integer when present")
        ok = False
    if not ok:
        return None

    header = rows = None
    if btype == "table":
        header, rows = raw.get("header"), raw.get("rows")
        label = f"{doc_id} ordinal {ordinal}"
        if not isinstance(header, list) or not header or not isinstance(rows, list) or not rows:
            problems.append(f"{label}: table needs a non-empty header and rows")
            return None
        for i, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != len(header):
                got = len(row) if isinstance(row, list) else type(row).__name__
                problems.append(f"{label}: table row {i} has {got} cells, header has {len(header)}")
                return None
        header = tuple(str(h) for h in header)
        rows = tuple(tuple(str(c) for c in row) for row in rows)

    return Block(
        document_id=doc_id,  # type: ignore[arg-type]
        ordinal=ordinal,  # type: ignore[arg-type]
        type=btype,  # type: ignore[arg-type]
        text=text,  # type: ignore[arg-type]
        heading_path=tuple(heading_path),  # type: ignore[arg-type]
        level=raw.get("level"),
        page=page,
        header=header,
        rows=rows,
        caption=raw.get("caption"),
    )
