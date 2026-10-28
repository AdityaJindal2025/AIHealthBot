"""Citation checks on every grounded claim, in code (FPS §4.3, FAP §9).

A claim ships only if all checks pass, in this order:

| Reason                | Fails when                                                              |
|-----------------------|-------------------------------------------------------------------------|
| `unknown_label`       | `source_label` is not one of this request's S1..Sk                      |
| `unsupported_number`  | a number in the claim does not appear in the cited chunk                |
| `publisher_mismatch`  | the claim names a publisher other than the cited document's            |
| `blended_attribution` | the claim speaks for several documents or ranks them (OUT-BLEND-*)      |
| `personal_framing`    | population guidance turned into a personal quantity (OUT-PERS-*)       |

A failing claim is dropped and returned in `dropped`, for the caller to record in
`citation_events`; nothing is dropped silently. These checks catch invented labels, invented
numbers and misattribution. They cannot prove that the chunk *means* what the claim says;
that gap is covered by the human citation review in the failure log (FAP §13.4).
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.guards.normalize import normalize
from app.guards.rules import CLAIM_RULES
from app.rag.retriever import RetrievedChunk
from app.schemas.model_output import GroundedClaim, GroundedOutput, Source

DropReason = Literal["unknown_label", "unsupported_number", "publisher_mismatch", "blended_attribution",
                     "personal_framing"]

_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅛": 0.125}
# A number, optionally with thousands separators and a decimal part, or a slash fraction.
_NUMBER = re.compile(r"(\d+)\s*/\s*(\d+)(?![\d/])|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_FRACTION_CHARS = re.compile("[" + "".join(_FRACTIONS) + "]")
# Citation markers and labels are ours, not the source's.
_OWN_MARKERS = re.compile(r"\[\d+\]|\bS\d+\b")
# Acronym aliases (WHO, FSA…) only count in capitals, so "people who eat" is not "WHO".
_ACRONYM_MAX = 5


@dataclass(frozen=True)
class ValidClaim:
    claim: GroundedClaim
    chunk: RetrievedChunk
    source: Source


@dataclass(frozen=True)
class DroppedClaim:
    claim: GroundedClaim
    reason: DropReason
    chunk_id: str | None
    rule_id: str | None = None


@dataclass(frozen=True)
class CitationResult:
    valid: list[ValidClaim]
    dropped: list[DroppedClaim]


@dataclass(frozen=True)
class PublisherInfo:
    document_id: str
    publisher: str
    aliases: tuple[str, ...]


def numbers_in(text: str) -> set[float]:
    """Every number in the text as a normalised value: 1,000 → 1000; ½ and 1/2 → 0.5; 1½ → 1.5.

    Signs are ignored (a range "0-5°C" and "-18°C" use the same dash), and units are ignored:
    the check is that the figure itself comes from the source.
    """
    text = _OWN_MARKERS.sub(" ", text)
    values: set[float] = set()
    # "1½" → 1.5 before the parts are read separately.
    for m in re.finditer(r"(\d+)\s?([½¼¾⅓⅔⅛])", text):
        values.add(round(int(m.group(1)) + _FRACTIONS[m.group(2)], 4))
    for ch in _FRACTION_CHARS.findall(text):
        values.add(round(_FRACTIONS[ch], 4))
    for m in _NUMBER.finditer(text):
        if m.group(1) is not None:
            denominator = int(m.group(2))
            if denominator:
                values.add(round(int(m.group(1)) / denominator, 4))
            values.update({float(m.group(1)), float(m.group(2))})
        else:
            values.add(round(float(m.group(0).replace(",", "")), 4))
    return values


def _claim_numbers(text: str) -> set[float]:
    """Numbers the claim asserts. A slash fraction counts as its value only."""
    text = _OWN_MARKERS.sub(" ", text)
    values: set[float] = set()
    for m in re.finditer(r"(\d+)\s?([½¼¾⅓⅔⅛])", text):
        values.add(round(int(m.group(1)) + _FRACTIONS[m.group(2)], 4))
        text = text.replace(m.group(0), " ")
    for ch in _FRACTION_CHARS.findall(text):
        values.add(round(_FRACTIONS[ch], 4))
    for m in _NUMBER.finditer(text):
        if m.group(1) is not None and int(m.group(2)):
            values.add(round(int(m.group(1)) / int(m.group(2)), 4))
        elif m.group(1) is None:
            values.add(round(float(m.group(0).replace(",", "")), 4))
    return values


def _alias_pattern(alias: str) -> re.Pattern[str]:
    if len(alias) <= _ACRONYM_MAX and " " not in alias:
        return re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias.upper())}(?![A-Za-z0-9])")
    return re.compile(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", re.IGNORECASE)


def check_claims(output: GroundedOutput, label_map: dict[str, RetrievedChunk],
                 publishers: list[PublisherInfo]) -> CitationResult:
    valid: list[ValidClaim] = []
    dropped: list[DroppedClaim] = []
    own_aliases = {p.document_id: set(p.aliases) for p in publishers}
    for claim in output.claims:
        chunk = label_map.get(claim.source_label.strip())
        if chunk is None:
            dropped.append(DroppedClaim(claim, "unknown_label", None))
            continue
        allowed = numbers_in(f"{chunk.text} {chunk.document_name} {chunk.section}")
        if not _claim_numbers(claim.text) <= allowed:
            dropped.append(DroppedClaim(claim, "unsupported_number", chunk.chunk_id))
            continue
        cited_aliases = own_aliases.get(chunk.document_id, set())
        named = {p.publisher for p in publishers for a in p.aliases
                 if a not in cited_aliases and _alias_pattern(a).search(claim.text)}
        if named - {chunk.publisher}:
            dropped.append(DroppedClaim(claim, "publisher_mismatch", chunk.chunk_id))
            continue
        normalised = normalize(claim.text)
        rule = next((r for r in CLAIM_RULES if r.pattern.search(normalised)), None)
        if rule is not None:
            dropped.append(DroppedClaim(claim, rule.reason, chunk.chunk_id, rule.id))
            continue
        valid.append(ValidClaim(claim, chunk, to_source(chunk)))
    return CitationResult(valid, dropped)


def to_source(chunk: RetrievedChunk) -> Source:
    return Source(
        document_id=chunk.document_id,
        document_name=chunk.document_name,
        publisher=chunk.publisher,
        publisher_short=chunk.publisher_short,
        year=chunk.year,
        url=chunk.url,  # type: ignore[arg-type]
        section=chunk.section,
        page=chunk.page_start,
        chunk_id=chunk.chunk_id,
        label=chunk.label,
        excerpt=chunk.text,
    )
