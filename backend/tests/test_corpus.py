import json
import shutil
from pathlib import Path

import pytest

from app.config import DEFAULT_CORPUS_DIR
from app.rag.corpus import CorpusError, load_corpus

FIXTURE = Path(__file__).parent / "fixtures" / "corpus"


@pytest.fixture
def corpus_dir(tmp_path):
    """A writable copy of the fixture corpus, so each test can break it in one way."""
    target = tmp_path / "corpus"
    shutil.copytree(FIXTURE, target)
    return target


def _blocks(path: Path) -> list[dict]:
    return [json.loads(line) for line in (path / "blocks.jsonl").read_text().splitlines() if line.strip()]


def _write_blocks(path: Path, blocks: list[dict]) -> None:
    (path / "blocks.jsonl").write_text("".join(json.dumps(b, ensure_ascii=False) + "\n" for b in blocks))


def _registry(path: Path) -> list[dict]:
    return json.loads((path / "documents.json").read_text())


def _write_registry(path: Path, entries: list[dict]) -> None:
    (path / "documents.json").write_text(json.dumps(entries))


def _problems(path: Path, *, allow_unverified: bool = False) -> list[str]:
    with pytest.raises(CorpusError) as err:
        load_corpus(path, allow_unverified=allow_unverified)
    return err.value.problems


def test_real_corpus_loads_in_development_mode():
    corpus = load_corpus(DEFAULT_CORPUS_DIR, allow_unverified=True)
    assert len(corpus.documents) == 7
    assert corpus.block_count == 1001
    assert sum(1 for blocks in corpus.blocks_by_doc.values() for b in blocks if b.page is None) == 48


def test_fixture_corpus_loads_in_production_mode():
    corpus = load_corpus(FIXTURE, allow_unverified=False)
    assert len(corpus.documents) == 5
    assert [b.ordinal for b in corpus.blocks_by_doc["alpha-safety"]] == list(range(15))
    table = corpus.blocks_by_doc["alpha-safety"][11]
    assert table.header == ("Food", "Fridge", "Freezer") and len(table.rows) == 3


def test_real_registry_is_verified_for_production():
    # Every citation shows year and link (FPS §4.3), so the committed registry must load in production
    # mode. A new or edited entry needs the same verification (corpus/README.md).
    corpus = load_corpus(DEFAULT_CORPUS_DIR, allow_unverified=False)
    for doc in corpus.documents.values():
        assert doc.verified and doc.year and doc.url and doc.url.startswith("https://"), doc.document_id


def test_duplicate_ordinal(corpus_dir):
    blocks = _blocks(corpus_dir)
    blocks[2]["ordinal"] = 1
    _write_blocks(corpus_dir, blocks)
    problems = _problems(corpus_dir)
    assert "alpha-safety: duplicate ordinal 1" in problems
    assert "alpha-safety: missing ordinal 2 (ordinals must run 0..n-1 without gaps)" in problems


def test_missing_ordinal(corpus_dir):
    blocks = [b for b in _blocks(corpus_dir) if not (b["document_id"] == "alpha-safety" and b["ordinal"] == 5)]
    _write_blocks(corpus_dir, blocks)
    problems = _problems(corpus_dir)
    assert any("alpha-safety: missing ordinal 5" in p for p in problems)


def test_blocks_without_registry_entry(corpus_dir):
    _write_registry(corpus_dir, [e for e in _registry(corpus_dir) if e["document_id"] != "gamma-salt"])
    problems = _problems(corpus_dir)
    assert "gamma-salt: has blocks but no registry entry" in problems


def test_registry_entry_without_blocks(corpus_dir):
    _write_blocks(corpus_dir, [b for b in _blocks(corpus_dir) if b["document_id"] != "gamma-salt"])
    problems = _problems(corpus_dir)
    assert "gamma-salt: registry entry has no blocks" in problems
    assert any("corpus has 4 documents" in p for p in problems)


def test_table_row_with_wrong_cell_count(corpus_dir):
    blocks = _blocks(corpus_dir)
    blocks[11]["rows"][1] = ["Soup", "3 to 4 days"]
    _write_blocks(corpus_dir, blocks)
    problems = _problems(corpus_dir)
    assert "alpha-safety ordinal 11: table row 1 has 2 cells, header has 3" in problems


def test_table_without_header(corpus_dir):
    blocks = _blocks(corpus_dir)
    del blocks[11]["header"]
    _write_blocks(corpus_dir, blocks)
    assert "alpha-safety ordinal 11: table needs a non-empty header and rows" in _problems(corpus_dir)


def test_unverified_entry_refused_in_production(corpus_dir):
    entries = _registry(corpus_dir)
    entries[0]["verified_by"] = ""
    _write_registry(corpus_dir, entries)
    assert "documents.json: alpha-safety: not verified (verified_by is empty)" in _problems(corpus_dir)
    load_corpus(corpus_dir, allow_unverified=True)  # fine for local development


def test_missing_year_and_url_refused_in_production(corpus_dir):
    entries = _registry(corpus_dir)
    entries[0]["year"] = None
    entries[0]["url"] = None
    _write_registry(corpus_dir, entries)
    problems = _problems(corpus_dir)
    assert "documents.json: alpha-safety: year is missing" in problems
    assert "documents.json: alpha-safety: url is missing" in problems
    corpus = load_corpus(corpus_dir, allow_unverified=True)
    assert corpus.documents["alpha-safety"].year is None


@pytest.mark.parametrize("field, value, message", [
    ("year", "2020", "year must be an integer year"),
    ("year", True, "year must be an integer year"),
    ("url", "http://example.org/x", "url must be an https:// URL"),
])
def test_malformed_year_or_url_refused_even_in_development(corpus_dir, field, value, message):
    entries = _registry(corpus_dir)
    entries[0][field] = value
    _write_registry(corpus_dir, entries)
    assert any(message in p for p in _problems(corpus_dir, allow_unverified=True))


def test_unknown_and_missing_registry_fields(corpus_dir):
    entries = _registry(corpus_dir)
    entries[0]["notes"] = "x"
    del entries[1]["publisher"]
    _write_registry(corpus_dir, entries)
    problems = _problems(corpus_dir)
    assert "documents.json: alpha-safety: unknown fields ['notes']" in problems
    assert "documents.json: beta-diet: missing fields ['publisher']" in problems


def test_aliases_must_be_lowercase(corpus_dir):
    entries = _registry(corpus_dir)
    entries[0]["aliases"] = ["Alpha Guide"]
    _write_registry(corpus_dir, entries)
    assert any("aliases must be a list of non-empty lowercase strings" in p for p in _problems(corpus_dir))


@pytest.mark.parametrize("keep", [4, 8])
def test_document_count_must_be_5_to_7(corpus_dir, keep):
    blocks, entries = _blocks(corpus_dir), _registry(corpus_dir)
    if keep == 4:
        blocks = [b for b in blocks if b["document_id"] != "gamma-salt"]
        entries = [e for e in entries if e["document_id"] != "gamma-salt"]
    else:
        for i in range(3):
            doc_id = f"extra-{i}"
            blocks.append({"document_id": doc_id, "ordinal": 0, "type": "paragraph", "text": "x", "heading_path": []})
            entries.append({**entries[0], "document_id": doc_id})
    _write_blocks(corpus_dir, blocks)
    _write_registry(corpus_dir, entries)
    assert any(f"corpus has {keep} documents; it must have 5 to 7" in p for p in _problems(corpus_dir))


def test_invalid_json_line_and_unknown_type_are_both_reported(corpus_dir):
    path = corpus_dir / "blocks.jsonl"
    lines = path.read_text().splitlines()
    lines[1] = lines[1].replace('"type": "paragraph"', '"type": "figure"')
    lines.append("{not json")
    path.write_text("\n".join(lines) + "\n")
    problems = _problems(corpus_dir)
    assert any("unknown block type 'figure'" in p for p in problems)
    assert any("invalid JSON" in p for p in problems)
