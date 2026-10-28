"""Themes: named groups of registry documents, offered as the "Select theme" filter.

`corpus/themes.json` lists each theme's id, name, description and `document_ids`. A theme
restricts retrieval to its documents, the way a document filter restricts it to one.
Every theme must name at least one registry document, and no document id may be unknown:
the file is checked when it is loaded, so a typo fails loudly instead of silently
searching nothing.
"""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import get_settings

THEMES_FILE = "themes.json"
_ID = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_FIELDS = {"theme_id", "name", "description", "document_ids"}


class ThemeError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Theme:
    theme_id: str
    name: str
    description: str
    document_ids: tuple[str, ...]


def load_themes(corpus_dir: Path, known_document_ids: set[str]) -> list[Theme]:
    """Read and check `themes.json`. A missing file means no themes (the filter is hidden)."""
    path = corpus_dir / THEMES_FILE
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ThemeError([f"{THEMES_FILE}: invalid JSON ({e})"]) from e
    if not isinstance(entries, list):
        raise ThemeError([f"{THEMES_FILE}: must be a list of themes"])

    problems: list[str] = []
    themes: list[Theme] = []
    seen: set[str] = set()
    for i, e in enumerate(entries):
        where = f"{THEMES_FILE}: entry {i}"
        if not isinstance(e, dict) or set(e) != _FIELDS:
            problems.append(f"{where}: needs exactly the fields {sorted(_FIELDS)}")
            continue
        theme_id, docs = e["theme_id"], e["document_ids"]
        if not isinstance(theme_id, str) or not _ID.match(theme_id):
            problems.append(f"{where}: theme_id must be lowercase-hyphenated")
        elif theme_id in seen:
            problems.append(f"{where}: duplicate theme_id {theme_id!r}")
        seen.add(theme_id)
        if not isinstance(e["name"], str) or not e["name"].strip():
            problems.append(f"{where}: name is empty")
        if not isinstance(docs, list) or not docs or not all(isinstance(d, str) for d in docs):
            problems.append(f"{where}: document_ids must be a non-empty list of document ids")
            continue
        unknown = sorted(set(docs) - known_document_ids)
        if unknown:
            problems.append(f"{where}: unknown document_ids {unknown}")
        themes.append(Theme(theme_id, e["name"].strip(), str(e["description"]).strip(), tuple(dict.fromkeys(docs))))
    if problems:
        raise ThemeError(problems)
    return themes


@lru_cache(maxsize=4)
def _cached(corpus_dir: str, known: frozenset[str]) -> tuple[Theme, ...]:
    return tuple(load_themes(Path(corpus_dir), set(known)))


def get_themes(known_document_ids: set[str]) -> list[Theme]:
    """The themes for the configured corpus, checked against the documents in the index.
    Before the index is built there are no documents, so there are no themes either."""
    if not known_document_ids:
        return []
    return list(_cached(get_settings().CORPUS_DIR, frozenset(known_document_ids)))
