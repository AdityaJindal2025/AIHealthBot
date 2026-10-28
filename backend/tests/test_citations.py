import pytest

from app.guards.normalize import normalize
from app.guards.rules import CLAIM_RULES
from app.rag.citations import PublisherInfo, check_claims, numbers_in
from app.rag.retriever import RetrievedChunk
from app.schemas.model_output import GroundedClaim, GroundedOutput


def chunk(label, text, doc="who-healthy-diet", publisher="World Health Organization", chunk_id=None):
    return RetrievedChunk(label=label, rank=int(label[1:]), chunk_id=chunk_id or f"{doc}#000{label[1:]}",
                          document_id=doc, document_name=f"{doc} title", publisher=publisher, publisher_short="X",
                          year=2020, url="https://example.org/doc", section="Section", section_path=("Section",),
                          page_start=3, page_end=3, kind="prose", text=text, score=0.8)


WHO = PublisherInfo("who-healthy-diet", "World Health Organization", ("who", "world health organization"))
FSA = PublisherInfo("fsa-chill", "Food Standards Agency", ("fsa", "food standards agency"))
PHE = PublisherInfo("eatwell-guide", "Public Health England", ("phe", "public health england"))
PUBLISHERS = [WHO, FSA, PHE]

S1 = chunk("S1", "Keeping salt intake to less than 5 g per day (equivalent to about one teaspoon) helps prevent "
                 "hypertension. Free sugars should be less than 10% of total energy intake.")
S2 = chunk("S2", "Your fridge should be between 0 and 5°C and your freezer should be around -18°C. "
                 "Cool leftovers within 2 hours.", doc="fsa-chill", publisher="Food Standards Agency")
S3 = chunk("S3", "Store 1,000 g of rice for ½ day. Use 1/2 cup of water. Cook to 165 °F (73.9 °C).",
           doc="eatwell-guide", publisher="Public Health England")
LABELS = {"S1": S1, "S2": S2, "S3": S3}


def run(*claims):
    out = GroundedOutput(coverage="covered", claims=[GroundedClaim(text=t, source_label=lbl) for t, lbl in claims])
    return check_claims(out, LABELS, PUBLISHERS)


def test_valid_claim_passes_all_checks_and_gets_full_source():
    result = run(("WHO recommends keeping salt intake to less than 5 g per day.", "S1"))
    assert not result.dropped
    source = result.valid[0].source
    assert (source.document_id, source.label, source.chunk_id, source.year, source.page) == (
        "who-healthy-diet", "S1", "who-healthy-diet#0001", 2020, 3)
    assert source.excerpt == S1.text


@pytest.mark.parametrize("text, label, reason", [
    ("Salt should be under 5 g a day.", "S9", "unknown_label"),
    ("Salt should be under 6 g a day.", "S1", "unsupported_number"),
    ("The FSA recommends less than 5 g of salt per day.", "S1", "publisher_mismatch"),
    ("Public Health England says free sugars should be less than 10% of total energy intake.", "S1",
     "publisher_mismatch"),
    ("The guidelines say salt should be less than 5 g per day.", "S1", "blended_attribution"),
    ("Experts agree that free sugars should be under 10% of energy.", "S1", "blended_attribution"),
    ("WHO is the most reliable source on salt.", "S1", "blended_attribution"),
    ("You should eat less than 5 g of salt.", "S1", "personal_framing"),
    ("Your daily salt intake should be below one teaspoon.", "S1", "personal_framing"),
])
def test_each_drop_reason(text, label, reason):
    result = run((text, label))
    assert not result.valid
    assert [d.reason for d in result.dropped] == [reason]
    assert result.dropped[0].chunk_id == (None if reason == "unknown_label" else LABELS[label].chunk_id)


def test_valid_and_dropped_claims_are_separated():
    result = run(("Free sugars should be less than 10% of total energy intake.", "S1"),
                 ("A fridge should be between 0 and 5°C.", "S2"),
                 ("Salt should be under 6 g a day.", "S1"))
    assert [v.claim.source_label for v in result.valid] == ["S1", "S2"]
    assert [d.reason for d in result.dropped] == ["unsupported_number"]


def test_number_from_another_chunk_still_fails():
    # 5 is in S1, but this claim cites S3, which does not contain it.
    assert [d.reason for d in run(("Rice keeps for 5 days.", "S3")).dropped] == ["unsupported_number"]


@pytest.mark.parametrize("claim", [
    "Rice can be stored for 0.5 day.",            # ½ in the source
    "Use one half cup, which is 0.5 cup of water.",  # 1/2 in the source
    "Store 1000 g of rice.",                      # 1,000 in the source
    "Cook to 165°F (73.9°C).",                    # spacing differs from the source
    "Cook to 165 degrees F.",
])
def test_number_normalisation(claim):
    assert run((claim, "S3")).valid


def test_percent_and_per_cent_match():
    assert run(("Free sugars should be below 10 per cent of total energy intake.", "S1")).valid


def test_negative_temperatures_and_ranges_match():
    assert run(("A freezer should be around -18°C and a fridge between 0 and 5°C.", "S2")).valid


def test_numbers_in():
    assert numbers_in("1,000 g, ½ cup, 1/4 tsp, 40 °F, -18°C, 1½ cups, 10%") >= {1000, 0.5, 0.25, 40, 18, 1.5, 10}


def test_lowercase_who_is_not_the_publisher():
    assert run(("People who keep salt below 5 g per day lower their risk of hypertension.", "S1")).valid


def test_own_publisher_named_is_fine():
    assert run(("The Food Standards Agency says a fridge should be between 0 and 5°C.", "S2")).valid


def test_food_safety_imperatives_are_not_personal_framing():
    for text in ["Keep your fridge between 0 and 5°C.", "You should cool leftovers within 2 hours."]:
        assert run((text, "S2")).valid, text


# --- claim rules coverage, like the guard rules' coverage test ---------------------------

CLAIM_RULE_CASES = [
    ("OUT-BLEND-01", "the guidelines say adults should eat less salt.", True),
    ("OUT-BLEND-01", "all sources recommend less sugar.", True),
    ("OUT-BLEND-01", "the eatwell guide says adults should eat less salt.", False),
    ("OUT-PERS-01", "you should eat 30 g of fibre a day.", True),
    ("OUT-PERS-01", "you should eat leftovers within 2 days.", False),
    ("OUT-PERS-02", "your daily sugar intake should be low.", True),
    ("OUT-PERS-02", "keep your fridge at 5°c or below.", False),
    ("OUT-PERS-03", "for you, that means 25 g of sugar.", True),
    ("OUT-PERS-03", "adults need less than 5 g of salt a day.", False),
]


@pytest.mark.parametrize("rule_id, text, matches", CLAIM_RULE_CASES)
def test_claim_rule_case(rule_id, text, matches):
    rule = next(r for r in CLAIM_RULES if r.id == rule_id)
    assert bool(rule.pattern.search(normalize(text))) is matches


def test_every_claim_rule_has_positive_and_negative_cases():
    for rule in CLAIM_RULES:
        assert any(r == rule.id and m for r, _, m in CLAIM_RULE_CASES), rule.id
        assert any(r == rule.id and not m for r, _, m in CLAIM_RULE_CASES), rule.id
