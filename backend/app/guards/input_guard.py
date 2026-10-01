"""Input guard: runs before the model call and decides deterministically (AP §6.2)."""

from dataclasses import replace

from app.guards.matching import ALLOWED, GuardResult, evaluate, rule_matches
from app.guards.normalize import normalize
from app.guards.rules import FOLLOW_UP_RULES, INPUT_RULES, Category

# Follow-up rules only apply to short messages, so a new, unrelated question after a
# decline is not blocked.
FOLLOW_UP_MAX_WORDS = 15

__all__ = ["GuardResult", "check_input"]


def check_input(
    text: str,
    *,
    previous_user_text: str | None = None,
    previous_decline_category: Category | None = None,
) -> GuardResult:
    """Check the new user message.

    - `previous_user_text`: the previous user turn. If the new message alone passes, the two
      are checked together, which catches a target split across turns (EC SCOPE-08).
    - `previous_decline_category`: set when the previous assistant turn was a decline. A short
      follow-up asking for "a rough number" stays declined in that category (EC SCOPE-09).
    """
    current = normalize(text)
    result = evaluate(INPUT_RULES, current)
    if not result.allowed:
        return result

    if previous_decline_category is not None and len(current.split()) <= FOLLOW_UP_MAX_WORDS:
        for rule in FOLLOW_UP_RULES:
            if rule_matches(rule, current):
                return GuardResult(
                    allowed=False,
                    category=previous_decline_category,
                    rule_id=rule.id,
                    matched_rules=[rule.id],
                )

    if previous_user_text:
        combined = evaluate(INPUT_RULES, f"{normalize(previous_user_text)} {current}")
        if not combined.allowed:
            return replace(combined, matched_rules=[f"{r}+prev" for r in combined.matched_rules])

    return ALLOWED
