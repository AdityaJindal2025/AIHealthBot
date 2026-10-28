import pytest

from app.config import DEFAULT_CORPUS_DIR
from app.rag.chunker import Chunk, ChunkSettings, chunk_corpus
from app.rag.corpus import load_corpus
from app.rag.tagger import TAG_RULES, match_rule, tag_chunks


def _chunk(text: str = "", table_labels: tuple[str, ...] = ()) -> Chunk:
    return Chunk("doc#0000-0000", "doc", "Doc", "Pub", 2020, ("S",), "S", None, None, (0,), "prose", text, text,
                 10, table_labels)


# (rule, text or table label, expected rule ID or None). Negatives come from the real corpus where possible.
CASES = [
    ("table", "Daily energy requirements – Males – kcal", "RET-CAL-01"),
    ("table", "Calorie guide :: Activity | kcal per day", "RET-CAL-01"),
    ("table", "Cold Storage Chart :: Product | Refrigerator (40 °F/4.4 °C) | Freezer (0 °F/-17.8 °C)", None),
    ("table", "Age | Recommended maximum free sugars intake | Sugar cubes", None),
    ("table", "Turkey Thawing Chart: Approximate Timelines :: Turkey Size | In the Refrigerator", None),
    ("text", "An average woman needs around 2,000 kcal a day to maintain a healthy weight.", "RET-CAL-02"),
    ("text", "Men should eat about 2500 calories a day.", "RET-CAL-02"),
    ("text", "This is around 2000 kcal for women and 2500 kcal for men.", "RET-CAL-02"),
    # WHO's sugar recommendation uses 2000 calories only as a reference point: it must stay answerable.
    ("text", "Less than 10% of total energy intake from free sugars (2, 7), which is equivalent to 50 g (or about 12 "
             "level tea-spoons) for a person of healthy body weight consuming about 2000 calories per day", None),
    ("text", "Alcohol also contains lots of calories (kcal) and should be limited to no more than 14 units per week.",
     None),
    ("text", "Some people think starchy food is fattening, but gram for gram it contains less than half the calories "
             "of fat.", None),
    ("text", "A healthy BMI for adults is 18.5 to 24.9.", "RET-WT-01"),
    ("text", "Your ideal weight is about 70 kg if you are 1.75 m tall.", "RET-WT-01"),
    ("text", "6. Get active and be a healthy weight", None),
    ("text", "If you’re overweight, then you may need to eat less. Ask your GP for advice about losing weight.", None),
    ("text", "Thaw a 4 to 12 pound turkey in the refrigerator for 1 to 3 days.", None),
]


@pytest.mark.parametrize("target, text, expected", CASES, ids=[c[1][:50] for c in CASES])
def test_rule_case(target, text, expected):
    chunk = _chunk(table_labels=(text,)) if target == "table" else _chunk(text=text)
    rule = match_rule(chunk)
    assert (rule.id if rule else None) == expected


def test_every_rule_has_positive_and_negative_cases():
    for rule in TAG_RULES:
        assert any(e == rule.id for _, _, e in CASES), f"{rule.id} has no positive case"
        assert any(t == rule.target and e is None for t, _, e in CASES), f"{rule.target} rules need negative cases"


def test_rule_ids_are_unique_and_prefixed():
    ids = [r.id for r in TAG_RULES]
    assert len(ids) == len(set(ids))
    assert all(i.startswith(("RET-CAL-", "RET-WT-")) for i in ids)


def test_table_rules_do_not_match_prose():
    # "energy requirements" in prose (FAO/WHO) is not a target table.
    chunk = _chunk(text="Healthy diets balance energy intake with energy requirements, which vary with age.")
    assert match_rule(chunk) is None


@pytest.fixture(scope="module")
def real_tagged():
    corpus = load_corpus(DEFAULT_CORPUS_DIR, allow_unverified=True)
    return tag_chunks(chunk_corpus(corpus, ChunkSettings()).chunks)


def test_energy_requirements_table_is_tagged(real_tagged):
    tagged = [c for c in real_tagged if c.restricted_category]
    energy = [c for c in tagged if 81 in c.ordinals and c.document_id == "eatwell-guide"]
    assert len(energy) == 1
    assert energy[0].restricted_category == "calorie_target"
    assert energy[0].restricted_rule_id == "RET-CAL-01"


@pytest.mark.parametrize("doc_id, ordinal", [
    ("cold-food-storage", 2),    # cold storage chart
    ("kitchen-companion", 232),  # turkey thawing chart
    ("kitchen-companion", 92),   # cold storage chart
    ("eatwell-guide", 71),       # free sugars by age (g/day, not calories)
    ("who-healthy-diet", 17),    # WHO sugar recommendation mentioning 2000 calories
])
def test_ordinary_content_is_not_tagged(real_tagged, doc_id, ordinal):
    chunks = [c for c in real_tagged if c.document_id == doc_id and ordinal in c.ordinals]
    assert chunks
    assert all(c.restricted_category is None for c in chunks)


def test_only_expected_chunks_are_tagged(real_tagged):
    # Any change here must be reviewed in corpus/build_report.md before updating this list.
    assert [c.chunk_id for c in real_tagged if c.restricted_category] == ["eatwell-guide#0079-0081"]
