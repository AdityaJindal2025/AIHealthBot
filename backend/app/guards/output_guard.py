"""Output guard: runs after validation over `answer` and every `claims[].text` (AP §6.3)."""

import re

from app.guards.matching import ALLOWED, GuardResult, evaluate
from app.guards.normalize import normalize
from app.guards.rules import CONDITIONS, MEDICATIONS, OUTPUT_RULES, Category
from app.schemas.model_output import AssistantOutput

__all__ = ["GuardResult", "check_output", "detect_model_decline"]

MODEL_DECLINE_RULE_ID = "OUT-MODEL-01"

# Sentences where the model is refusing ("I can't tell you your ideal weight…") are not
# leaks, so they are skipped before matching (EC SCOPE-20).
_REFUSAL = re.compile(
    r"\b(?:can't|cannot|can not|won't|will not|unable to|not able to|not in a position to|don't provide"
    r"|do not provide|don't give|do not give|not something i can|i'm not able|isn't something i can"
    r"|shouldn't give|not appropriate for me)\b"
)
_REFERRAL = re.compile(
    r"\b(?:registered dietitian|dietitian|dietician|nutritionist|doctor|gp|physician|pharmacist"
    r"|healthcare (?:provider|professional)|health care (?:provider|professional)|medical professional)\b"
)
_SENTENCE = re.compile(r"[^.?!\n]+[.?!]?")


def _without_refusal_sentences(text: str) -> str:
    kept = [s for s in _SENTENCE.findall(text) if not _REFUSAL.search(s)]
    return " ".join(s.strip() for s in kept)


def check_output(output: AssistantOutput) -> GuardResult:
    for text in [output.answer, *(c.text for c in output.claims)]:
        result = evaluate(OUTPUT_RULES, _without_refusal_sentences(normalize(text)))
        if not result.allowed:
            return result
    return ALLOWED


def detect_model_decline(output: AssistantOutput, user_message: str) -> GuardResult:
    """Recognise the model declining by itself, so it is reported as `declined` (EC SCOPE-12).

    A model decline has no claims, a refusal phrase and a referral to a professional.
    Off-domain redirects have no referral, so they stay `in_scope`.
    """
    answer = normalize(output.answer)
    if output.claims or not _REFUSAL.search(answer) or not _REFERRAL.search(answer):
        return ALLOWED
    return GuardResult(
        allowed=False,
        category=_infer_category(normalize(user_message) + " " + answer),
        rule_id=MODEL_DECLINE_RULE_ID,
        matched_rules=[MODEL_DECLINE_RULE_ID],
    )


_MEDICAL_TERMS = re.compile(
    rf"\b(?:{CONDITIONS}|{MEDICATIONS}|pharmacist|medical|diagnos\w*|treat\w*|health condition)\b"
)


def _infer_category(text: str) -> Category:
    # "doctor" is not a signal: the target referral also names one.
    if _MEDICAL_TERMS.search(text):
        return "medical_advice"
    if re.search(r"\b(?:weigh|weight|bmi)\b", text):
        return "weight_target"
    if re.search(r"\bcalorie", text):
        return "calorie_target"
    return "medical_advice"
