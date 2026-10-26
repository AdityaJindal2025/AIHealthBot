import json
import os
from collections import defaultdict
from pathlib import Path

import pytest

from app.config import DEFAULT_CORPUS_DIR
from app.rag.chunker import ChunkSettings, chunk_corpus
from app.rag.corpus import Block, Corpus, DocumentEntry, load_corpus
from app.rag.tokens import count_tokens

FIXTURE = Path(__file__).parent / "fixtures" / "corpus"
SNAPSHOT = Path(__file__).parent / "snapshots" / "chunks.json"
SETTINGS = ChunkSettings()


@pytest.fixture(scope="module")
def real_corpus():
    return load_corpus(DEFAULT_CORPUS_DIR, allow_unverified=True)


@pytest.fixture(scope="module")
def real_result(real_corpus):
    return chunk_corpus(real_corpus, SETTINGS)


@pytest.fixture(scope="module")
def fixture_chunks():
    return chunk_corpus(load_corpus(FIXTURE, allow_unverified=False), SETTINGS).chunks


def _doc(doc_id: str = "doc") -> DocumentEntry:
    return DocumentEntry(doc_id, "Test Document", "Test Publisher", "TP", 2020, "https://example.org", (), (),
                         "Test", "2026-10-26")


def _corpus(blocks: list[Block]) -> Corpus:
    by_doc: dict[str, list[Block]] = defaultdict(list)
    for b in blocks:
        by_doc[b.document_id].append(b)
    return Corpus(documents={d: _doc(d) for d in by_doc}, blocks_by_doc=dict(by_doc))


class _Builder:
    """Builds a block list with contiguous ordinals for synthetic tests."""

    def __init__(self, doc_id: str = "doc") -> None:
        self.doc_id = doc_id
        self.blocks: list[Block] = []

    def add(self, type_: str, text: str, path: tuple[str, ...], **kw) -> "_Builder":
        self.blocks.append(Block(self.doc_id, len(self.blocks), type_, text, path, **kw))  # type: ignore[arg-type]
        return self

    def heading(self, text: str, path: tuple[str, ...], level: int) -> "_Builder":
        return self.add("heading", text, path, level=level)


# --- Fixture corpus -----------------------------------------------------------------


def test_fixture_chunks(fixture_chunks):
    by_id = {c.chunk_id: c for c in fixture_chunks}
    alpha = [c for c in fixture_chunks if c.document_id == "alpha-safety"]
    # Intro paragraph; fridge list with lead-in; the tiny "Note" section merged into "Freezer";
    # the Cooking section's paragraph (the heading-only "Cooking" section gives no chunk).
    assert [c.chunk_id for c in alpha] == [
        "alpha-safety#0001-0001", "alpha-safety#0003-0006", "alpha-safety#0008-0011", "alpha-safety#0014-0014",
    ]

    fridge = by_id["alpha-safety#0003-0006"]
    assert fridge.kind == "list"
    assert fridge.text.startswith("Follow these rules for your fridge:\n- Keep your fridge at 5°C or below,")
    assert fridge.section_path == ("Alpha Food Safety Guide", "Fridge")
    assert fridge.page_start == fridge.page_end == 2

    merged = by_id["alpha-safety#0008-0011"]
    assert merged.section == "Note; Freezer"
    assert merged.section_path == ("Alpha Food Safety Guide", "Note; Freezer")
    assert "**Note**\n\nLabel leftovers with the date." in merged.text
    table = "Storage Chart\n| Food | Fridge | Freezer |\n| --- | --- | --- |\n| Cooked rice | 1 day | 1 month |"
    assert table in merged.text
    assert merged.kind == "mixed"
    assert merged.table_labels == ("Storage Chart :: Food | Fridge | Freezer",)

    no_page = by_id["alpha-safety#0014-0014"]
    assert no_page.page_start is None and no_page.page_end is None


def test_chunk_metadata_comes_from_registry(fixture_chunks):
    chunk = next(c for c in fixture_chunks if c.document_id == "gamma-salt")
    assert (chunk.document_name, chunk.publisher, chunk.year) == ("Gamma Salt Guidance", "Gamma Organization", 2020)
    assert chunk.embed_text == "Gamma Salt Guidance — Salt\n\nAdults should eat less than 5 g of salt a day."
    assert chunk.token_count == count_tokens(chunk.embed_text)


# --- Synthetic structure cases -------------------------------------------------------


def test_tiny_section_does_not_merge_across_level_1_or_2_heading():
    b = _Builder()
    b.heading("Parent", ("Parent",), 1)
    b.heading("Tiny", ("Parent", "Tiny"), 3).add("paragraph", "Short.", ("Parent", "Tiny"))
    b.heading("Big", ("Parent", "Big"), 2).add("paragraph", "Next section text.", ("Parent", "Big"))
    chunks = chunk_corpus(_corpus(b.blocks), SETTINGS).chunks
    assert [c.section for c in chunks] == ["Tiny", "Big"]


def test_tiny_section_does_not_merge_with_a_different_parent():
    b = _Builder()
    b.heading("Tiny", ("A", "Tiny"), 3).add("paragraph", "Short.", ("A", "Tiny"))
    b.heading("Other", ("B", "Other"), 3).add("paragraph", "Other parent.", ("B", "Other"))
    chunks = chunk_corpus(_corpus(b.blocks), SETTINGS).chunks
    assert [c.section_path for c in chunks] == [("A", "Tiny"), ("B", "Other")]


def test_top_level_tiny_sections_do_not_merge():
    b = _Builder()
    b.heading("One", ("One",), 4).add("paragraph", "Short.", ("One",))
    b.heading("Two", ("Two",), 4).add("paragraph", "Also short.", ("Two",))
    assert len(chunk_corpus(_corpus(b.blocks), SETTINGS).chunks) == 2


def test_merges_never_cross_documents():
    a = _Builder("doc-a").heading("Tiny", ("P", "Tiny"), 3).add("paragraph", "Short.", ("P", "Tiny"))
    b = _Builder("doc-b").heading("Next", ("P", "Next"), 3).add("paragraph", "Short too.", ("P", "Next"))
    chunks = chunk_corpus(_corpus(a.blocks + b.blocks), SETTINGS).chunks
    assert [(c.document_id, c.section) for c in chunks] == [("doc-a", "Tiny"), ("doc-b", "Next")]


def test_oversize_table_split_by_row_with_header_repeated():
    rows = tuple((f"Food item {i}", f"Keep for {i} days in a covered container on a low shelf of the fridge")
                 for i in range(60))
    b = _Builder().add("table", "", ("Charts",), caption="Big Chart", header=("Food", "Fridge"), rows=rows)
    result = chunk_corpus(_corpus(b.blocks), SETTINGS)
    parts = result.chunks
    assert len(parts) > 1
    n = len(parts)
    seen_rows = []
    for i, part in enumerate(parts, start=1):
        assert part.chunk_id == f"doc#0000-0000.p{i}"
        lines = part.text.split("\n")
        assert lines[0] == f"Big Chart (part {i} of {n})"
        assert lines[1:3] == ["| Food | Fridge |", "| --- | --- |"]
        assert part.token_count <= SETTINGS.max_tokens
        seen_rows += lines[3:]
    # Every row appears exactly once, whole, and in order: no row is cut.
    assert seen_rows == [f"| {a} | {c} |" for a, c in rows]
    assert [e.kind for e in result.events] == ["table_split"]


def test_oversize_list_split_between_items_with_lead_in_repeated():
    b = _Builder().add("paragraph", "Follow these tips:", ("Tips",))
    for i in range(80):
        b.add("list_item", f"{i + 1}. Tip number {i + 1} explains one way to keep food safe at home.", ("Tips",))
    result = chunk_corpus(_corpus(b.blocks), SETTINGS)
    parts = result.chunks
    assert len(parts) > 1
    items = []
    for part in parts:
        lines = part.text.split("\n")
        assert lines[0] == "Follow these tips:"
        assert part.token_count <= SETTINGS.max_tokens
        assert 0 in part.ordinals  # the lead-in block is part of every piece
        items += lines[1:]
    assert items == [f"{i + 1}. Tip number {i + 1} explains one way to keep food safe at home." for i in range(80)]
    assert [e.kind for e in result.events] == ["list_split"]


def test_oversize_paragraph_split_at_sentences_and_flagged():
    sentence = "Wash your hands with soap and water before handling food and after touching raw meat."
    b = _Builder().add("paragraph", " ".join([sentence] * 60), ("Hygiene",))
    result = chunk_corpus(_corpus(b.blocks), SETTINGS)
    assert len(result.chunks) > 1
    for chunk in result.chunks:
        assert chunk.text.endswith(".")
        assert chunk.token_count <= SETTINGS.max_tokens
    assert [e.kind for e in result.events] == ["sentence_split"]


def test_short_units_are_packed_together_up_to_target():
    b = _Builder()
    for i in range(30):
        b.add("paragraph", f"Paragraph {i} gives a short piece of food safety advice for the kitchen.", ("S",))
    chunks = chunk_corpus(_corpus(b.blocks), SETTINGS).chunks
    assert 1 < len(chunks) < 30
    assert all(c.token_count <= SETTINGS.max_tokens for c in chunks)


# --- Real corpus ---------------------------------------------------------------------


def test_real_corpus_sizes(real_result):
    chunks = real_result.chunks
    assert 150 <= len(chunks) <= 250
    assert all(c.token_count <= SETTINGS.max_tokens for c in chunks)
    assert all(c.token_count == count_tokens(c.embed_text) for c in chunks)


def test_real_corpus_ids_are_unique_and_stable(real_corpus, real_result):
    ids = [c.chunk_id for c in real_result.chunks]
    assert len(ids) == len(set(ids))
    again = chunk_corpus(real_corpus, SETTINGS).chunks
    assert [(c.chunk_id, c.text) for c in again] == [(c.chunk_id, c.text) for c in real_result.chunks]


def test_every_content_block_is_in_exactly_one_chunk(real_corpus, real_result):
    owners: dict[tuple[str, int], set[str]] = defaultdict(set)
    for c in real_result.chunks:
        base = c.chunk_id.split(".p")[0]  # parts of one split unit count as one owner
        for o in c.ordinals:
            owners[(c.document_id, o)].add(base)
    for doc_id, blocks in real_corpus.blocks_by_doc.items():
        for b in blocks:
            key = (doc_id, b.ordinal)
            if b.type == "heading":
                assert key not in owners, f"heading {key} became chunk text"
            else:
                assert len(owners[key]) == 1, f"block {key} is in {owners[key] or 'no chunk'}"


def test_no_table_or_list_is_cut_mid_row_or_item(real_corpus, real_result):
    tables = {(d, b.ordinal): b for d, bs in real_corpus.blocks_by_doc.items() for b in bs if b.type == "table"}
    for chunk in real_result.chunks:
        for o in chunk.ordinals:
            table = tables.get((chunk.document_id, o))
            if table is None:
                continue
            row_lines = [ln for ln in chunk.text.split("\n") if ln.startswith("| ") and "| --- |" not in ln]
            header_line = "| " + " | ".join(" ".join(h.split()) for h in table.header) + " |"
            assert header_line in chunk.text, f"{chunk.chunk_id} is missing its table header"
            # Every row line in the chunk is a complete row with the header's cell count.
            for line in row_lines:
                assert line.count(" | ") + 1 == len(table.header) or line == header_line, (chunk.chunk_id, line)
    for chunk in real_result.chunks:
        if chunk.kind == "list" and ".p" in chunk.chunk_id:
            assert not chunk.text.rstrip().endswith((",", ";", " and", " or"))


def test_snapshot_of_chunk_ids(real_result):
    current: dict[str, list[str]] = defaultdict(list)
    for c in real_result.chunks:
        current[c.document_id].append(c.chunk_id)
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
    expected = json.loads(SNAPSHOT.read_text())
    assert dict(current) == expected, (
        "chunk IDs changed: if this is intended, run `UPDATE_SNAPSHOTS=1 pytest tests/test_chunker.py`, "
        "regenerate corpus/build_report.md and commit both"
    )
