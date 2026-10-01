"""Versioned system prompts. `system_v1.md` -> PROMPT_VERSION=v1 (AP §8)."""

import re
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent
_VERSION_RE = re.compile(r"^v\d+$")


@lru_cache
def load_system_prompt(version: str) -> str:
    if not _VERSION_RE.match(version):
        raise ValueError(f"Invalid PROMPT_VERSION {version!r}; expected e.g. 'v1'")
    path = PROMPTS_DIR / f"system_{version}.md"
    if not path.is_file():
        raise FileNotFoundError(f"System prompt for PROMPT_VERSION={version!r} not found at {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"System prompt {path} is empty")
    return text
