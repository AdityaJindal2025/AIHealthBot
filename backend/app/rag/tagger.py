"""Marks chunks whose content is itself out of scope (FPS §4.5, FAP §10.3).

The corpus contains material that becomes a calorie or weight target the moment it is
relayed to a person, such as the Eatwell Guide's table of daily energy requirements by
age. Retrieving that text does not permit the assistant to repeat it. A tagged chunk is
declined if it is the top hit and withheld from the model otherwise (Phase 4/7).

Rules are data, like `guards/rules.py`, so each one is reviewable and testable. Every
tagged chunk is listed in `build_report.md` with the rule that tagged it, so over-tagging
is visible. Rules are deliberately narrow: WHO's sugar guidance mentions "a person of
healthy body weight consuming about 2000 calories per day" as a reference point for a
percentage, and that recommendation must stay answerable.
"""

import re
from dataclasses import dataclass, replace
from typing import Literal

from app.rag.chunker import Chunk

RestrictedCategory = Literal["calorie_target", "weight_target"]


@dataclass(frozen=True)
class TagRule:
    id: str
    category: RestrictedCategory
    target: Literal["table", "text"]  # table: caption + header of each table; text: the chunk text
    pattern: re.Pattern[str]
    description: str


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_NUM = r"\d[\d,.]*"

TAG_RULES: tuple[TagRule, ...] = (
    TagRule(
        id="RET-CAL-01",
        category="calorie_target",
        target="table",
        pattern=_p(r"\benergy\s+requirements?\b|\b(kcal|calories|kilocalories)\s*(per|a|/)\s*day\b"),
        description="Table of energy requirements or daily calorie amounts",
    ),
    TagRule(
        id="RET-CAL-02",
        category="calorie_target",
        target="text",
        pattern=_p(
            rf"\b(need|needs|requirements?|recommended|should\s+(eat|consume|have))\b[^.]{{0,80}}?\b{_NUM}\s*"
            rf"(kcal|calories|kilocalories|kj)\b"
            rf"|\b{_NUM}\s*(kcal|calories|kilocalories)\b[^.]{{0,40}}?\b(for\s+(men|women|boys|girls|adults|children)"
            rf"|a\s+day\s+for)\b"
        ),
        description="Text stating how many calories someone needs",
    ),
    TagRule(
        id="RET-WT-01",
        category="weight_target",
        target="text",
        pattern=_p(
            rf"\b(healthy|ideal|target|recommended|normal)\s+(body\s+)?(weight|bmi)\b[^.]{{0,60}}?"
            rf"\b{_NUM}\s*(kg|kilograms?|lbs?|pounds|stone|kg/m2|kg/m²)\b"
            rf"|\bbmi\b[^.]{{0,40}}?\b\d{{2}}(\.\d)?\s*(to|-|–|and)\s*\d{{2}}(\.\d)?\b"
        ),
        description="Text giving a weight or BMI range as a target",
    ),
)


def match_rule(chunk: Chunk) -> TagRule | None:
    for rule in TAG_RULES:
        haystacks = chunk.table_labels if rule.target == "table" else (chunk.text,)
        if any(rule.pattern.search(h) for h in haystacks):
            return rule
    return None


def tag_chunks(chunks: list[Chunk]) -> list[Chunk]:
    tagged = []
    for chunk in chunks:
        rule = match_rule(chunk)
        if rule is not None:
            chunk = replace(chunk, restricted_category=rule.category, restricted_rule_id=rule.id)
        tagged.append(chunk)
    return tagged
