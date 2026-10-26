import re

import pytest

from app.guards.output_guard import check_output
from app.rag.citations import ValidClaim, to_source
from app.rag.composer import MULTI_DOCUMENT_LEAD, compose_answer, compose_not_covered
from app.rag.retriever import RetrievedChunk
from app.schemas.api import SearchedDocument
from app.schemas.model_output import GroundedClaim


def chunk(label, doc, name, publisher, year=2016):
    return RetrievedChunk(label=label, rank=1, chunk_id=f"{doc}#{label}", document_id=doc, document_name=name,
                          publisher=publisher, publisher_short="X", year=year, url="https://example.org",
                          section="S", section_path=("S",), page_start=1, page_end=1, kind="prose", text="t",
                          score=0.8)


EATWELL = ("eatwell-guide", "The Eatwell Guide", "Public Health England")
WHO = ("who-healthy-diet", "Healthy diet (Fact sheet N°394)", "World Health Organization")
FSA = ("fsa-chill", "How to chill, freeze and defrost food safely", "Food Standards Agency")


def valid(text, label, doc, year=2016):
    c = chunk(label, *doc, year=year)
    return ValidClaim(GroundedClaim(text=text, source_label=label), c, to_source(c))


def test_one_document():
    out = compose_answer([valid("Adults should eat no more than 6 g of salt a day.", "S2", EATWELL),
                          valid("Most salt is already in food.", "S4", EATWELL)])
    assert out.answer == (
        "From The Eatwell Guide (Public Health England, 2016):\n"
        "- Adults should eat no more than 6 g of salt a day. [2]\n"
        "- Most salt is already in food. [4]"
    )
    assert [c.source.label for c in out.claims] == ["S2", "S4"]


def test_several_documents_kept_separate_in_first_appearance_order():
    out = compose_answer([
        valid("WHO recommends less than 5 g of salt a day.", "S1", WHO, year=2015),
        valid("Adults should eat no more than 6 g of salt a day.", "S3", EATWELL),
        valid("Salt intake should be reduced.", "S2", WHO, year=2015),
        valid("Cool food quickly.", "S5", FSA, year=None),
    ])
    blocks = out.answer.split("\n\n")
    assert blocks[0] == MULTI_DOCUMENT_LEAD
    assert blocks[1].startswith("Healthy diet (Fact sheet N°394) (World Health Organization, 2015):\n")
    assert blocks[2].startswith("The Eatwell Guide (Public Health England, 2016):\n")
    assert blocks[3].startswith("How to chill, freeze and defrost food safely (Food Standards Agency):\n")
    # Each block holds only its own document's claims; markers match labels.
    assert re.findall(r"\[(\d)\]", blocks[1]) == ["1", "2"]
    assert re.findall(r"\[(\d)\]", blocks[2]) == ["3"]
    # Claims follow the grouped order, so claims[i] is the i-th bullet.
    assert [c.source.label for c in out.claims] == ["S1", "S2", "S3", "S5"]
    assert "agree" not in out.answer.lower() and "better" not in out.answer.lower()


def test_no_claims_is_an_error():
    with pytest.raises(ValueError):
        compose_answer([])


def searched(*docs):
    return [SearchedDocument(document_id=d[0], document_name=d[1], publisher=d[2], year=2016) for d in docs]


def test_not_covered_lists_every_searched_document():
    out = compose_not_covered(searched(EATWELL, WHO, FSA), filtered=False)
    assert out.claims == []
    assert out.answer.startswith("The guidance I searched doesn't cover this. I searched: ")
    for _, name, publisher in (EATWELL, WHO, FSA):
        assert f"{name} ({publisher}, 2016)" in out.answer


def test_not_covered_filtered_names_only_that_document():
    out = compose_not_covered(searched(FSA), filtered=True)
    assert out.answer == ("The guidance I searched doesn't cover this. I searched only How to chill, freeze and "
                          "defrost food safely (Food Standards Agency, 2016), as you asked.")


@pytest.mark.parametrize("text, doc", [
    ("Keep your fridge between 0 and 5°C.", FSA),
    ("Adults should eat no more than 6 g of salt a day.", EATWELL),
    ("Free sugars should be less than 10% of total energy intake.", WHO),
])
def test_composed_answers_pass_the_output_guard(text, doc):
    assert check_output(compose_answer([valid(text, "S1", doc)])).allowed
