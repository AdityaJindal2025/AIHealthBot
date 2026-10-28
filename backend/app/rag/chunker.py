"""Structure-aware chunking (FPS §4.1, FAP §5.2).

The corpus is already structured: every block has a `type` and a `heading_path`. Chunks
follow that structure instead of character counts:

1. **Sections**: consecutive blocks with the same `heading_path`. Heading blocks only
   label the section and never become chunk text.
2. **Units** (never split while packing): one paragraph; one run of `list_item` blocks
   together with a lead-in paragraph ending in ":"; one table, rendered as Markdown.
3. **Packing**: units are packed greedily up to the target size and never past the
   hard maximum, both counted on `embed_text` (context header included).
4. **Oversize units**: a table is split by rows with its caption and header repeated; a
   list run between items with its lead-in repeated; a paragraph (or a single row or
   item) at sentence boundaries, which is flagged in the build report.
5. **Tiny sections** merge into the next sibling section under the same parent heading,
   never across documents and never across a level-1 or level-2 heading.

Overlap is 0: chunks end on unit boundaries, and the context header prepended to every
chunk (document title › section path) does the job overlap usually does.

`heading_path` depth, not the heading `level` (which follows font size in the source
PDFs), decides what a sibling is. A merge also needs the next section's heading to be
level 3 or deeper, and both sections to sit under a parent heading (depth ≥ 2).
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from app.config import Settings
from app.rag.corpus import Block, Corpus, DocumentEntry
from app.rag.tokens import count_tokens

# Bump when the algorithm changes in a way that changes chunks; it feeds `corpus_version`.
CHUNKER_VERSION = 1

ChunkKind = Literal["prose", "list", "table", "mixed"]
UnitKind = Literal["paragraph", "list", "table"]
EventKind = Literal["table_split", "list_split", "sentence_split", "merge"]

_MARKER = re.compile(r"^\s*(\d+[.)]|[•\-–*])\s")
_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"”’)]?\s+(?=[\"“‘(]?[A-Z0-9])")


@dataclass(frozen=True)
class ChunkSettings:
    target_tokens: int = 350
    max_tokens: int = 480
    min_tokens: int = 60

    @classmethod
    def from_settings(cls, settings: Settings) -> "ChunkSettings":
        return cls(settings.CHUNK_TARGET_TOKENS, settings.CHUNK_MAX_TOKENS, settings.CHUNK_MIN_TOKENS)

    def as_dict(self) -> dict[str, int]:
        return {"chunker_version": CHUNKER_VERSION, "target_tokens": self.target_tokens,
                "max_tokens": self.max_tokens, "min_tokens": self.min_tokens, "overlap_tokens": 0}

    def fingerprint(self) -> str:
        return repr(sorted(self.as_dict().items()))


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    document_name: str
    publisher: str
    year: int | None
    section_path: tuple[str, ...]
    section: str
    page_start: int | None
    page_end: int | None
    ordinals: tuple[int, ...]
    kind: ChunkKind
    text: str
    embed_text: str
    token_count: int
    # Caption + header of each table in the chunk; the tagger matches table rules on these.
    table_labels: tuple[str, ...] = ()
    restricted_category: str | None = None
    restricted_rule_id: str | None = None


@dataclass(frozen=True)
class ChunkEvent:
    """A split, merge or sentence-level split, listed in the build report for review."""

    kind: EventKind
    document_id: str
    chunk_ids: tuple[str, ...]
    detail: str


@dataclass
class ChunkingResult:
    chunks: list[Chunk]
    events: list[ChunkEvent] = field(default_factory=list)


@dataclass(frozen=True)
class _Section:
    path: tuple[str, ...]
    heading_level: int | None  # level of the heading block that opened it, if any
    blocks: tuple[Block, ...]  # content blocks only


@dataclass(frozen=True)
class _Unit:
    kind: UnitKind
    blocks: tuple[Block, ...]  # for a list: lead-in (if any) then items
    origin: tuple[str, ...]  # section path the unit came from
    lead_in: Block | None = None

    @property
    def items(self) -> tuple[Block, ...]:
        return self.blocks[1:] if self.lead_in else self.blocks


@dataclass(frozen=True)
class _Piece:
    """Rendered content for one chunk before metadata is attached."""

    text: str
    blocks: tuple[Block, ...]
    origins: tuple[tuple[str, ...], ...]
    unit_kinds: frozenset[UnitKind]
    table_labels: tuple[str, ...]
    id_range: tuple[int, int]
    part: int | None = None


# ---------------------------------------------------------------------------
# Public entry point


def chunk_corpus(corpus: Corpus, settings: ChunkSettings) -> ChunkingResult:
    result = ChunkingResult(chunks=[])
    for doc_id in sorted(corpus.blocks_by_doc):
        doc = corpus.documents[doc_id]
        _chunk_document(doc, corpus.blocks_by_doc[doc_id], settings, result)
    return result


# ---------------------------------------------------------------------------
# Steps 1 and 2: sections and units


def _sections(blocks: list[Block]) -> list[_Section]:
    sections: list[_Section] = []
    path: tuple[str, ...] | None = None
    level: int | None = None
    content: list[Block] = []
    for block in blocks:
        if block.heading_path != path:
            if path is not None:
                sections.append(_Section(path, level, tuple(content)))
            path, level, content = block.heading_path, None, []
        if block.type == "heading":
            if not content and level is None:
                level = block.level
            continue
        content.append(block)
    if path is not None:
        sections.append(_Section(path, level, tuple(content)))
    return sections


def _units(section: _Section) -> list[_Unit]:
    units: list[_Unit] = []
    blocks = section.blocks
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if block.type == "table":
            units.append(_Unit("table", (block,), section.path))
            i += 1
            continue
        lead_in = None
        if block.type == "paragraph":
            starts_list = i + 1 < len(blocks) and blocks[i + 1].type == "list_item"
            if starts_list and block.text.rstrip().endswith(":"):
                lead_in = block
                i += 1
            else:
                units.append(_Unit("paragraph", (block,), section.path))
                i += 1
                continue
        items: list[Block] = []
        while i < len(blocks) and blocks[i].type == "list_item":
            items.append(blocks[i])
            i += 1
        run = ((lead_in,) if lead_in else ()) + tuple(items)
        units.append(_Unit("list", run, section.path, lead_in=lead_in))
    return units


# ---------------------------------------------------------------------------
# Rendering


def _render_item(block: Block) -> str:
    text = block.text.strip()
    return text if _MARKER.match(text) else f"- {text}"


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _table_lines(block: Block) -> tuple[str, str]:
    assert block.header is not None
    header = "| " + " | ".join(_cell(h) for h in block.header) + " |"
    rule = "| " + " | ".join("---" for _ in block.header) + " |"
    return header, rule


def _render_table(block: Block, rows: tuple[tuple[str, ...], ...], part: str = "") -> str:
    header, rule = _table_lines(block)
    lines = []
    if block.caption or part:
        lines.append(f"{(block.caption or 'Table').strip()}{part}")
    lines += [header, rule]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _render_unit(unit: _Unit) -> str:
    if unit.kind == "paragraph":
        return unit.blocks[0].text.strip()
    if unit.kind == "table":
        block = unit.blocks[0]
        return _render_table(block, block.rows or ())
    lines = [unit.lead_in.text.strip()] if unit.lead_in else []
    return "\n".join(lines + [_render_item(b) for b in unit.items])


def _table_label(block: Block) -> str:
    caption = (block.caption or "").strip()
    header = " | ".join(block.header or ())
    return f"{caption} :: {header}" if caption else header


def _join_units(units: list[_Unit]) -> str:
    """Units from one section are joined plainly; merged sections get a bold sub-heading each."""
    origins = list(dict.fromkeys(u.origin for u in units))
    if len(origins) == 1:
        return "\n\n".join(_render_unit(u) for u in units)
    parts = []
    for origin in origins:
        body = "\n\n".join(_render_unit(u) for u in units if u.origin == origin)
        parts.append(f"**{origin[-1]}**\n\n{body}")
    return "\n\n".join(parts)


def _section_path(origins: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    if len(origins) == 1:
        return origins[0]
    parent = origins[0][:-1]
    return parent + ("; ".join(o[-1] for o in origins),)


def _embed_text(doc: DocumentEntry, section_path: tuple[str, ...], text: str) -> str:
    header = f"{doc.title} — {' › '.join(section_path)}" if section_path else doc.title
    return f"{header}\n\n{text}"


def _tokens(doc: DocumentEntry, origins: tuple[tuple[str, ...], ...], text: str) -> int:
    return count_tokens(_embed_text(doc, _section_path(origins), text))


def _piece_from_units(units: list[_Unit]) -> _Piece:
    blocks = tuple(b for u in units for b in u.blocks)
    ordinals = [b.ordinal for b in blocks]
    return _Piece(
        text=_join_units(units),
        blocks=blocks,
        origins=tuple(dict.fromkeys(u.origin for u in units)),
        unit_kinds=frozenset(u.kind for u in units),
        table_labels=tuple(_table_label(b) for u in units if u.kind == "table" for b in u.blocks),
        id_range=(min(ordinals), max(ordinals)),
    )


# ---------------------------------------------------------------------------
# Steps 3 to 5: merge tiny sections, pack, split oversize units


def _chunk_document(doc: DocumentEntry, blocks: list[Block], settings: ChunkSettings,
                    result: ChunkingResult) -> None:
    sections = [s for s in _sections(blocks) if s.blocks]  # heading-only sections give no chunk
    groups = _merge_tiny_sections(doc, sections, settings)
    for group in groups:
        pieces = _pack(doc, group, settings, result)
        for piece in pieces:
            chunk = _make_chunk(doc, piece)
            result.chunks.append(chunk)
            if len(piece.origins) > 1:
                result.events.append(ChunkEvent(
                    "merge", doc.document_id, (chunk.chunk_id,),
                    "merged tiny section(s) " + " + ".join(f"'{o[-1]}'" for o in piece.origins),
                ))


def _can_merge(tiny: _Section, nxt: _Section) -> bool:
    return (
        len(tiny.path) >= 2
        and nxt.path[:-1] == tiny.path[:-1]
        and len(nxt.path) == len(tiny.path)
        and (nxt.heading_level is None or nxt.heading_level >= 3)
    )


def _merge_tiny_sections(doc: DocumentEntry, sections: list[_Section],
                         settings: ChunkSettings) -> list[list[_Unit]]:
    groups: list[list[_Unit]] = []
    carry: list[_Unit] = []
    carry_section: _Section | None = None
    for i, section in enumerate(sections):
        units = carry + _units(section)
        nxt = sections[i + 1] if i + 1 < len(sections) else None
        anchor = carry_section or section
        size = _tokens(doc, tuple(dict.fromkeys(u.origin for u in units)), _join_units(units))
        if size < settings.min_tokens and nxt is not None and _can_merge(anchor, nxt) and _can_merge(section, nxt):
            carry, carry_section = units, anchor
            continue
        groups.append(units)
        carry, carry_section = [], None
    return groups


def _pack(doc: DocumentEntry, units: list[_Unit], settings: ChunkSettings,
          result: ChunkingResult) -> list[_Piece]:
    pieces: list[_Piece] = []
    current: list[_Unit] = []

    def size(us: list[_Unit]) -> int:
        return _tokens(doc, tuple(dict.fromkeys(u.origin for u in us)), _join_units(us))

    def flush() -> None:
        if current:
            pieces.append(_piece_from_units(current))
            current.clear()

    for i, unit in enumerate(units):
        if size([unit]) > settings.max_tokens:
            flush()
            pieces.extend(_split_unit(doc, unit, settings, result))
            continue
        if not current:
            current.append(unit)
            continue
        candidate = size(current + [unit])
        # Past the target is allowed (up to the hard maximum) when the chunk so far is tiny, or
        # for a tiny last unit, so a short closing paragraph stays with its table.
        last = i == len(units) - 1
        small = size(current) < settings.min_tokens or (last and size([unit]) < settings.min_tokens)
        if candidate <= settings.target_tokens or (small and candidate <= settings.max_tokens):
            current.append(unit)
        else:
            flush()
            current.append(unit)
    flush()
    return pieces


def _split_unit(doc: DocumentEntry, unit: _Unit, settings: ChunkSettings,
                result: ChunkingResult) -> list[_Piece]:
    if unit.kind == "table":
        pieces = _split_table(doc, unit, settings, result)
        kind: EventKind = "table_split"
    elif unit.kind == "list":
        pieces = _split_list(doc, unit, settings, result)
        kind = "list_split"
    else:
        block = unit.blocks[0]
        texts = _split_sentences(block.text.strip(), lambda t: _tokens(doc, (unit.origin,), t), settings.max_tokens)
        pieces = [_simple_piece(unit, t, (block,)) for t in texts]
        kind = "sentence_split"
    pieces = [_with_part(p, i + 1) for i, p in enumerate(pieces)]
    first, last = unit.blocks[0].ordinal, unit.blocks[-1].ordinal
    ids = tuple(_chunk_id(doc.document_id, (first, last), p.part) for p in pieces)
    result.events.append(ChunkEvent(kind, doc.document_id, ids,
                                    f"{unit.kind} at ordinals {first}-{last} split into {len(pieces)} parts"))
    return pieces


def _simple_piece(unit: _Unit, text: str, blocks: tuple[Block, ...]) -> _Piece:
    return _Piece(
        text=text,
        blocks=blocks,
        origins=(unit.origin,),
        unit_kinds=frozenset({unit.kind}),
        table_labels=tuple(_table_label(b) for b in blocks if b.type == "table"),
        # Every part of one unit shares the unit's ordinal range; the part number tells them apart.
        id_range=(unit.blocks[0].ordinal, unit.blocks[-1].ordinal),
    )


def _with_part(piece: _Piece, part: int) -> _Piece:
    return _Piece(piece.text, piece.blocks, piece.origins, piece.unit_kinds, piece.table_labels,
                  piece.id_range, part)


def _split_table(doc: DocumentEntry, unit: _Unit, settings: ChunkSettings,
                 result: ChunkingResult) -> list[_Piece]:
    block = unit.blocks[0]
    rows = block.rows or ()
    # Measure with a worst-case part label so the final "(part i of n)" never pushes a part over.
    probe = " (part 99 of 99)"

    def fits(rs: tuple[tuple[str, ...], ...]) -> bool:
        return _tokens(doc, (unit.origin,), _render_table(block, rs, probe)) <= settings.max_tokens

    groups: list[tuple[tuple[str, ...], ...] | str] = []
    current: tuple[tuple[str, ...], ...] = ()
    for row in rows:
        if fits(current + (row,)):
            current += (row,)
            continue
        if current:
            groups.append(current)
            current = ()
        if fits((row,)):
            current = (row,)
        else:
            # One row is too big on its own: split its text at sentence boundaries, header repeated.
            header, rule = _table_lines(block)
            row_text = "\n".join(f"{_cell(h)}: {_cell(c)}" for h, c in zip(block.header or (), row, strict=True))
            prefix = f"{(block.caption or 'Table').strip()}{probe}\n{header}\n{rule}\n"
            for text in _split_sentences(row_text, lambda t, p=prefix: _tokens(doc, (unit.origin,), p + t),
                                         settings.max_tokens):
                groups.append(text)
            result.events.append(ChunkEvent("sentence_split", doc.document_id, (),
                                            f"table row at ordinal {block.ordinal} split at sentences"))
    if current:
        groups.append(current)

    n = len(groups)
    pieces = []
    for i, group in enumerate(groups, start=1):
        label = f" (part {i} of {n})"
        if isinstance(group, str):
            header, rule = _table_lines(block)
            text = f"{(block.caption or 'Table').strip()}{label}\n{header}\n{rule}\n{group}"
        else:
            text = _render_table(block, group, label)
        pieces.append(_simple_piece(unit, text, (block,)))
    return pieces


def _split_list(doc: DocumentEntry, unit: _Unit, settings: ChunkSettings,
                result: ChunkingResult) -> list[_Piece]:
    lead = unit.lead_in.text.strip() if unit.lead_in else ""
    lead_blocks = (unit.lead_in,) if unit.lead_in else ()

    def render(items: list[Block]) -> str:
        return "\n".join(([lead] if lead else []) + [_render_item(b) for b in items])

    def fits(items: list[Block]) -> bool:
        return _tokens(doc, (unit.origin,), render(items)) <= settings.max_tokens

    pieces: list[_Piece] = []
    current: list[Block] = []
    for item in unit.items:
        if fits(current + [item]):
            current.append(item)
            continue
        if current:
            pieces.append(_simple_piece(unit, render(current), lead_blocks + tuple(current)))
            current = []
        if fits([item]):
            current = [item]
        else:
            prefix = f"{lead}\n" if lead else ""
            for text in _split_sentences(_render_item(item),
                                         lambda t, p=prefix: _tokens(doc, (unit.origin,), p + t),
                                         settings.max_tokens):
                pieces.append(_simple_piece(unit, prefix + text, lead_blocks + (item,)))
            result.events.append(ChunkEvent("sentence_split", doc.document_id, (),
                                            f"list item at ordinal {item.ordinal} split at sentences"))
    if current:
        pieces.append(_simple_piece(unit, render(current), lead_blocks + tuple(current)))
    return pieces


def _split_sentences(text: str, measure, max_tokens: int) -> list[str]:
    """Greedy sentence packing. A single sentence over the limit is split on words as a last resort."""
    sentences = [s for s in _SENTENCE_END.split(text) if s.strip()]
    out: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if measure(candidate) <= max_tokens:
            current = candidate
            continue
        if current:
            out.append(current)
        if measure(sentence) <= max_tokens:
            current = sentence
            continue
        current = ""
        for word in sentence.split():
            candidate = f"{current} {word}".strip()
            if current and measure(candidate) > max_tokens:
                out.append(current)
                current = word
            else:
                current = candidate
    if current:
        out.append(current)
    return out


# ---------------------------------------------------------------------------
# Chunk records


def _chunk_id(doc_id: str, id_range: tuple[int, int], part: int | None) -> str:
    base = f"{doc_id}#{id_range[0]:04d}-{id_range[1]:04d}"
    return f"{base}.p{part}" if part is not None else base


def _kind(unit_kinds: frozenset[UnitKind]) -> ChunkKind:
    if len(unit_kinds) > 1:
        return "mixed"
    return {"paragraph": "prose", "list": "list", "table": "table"}[next(iter(unit_kinds))]  # type: ignore[return-value]


def _make_chunk(doc: DocumentEntry, piece: _Piece) -> Chunk:
    section_path = _section_path(piece.origins)
    embed_text = _embed_text(doc, section_path, piece.text)
    pages = [b.page for b in piece.blocks if b.page is not None]
    return Chunk(
        chunk_id=_chunk_id(doc.document_id, piece.id_range, piece.part),
        document_id=doc.document_id,
        document_name=doc.title,
        publisher=doc.publisher,
        year=doc.year,
        section_path=section_path,
        section=section_path[-1] if section_path else doc.title,
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        ordinals=tuple(sorted({b.ordinal for b in piece.blocks})),
        kind=_kind(piece.unit_kinds),
        text=piece.text,
        embed_text=embed_text,
        token_count=count_tokens(embed_text),
        table_labels=piece.table_labels,
    )
