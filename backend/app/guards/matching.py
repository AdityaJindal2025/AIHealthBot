"""Rule matching shared by the input and output guards."""

import re
from dataclasses import dataclass, field

from app.guards.rules import CATEGORY_PRIORITY, Category, Rule

_SENTENCE_END = re.compile(r"[.?!\n]")


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    category: Category | None = None
    rule_id: str | None = None
    matched_rules: list[str] = field(default_factory=list)


ALLOWED = GuardResult(allowed=True)


def sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = max((m.end() for m in _SENTENCE_END.finditer(text, 0, start)), default=0)
    right_match = _SENTENCE_END.search(text, end)
    return left, right_match.end() if right_match else len(text)


def rule_matches(rule: Rule, text: str) -> bool:
    """True if the rule matches at some position without an exception cancelling that match.

    The pattern is tried at every start position, so a later clause is still found when an
    earlier, overlapping match was cancelled by an exception (EC SCOPE-05).
    """
    pos = 0
    while pos <= len(text):
        m = rule.pattern.search(text, pos)
        if m is None:
            return False
        if rule.exception_scope == "sentence":
            lo, hi = sentence_bounds(text, m.start(), m.end())
            scope = text[lo:hi]
        else:
            scope = m.group(0)
        if not any(ex.search(scope) for ex in rule.exceptions):
            return True
        pos = m.start() + 1
    return False


def evaluate(rules: list[Rule], text: str) -> GuardResult:
    """Run every rule. One decline with a fixed category priority; every matched rule is recorded (EC SCOPE-27)."""
    matched = [r for r in rules if rule_matches(r, text)]
    if not matched:
        return ALLOWED
    primary = min(matched, key=lambda r: CATEGORY_PRIORITY.index(r.category))
    return GuardResult(
        allowed=False,
        category=primary.category,
        rule_id=primary.id,
        matched_rules=[r.id for r in matched],
    )
