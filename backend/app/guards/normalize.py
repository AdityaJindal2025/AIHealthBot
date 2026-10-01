"""Text normalisation shared by the input and output guards (AP §6.2 step 1)."""

import re

_QUOTES = str.maketrans({"‘": "'", "’": "'", "′": "'", "“": '"', "”": '"', "″": '"'})

# Common misspellings and light obfuscation (EC SCOPE-03). Misses are recorded, not chased.
_TYPOS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bc[a@]l[o0]r(?:i|1|!)?e?s\b|\bcal(?:ro|or|o)i?e?s\b|\bcalorise\b|\bcalores\b"), "calories"),
    (re.compile(r"\bc[a@]l[o0]r(?:i|1)e\b"), "calorie"),
    (re.compile(r"\bid[e3][a@]l\b"), "ideal"),
    (re.compile(r"\bw[e3][i1]ght\b|\bwieght\b|\bweigth\b"), "weight"),
]

_SPACED_LETTERS = re.compile(r"\b(?:[a-z] ){3,}[a-z]\b")

_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "twenty-five": 25, "thirty": 30,
}
_NUM_WORD_SCALE = re.compile(r"\b(" + "|".join(sorted(_NUM_WORDS, key=len, reverse=True)) + r") (hundred|thousand)\b")


def _num_word_scale(m: re.Match[str]) -> str:
    return str(_NUM_WORDS[m.group(1)] * (100 if m.group(2) == "hundred" else 1000))


def normalize(text: str) -> str:
    t = text.translate(_QUOTES).lower()
    t = _SPACED_LETTERS.sub(lambda m: m.group(0).replace(" ", ""), t)
    for pattern, repl in _TYPOS:
        t = pattern.sub(repl, t)

    # Numbers: "1,500" -> "1500", "1.5k" -> "1500", "fifteen hundred" -> "1500" (EC SCOPE-21).
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
    t = re.sub(r"\b(\d+(?:\.\d+)?)k\b", lambda m: str(int(float(m.group(1)) * 1000)), t)
    t = _NUM_WORD_SCALE.sub(_num_word_scale, t)

    # Energy units.
    t = re.sub(r"\bkcals?\b|\bkilocalories\b|\bcals\b", "calories", t)
    t = re.sub(r"\bkilocalorie\b|\bcal\b", "calorie", t)
    t = re.sub(r"(\d)\s*calories\b", r"\1 calories", t)

    # Weight units.
    t = re.sub(r"(\d)\s*(?:lbs?|pounds?)\b", r"\1 lbs", t)
    t = re.sub(r"(\d)\s*(?:kgs?|kilos?|kilograms?)\b", r"\1 kg", t)
    t = re.sub(r"\b(?:lbs?|pounds)\b", "lbs", t)
    t = re.sub(r"\b(?:kgs|kilos|kilograms?)\b", "kg", t)

    # Height: 5'8", 5' 8", 5ft8, 5 ft 8 in -> "5 ft 8 in"; 170cm -> "170 cm".
    t = re.sub(r"\b(\d)\s*(?:'|ft|feet|foot)\s*(\d{1,2})\s*(?:\"|in(?:ches)?\b)?", r"\1 ft \2 in", t)
    t = re.sub(r"(\d)\s*cm\b", r"\1 cm", t)

    return re.sub(r"\s+", " ", t).strip()
