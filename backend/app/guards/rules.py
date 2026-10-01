"""Scope rules as data (PS §3.5, AP §6). Every decline traces back to one of these rule IDs.

Patterns run on normalised text (see normalize.py). Two details make them safer than a
plain `re.search`:

- Patterns use lazy quantifiers and are tried at every start position, so the minimal
  match is found for each clause. "Calories in a banana, and how many calories should I
  eat a day?" finds the second clause even though the first is a composition question
  (EC SCOPE-05).
- An exception only cancels the match it overlaps: with `exception_scope="match"` the
  exception must appear inside the matched text; with `"sentence"` it may appear anywhere
  in the same sentence (used for food nouns such as "portion of pasta", EC SCOPE-15).

Category decisions for borderline cases (EC §4.3) are recorded next to the rules.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

Category = Literal["calorie_target", "weight_target", "medical_advice"]
Stage = Literal["input", "output"]

# Highest priority first (EC SCOPE-27).
CATEGORY_PRIORITY: list[Category] = ["medical_advice", "weight_target", "calorie_target"]


@dataclass(frozen=True)
class Rule:
    id: str
    category: Category
    stage: Stage
    pattern: re.Pattern[str]
    exceptions: list[re.Pattern[str]] = field(default_factory=list)
    exception_scope: Literal["match", "sentence"] = "match"


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


# --- shared term groups ---------------------------------------------------------------------

SUBJECT = r"(?:i|we|he|she|they|you|my [\w-]+(?: [\w-]+)?|a [\w-]+(?: [\w-]+)?|an [\w-]+|someone|somebody)"

CONDITIONS = (
    r"(?:pre-?diabet\w*|diabet\w*|hypertension|high blood pressure|blood pressure|pregnan\w*|breastfeeding"
    r"|kidney (?:disease|stones?|problems?|failure)|kidneys|renal|liver disease|fatty liver|ibs|crohn'?s"
    r"|colitis|cancer|chemo\w*|allerg\w*|intoleran\w*|celiac|coeliac|cholesterol|pcos|gout|an(?:a)?emi\w*"
    r"|thyroid|hypothyroid\w*|hyperthyroid\w*|heart (?:disease|condition|failure|problems?)|eating disorder"
    r"|anorexi\w*|bulimi\w*|gerd|acid reflux|reflux|epilep\w*|arthritis|osteoporosis|insulin resistan\w*"
    r"|gastritis|ulcers?|depression|adhd|migraines?)"
)

ADVICE = (
    r"(?:should (?:i|he|she|they|we|my [\w-]+)|can (?:i|he|she|they|we|my [\w-]+)|could (?:i|he|she)"
    r"|is (?:it|this|that|the [\w-]+) (?:\w+ )?(?:safe|ok|okay|bad|good|dangerous|fine)"
    r"|are (?:they|these|those) (?:\w+ )?(?:safe|ok|okay|bad|good)"
    r"|(?:safe|ok|okay|good|best|bad|healthy|recommended|worst|dangerous) (?:for|with)"
    r"|treat\w*|cures?|reverse|manag\w*|control (?:my|his|her|their|blood)|stop taking|dose|dosage"
    r"|what should|(?:should|can|must) (?:\w+ )?(?:eat|avoid|drink)|foods? to avoid|avoid eating|allowed to)"
)

MEDICATIONS = (
    r"(?:pills?|medications?|medicines?|meds|prescriptions?|ibuprofen|paracetamol|acetaminophen|aspirin"
    r"|statins?|metformin|warfarin|blood thinners?|antibiotics?|antidepressants?|ssris?|maois?"
    r"|levothyroxine|birth control|contraceptives?|lithium|chemotherapy|steroids?|prednisone"
    r"|antihistamines?|beta.blockers?|ace inhibitors?|diuretics?|ozempic|semaglutide|wegovy)"
)

INTERACTION = r"(?:with|on|while|and|affect\w*|interact\w*|take|taking|before|after|mix\w*|combine\w*|skip\w*)"

# Nouns that make "weight"/"weigh" about food, not a person (EC SCOPE-15).
FOOD_NOUNS = (
    r"(?:portions?|servings?|patty|patties|burgers?|dough|loaf|loaves|cakes?|pasta|rice|grains?|meat|steak"
    r"|chicken|fish|eggs?|cups?|slices?|pieces?|batch|batches|beans|lentils|potato\w*|bread|flour|butter"
    r"|cheese|fruit|vegetables?|veg|nuts|oats|cereal|baby food|ingredients?|recipe|meal|bowl|scoop"
    r"|sandwich|pizza|turkey|ham|bacon|sausages?|tofu|quinoa|noodles)"
)

# Standard pregnancy food-safety questions stay in scope (EC SCOPE-B1 decision: allow).
PREGNANCY_FOOD_SAFETY = _p(
    r"pregnan\w*[^.?!]{0,80}?\b(?:raw|undercooked|runny|rare|sushi|sashimi|soft cheese|brie|camembert"
    r"|blue cheese|feta|deli|cold cuts|pate|pâté|unpasteuri[sz]ed|smoked salmon|shellfish|oysters|mercury"
    r"|tuna|swordfish|caffeine|coffee|tea|alcohol|wine|listeria|liver)\b"
    r"|\b(?:raw|undercooked|runny|rare|sushi|sashimi|soft cheese|brie|camembert|blue cheese|feta|deli"
    r"|cold cuts|pate|pâté|unpasteuri[sz]ed|smoked salmon|shellfish|oysters|mercury|tuna|swordfish|caffeine"
    r"|coffee|tea|alcohol|wine|listeria|liver)\b[^.?!]{0,80}?pregnan\w*"
)

CAL_COMPOSITION_EXCEPTIONS = [
    _p(r"\bcalories (?:are )?(?:there )?in\b"),
    _p(r"\bcalories (?:does|do|is|are) (?:there )?(?:in )?.{1,40}?\b(?:have|contain|has)\b"),
    _p(r"\bcalories per (?:\d+|serving|portion|cup|slice|gram|g|ounce|oz|piece|tablespoon|tbsp|teaspoon|tsp|litre|liter|ml)\b"),
    _p(r"\bcalories (?:does|do) .{1,40}?\bburn\b|\bburns?\b.{0,20}?\bcalories\b"),  # EC SCOPE-18: allow
]

FOOD_WEIGHT_EXCEPTIONS = [
    _p(rf"\b(?:weight|weigh|weighs)\b (?:of|for) (?:a |an |the |one |each |my |our )?(?:[\w-]+ ){{0,2}}{FOOD_NOUNS}\b"),
    _p(rf"\b{FOOD_NOUNS}\b[^.?!]{{0,40}}?\b(?:weigh|weighs|weight|gain|lose)\b"),
]


# --- input rules ----------------------------------------------------------------------------

INPUT_RULES: list[Rule] = [
    # Calorie targets
    Rule("IN-CAL-01", "calorie_target", "input",
         _p(r"\b(?:how many|how much|what|which)\b.{0,30}?\bcalories\b.{0,40}?\b(?:should|need|needs|require"
            r"|required|to (?:lose|gain|maintain|cut|bulk|drop)|per day|a day|daily|each day|every day|a week)\b"),
         CAL_COMPOSITION_EXCEPTIONS),
    # "How many should I eat a day to lose weight?" with no "calories" word (EC SCOPE-05 second clause)
    Rule("IN-CAL-02", "calorie_target", "input",
         _p(rf"\bhow (?:many|much)\b.{{0,40}}?\b(?:should|do|must|can) {SUBJECT} (?:eat|have|consume|take in)\b"
            r".{0,40}?\b(?:lose|gain|cut|drop|shed|maintain|slim|bulk)\b")),
    Rule("IN-CAL-03", "calorie_target", "input",
         _p(r"\b(?:daily|recommended|my|maintenance|a|personal|ideal|target|right|his|her) calorie"
            r" (?:intake|target|needs?|goal|budget|limit|requirements?|allowance)\b|\bcalorie intake\b")),
    # EC SCOPE-B3 decision: population targets ("an average adult") are declined in M1.
    Rule("IN-CAL-04", "calorie_target", "input",
         _p(r"\b(?:how (?:big|much|large)|what|which)\b.{0,20}?\bcalorie (?:deficit|surplus)\b"
            r"|\bcalorie (?:deficit|surplus)\b.{0,30}?\b(?:for me|should i|do i need|i need|to lose|to gain)\b"),
         # Definitions stay in scope: "What is a calorie deficit?"
         [_p(r"^what(?: is|'s| does) (?:a |an |the )?calorie (?:deficit|surplus)$")]),
    # EC SCOPE-10: "Is 2000 enough for me?"
    Rule("IN-CAL-05", "calorie_target", "input",
         _p(r"\b\d{3,4}(?: calories)?\b(?! ?(?:g|mg|ml|grams|ounces|oz)\b).{0,25}?\b(?:enough|too much|too little|too few|right|ok|okay|good)\b"
            r".{0,15}?\bfor (?:me|him|her|them|my [\w-]+)\b")),

    # Weight targets
    Rule("IN-WT-01", "weight_target", "input",
         _p(r"\b(?:ideal|healthy|target|goal|right|normal|good|perfect) (?:body )?(?:weight|bmi)\b"),
         [*FOOD_WEIGHT_EXCEPTIONS,
          # EC SCOPE-B2 decision: a general BMI range is allowed; "my BMI" is not.
          _p(r"\b(?:healthy|normal|ideal) bmi range\b(?![^.?!]{0,30}\b(?:for me|my|i)\b)")],
         exception_scope="sentence"),
    Rule("IN-WT-02", "weight_target", "input",
         _p(rf"\b(?:what|how much) (?:should|do|does|must|would|could) {SUBJECT}.{{0,20}}? weigh\b"),
         FOOD_WEIGHT_EXCEPTIONS, exception_scope="sentence"),
    Rule("IN-WT-03", "weight_target", "input",
         _p(rf"\bhow (?:much|many)\b.{{0,20}}?\b(?:should|do|must|can|could) {SUBJECT}"
            r" (?:lose|gain|drop|shed|put on)\b"
            r"|\bhow much\b.{0,20}?\b(?:lose|gain)\b.{0,20}?\b(?:weight|kg|lbs|stone)\b"),
         FOOD_WEIGHT_EXCEPTIONS, exception_scope="sentence"),
    Rule("IN-WT-04", "weight_target", "input",
         _p(r"\bwhat(?:'s| is| should)? (?:my|his|her) (?:bmi|weight)(?: goal| target)? (?:be|to be)\b"
            r"|\bwhat (?:bmi|weight) should (?:i|he|she|we|they) (?:be|aim|target|have|get)\b"
            r"|\bwhat (?:number|figure|weight) should (?:i|he|she|we|they) (?:aim|target|be|see|hit|get)\b.{0,30}?\bscale\b"
            r"|\b(?:aim|target|goal) for on the scale\b"
            r"|\bmy (?:bmi|weight) (?:goal|target)\b")),
    # EC SCOPE-10: "Am I too heavy at 80 kg?"
    Rule("IN-WT-05", "weight_target", "input",
         _p(r"\b(?:am i|is (?:he|she|my [\w-]+)|are (?:they|we)) (?:too |a bit |slightly |very )?"
            r"(?:overweight|underweight|obese|heavy|thin|fat|skinny|big|light)\b"),
         [*FOOD_WEIGHT_EXCEPTIONS, _p(rf"\b{FOOD_NOUNS}\b")], exception_scope="sentence"),
    Rule("IN-WT-06", "weight_target", "input",
         _p(r"\b(?:safe|realistic|healthy|possible|ok|okay) (?:for (?:me|him|her) )?to (?:lose|gain) \d+"
            rf"|\bhow (?:fast|quickly) (?:should|can|could) {SUBJECT} (?:lose|gain)\b")),
    # EC SCOPE-08: body stats followed by a target question (checked across the last two user turns).
    Rule("IN-WT-07", "weight_target", "input",
         _p(r"\b\d+ (?:kg|lbs|ft|cm|stone|years? old|yo)\b.{0,80}?\b(?:what should (?:i|he|she) (?:aim|target|go|weigh|eat)"
            r"|what(?:'s| is) (?:my|a good|the right) (?:target|goal)|how much should (?:i|he|she) (?:eat|weigh|lose|gain))")),

    # Medical advice
    Rule("IN-MED-01", "medical_advice", "input",
         _p(rf"\b{CONDITIONS}\b.{{0,60}}?\b{ADVICE}\b|\b{ADVICE}\b.{{0,60}}?\b{CONDITIONS}\b"),
         [PREGNANCY_FOOD_SAFETY], exception_scope="sentence"),
    # Drug-food interactions, with or without a named condition (EC SCOPE-11).
    Rule("IN-MED-02", "medical_advice", "input",
         _p(rf"\b{MEDICATIONS}\b.{{0,40}}?\b{INTERACTION}\b|\b{INTERACTION}\b.{{0,40}}?\b{MEDICATIONS}\b")),
    Rule("IN-MED-03", "medical_advice", "input",
         _p(r"\b(?:stop|start|skip|reduce|increase|lower|raise|change|adjust|come off|quit|double|halve)"
            r" (?:taking )?(?:my |his |her |their )?(?:medication|meds|medicine|pills|insulin|dose|dosage|prescription)\b"
            r"|\binsulin (?:dose|doses|dosage|injection|injections|shots?|units)\b")),
    # Personal condition disclosure makes a food question personal (EC SCOPE-B5, B7 decisions: decline).
    Rule("IN-MED-04", "medical_advice", "input",
         _p(rf"\b(?:i'?m|i am|i have|i've got|i've been diagnosed with|diagnosed with|i suffer from|i was told i have"
            rf"|he has|she has|he is|she is|they have|my (?:son|daughter|child|kid|husband|wife|partner|mom|mum|dad"
            rf"|mother|father|baby) (?:has|is))\b (?:[\w'-]+ ){{0,2}}{CONDITIONS}\b"),
         [PREGNANCY_FOOD_SAFETY], exception_scope="sentence"),
    # Supplement or medication dosing.
    Rule("IN-MED-05", "medical_advice", "input",
         _p(rf"\bhow (?:much|many)\b(?: [\w-]+){{0,4}}? (?:should|can|do|must) {SUBJECT} take\b"
            r"|\bhow many (?:mg|mcg|milligrams|micrograms|iu|units)\b")),
    # "What diet cures IBS?" / "foods that treat diabetes" / "diet for my gout"
    Rule("IN-MED-06", "medical_advice", "input",
         _p(rf"\b(?:diet|foods?|eat\w*|meal plan)\b.{{0,20}}?\b(?:for|to (?:treat|cure|manage|reverse|help|beat|fight))"
            rf" (?:my |his |her |their )?{CONDITIONS}\b|\b{CONDITIONS} diet\b"),
         [PREGNANCY_FOOD_SAFETY], exception_scope="sentence"),
]

# A short follow-up right after a decline stays declined, with the previous decline's
# category (EC SCOPE-09). "Inherit" rules only run when the previous assistant turn was a decline.
FOLLOW_UP_RULES: list[Rule] = [
    Rule("IN-FUP-01", "calorie_target", "input",  # category is replaced by the previous decline's
         _p(r"\b(?:rough|roughly|ballpark|approximate|approximately|estimate|guess|range|any number|a number"
            r"|a figure|just (?:a|give me|tell me|say)|come on|hypothetically|pretend|for a friend|for a story"
            r"|what about (?:me|for me|him|her)|so how (?:many|much)|then what|ignore)\b")),
]


# --- output rules ---------------------------------------------------------------------------

_NUM = r"\d{2,5}(?:\.\d+)?(?: ?(?:-|–|to) ?\d{2,5})?"

OUTPUT_RULES: list[Rule] = [
    Rule("OUT-CAL-01", "calorie_target", "output",
         _p(rf"\byou (?:should|could|need to|must|can|might|may want to) (?:eat|consume|aim for|target|stick to|have"
            rf"|get|take in|limit yourself to|stay under|stay around|keep to)\b.{{0,30}}?\b{_NUM} calories\b")),
    # Any daily calorie figure, personal or population (EC SCOPE-22 follows SCOPE-B3: out of scope).
    Rule("OUT-CAL-02", "calorie_target", "output",
         _p(rf"\b{_NUM} calories (?:a|per|each|every) day\b|\b{_NUM} calories daily\b|\bdaily (?:intake|target|goal) of"
            rf" (?:about |around |roughly )?{_NUM} calories\b")),
    Rule("OUT-CAL-03", "calorie_target", "output",
         _p(rf"\b(?:deficit|surplus) of (?:about |around |roughly )?{_NUM}(?: calories)?\b")),
    Rule("OUT-WT-01", "weight_target", "output",
         _p(r"\byour (?:ideal|target|healthy|goal) (?:body )?(?:weight|bmi)(?: range)? (?:is|would be|should be|of|is about"
            r"|is around|is roughly)\b")),
    Rule("OUT-WT-02", "weight_target", "output",
         _p(r"\byou (?:should|could|need to|must|can safely|may want to) (?:lose|gain|drop|shed|weigh|aim to weigh)\b"
            r".{0,20}?\d+|\baim to weigh\b")),
    Rule("OUT-WT-03", "weight_target", "output",
         _p(r"\ba healthy weight for you\b|\bhealthy weight range for you\b|\byour bmi (?:should|would) be\b")),
    Rule("OUT-WT-04", "weight_target", "output",
         _p(r"\b(?:ideal|healthy|target) (?:body )?weight\b[^.]{0,60}?\b(?:is|would be|of|around|about) (?:about |around"
            r" |roughly )?\d{2,3}(?: ?(?:-|–|to) ?\d{2,3})? (?:kg|lbs|stone)\b")),
    Rule("OUT-MED-01", "medical_advice", "output",
         _p(r"\b(?:stop|start|increase|reduce|lower|raise|skip|double|halve|adjust|change) (?:taking |your )(?:your )?"
            rf"(?:medication|medicine|meds|insulin|dose|dosage|pills|{MEDICATIONS})\b")),
    Rule("OUT-MED-02", "medical_advice", "output",
         _p(r"\b(?:this|it|these|that|the|this diet|that diet|these foods) (?:will|can|should|may) (?:cure|treat|reverse"
            r"|heal)\b"),
         # "cure" as food preservation ("salt can cure meat") is not a medical claim.
         [_p(r"\bcur(?:e|es|ed|ing)\b[^.?!]{0,20}?\b(?:meat|bacon|ham|fish|salmon|pork|sausages?|olives|egg yolks?"
             r"|beef)\b")],
         exception_scope="sentence"),
    Rule("OUT-MED-03", "medical_advice", "output",
         _p(r"\byou (?:can|should|could|need to) take (?:about |around |up to )?\d+ ?(?:mg|mcg|µg|iu|g|units)\b")),
]

ALL_RULES: list[Rule] = [*INPUT_RULES, *FOLLOW_UP_RULES, *OUTPUT_RULES]
