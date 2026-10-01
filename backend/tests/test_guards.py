import re
from pathlib import Path

import pytest
import yaml

from app.guards.decline import DECLINE_TEXTS, build_decline
from app.guards.input_guard import check_input
from app.guards.output_guard import check_output, detect_model_decline
from app.guards.rules import ALL_RULES
from app.schemas.model_output import AssistantOutput, Claim

CASES = yaml.safe_load((Path(__file__).parent / "guard_cases.yaml").read_text())


def _run(case):
    if case.get("stage", "input") == "output":
        return check_output(AssistantOutput(answer="General information.", claims=[Claim(text=case["text"])]))
    return check_input(case["text"], previous_user_text=case.get("prev_user"),
                       previous_decline_category=case.get("prev_decline"))


@pytest.mark.parametrize("case", CASES, ids=[c["text"][:60] for c in CASES])
def test_guard_case(case):
    result = _run(case)
    if case["expect"] == "allow":
        assert result.allowed, f"false positive: {result.matched_rules}"
    else:
        assert not result.allowed, "expected a decline"
        assert result.category == case["category"]
        assert case["rule"] in result.matched_rules


def test_at_least_40_cases():
    assert len(CASES) >= 40


def test_every_rule_has_a_positive_case():
    covered = {c["rule"].removesuffix("+prev") for c in CASES if c["expect"] == "decline"}
    missing = [r.id for r in ALL_RULES if r.id not in covered]
    assert not missing, f"rules without a positive case: {missing}"


def test_rule_ids_are_unique():
    ids = [r.id for r in ALL_RULES]
    assert len(ids) == len(set(ids))


def test_output_guard_scans_answer_as_well_as_claims():
    out = AssistantOutput(answer="You should aim for 1,500 calories a day.", claims=[])
    assert not check_output(out).allowed


@pytest.mark.parametrize("category", list(DECLINE_TEXTS))
def test_decline_texts_are_schema_valid_and_digit_free(category):
    out = build_decline(category)
    AssistantOutput.model_validate(out.model_dump(), strict=True)
    assert out.claims == []
    assert not re.search(r"\d", out.answer)
    assert re.search(r"dietitian|doctor|pharmacist", out.answer)
    # Our own declines must not trip the output guard.
    assert check_output(out).allowed


def test_model_self_decline_is_detected():
    out = AssistantOutput(answer="I can't give personal calorie targets. A registered dietitian can help.", claims=[])
    result = detect_model_decline(out, "how much should I eat")
    assert not result.allowed
    assert result.category == "calorie_target"
    assert result.rule_id == "OUT-MODEL-01"


def test_off_domain_redirect_is_not_a_decline():
    out = AssistantOutput(answer="I can only help with questions about food and nutrition.", claims=[])
    assert detect_model_decline(out, "write me a poem").allowed


def test_caveat_in_normal_answer_is_not_a_decline():
    out = AssistantOutput(answer="Oats are high in fibre. I can't give personal advice; a dietitian can.",
                          claims=[Claim(text="Oats are high in fibre.")])
    assert detect_model_decline(out, "are oats healthy").allowed
