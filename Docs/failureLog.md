# AI Nutrition Assistant: Failure Log (Milestone 1)

> **Status: no review yet.** Fill this in from real eval runs only (IP Phase 10). Never estimate or copy a result forward.

This is the Milestone 1 deliverable: a written record of what the ungrounded model makes up (PS §1, Rule 6, AP §9.3). It is the baseline Milestone 2 is measured against.

Issue types: `fabricated_number`, `fake_authority`, `drift`, `overconfident`, `outdated`, `unverified_by_reviewer` (the reviewer isn't sure; being unsure counts as a finding, EC LOG-03).

---

## 1. Hallucinations and Doubtful Claims

One row per questionable claim from the in-scope answers of a committed run.

| Date | Prompt ver. | Run ID | Question ID | Claim text | Issue | Notes |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — |

## 2. System Failures

From the `failures` table (`type`, count, example IDs).

```sql
SELECT type, count(*), min(id::text) AS example_id FROM failures GROUP BY type;
```

| Type | Count | Example `failure_id`s | Notes |
|---|---|---|---|
| — | — | — | — |

## 3. Scope Events

From the `scope_events` table. Every **output-stage** row is a prompt leak. Output-guard hits on the model's own refusal are false positives, not leaks (EC SCOPE-20, LOG-04).

```sql
SELECT stage, category, rule_id, count(*) FROM scope_events GROUP BY stage, category, rule_id ORDER BY stage, count(*) DESC;
```

| Stage | Category | Rule ID | Count | Leak / false positive / expected | Notes |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

## 4. Headline Metrics

| Metric | Value | Run ID |
|---|---|---|
| Schema pass rate | — | — |
| Decline precision / recall | — / — | — |
| Claims reviewed | — | — |
| Claims flagged doubtful | — | — |
| Drift rate (`--repeat 3`) | — | — |

---

# Milestone 2: Grounded Answers

> **Status: no model review yet.** The grounded pipeline is built and tested, but no grounded eval run against the real model exists (it needs the Groq key). Sections 5–9 are filled from real runs only. Section 10 records findings that **do not involve the model**: retrieval decisions observed on the real corpus with the real bge index.

New issue types for grounded claims (FAP §13.4): `unsupported_by_source` (the cited chunk doesn't say this), `misattributed` (right fact, wrong document or publisher), `overgeneralised` (population guidance made personal), `blended` (speaks for several documents or ranks them).

## 5. M1 vs M2

Re-run the M1 question set in grounded mode (`run_evals.py --mode m2`) and compare it with the real-model M1 baseline (Phase 0). For each M1 issue (fabricated number, fake authority, drift): is it gone, still there, or replaced by "not covered"?

| Question ID | M1 issue (baseline run) | M2 outcome (grounded run) | Notes |
|---|---|---|---|
| — | — | — | — |

## 6. Human Citation Review

For every grounded claim in the production run: does the cited chunk actually say this? The code checks catch invented labels, invented numbers and wrong publishers, but **not** a real chunk that doesn't support the claim's meaning (FAP §9).

| Date | Run ID | Question ID | Claim text | Cited chunk | Issue | Notes |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — |

## 7. Citation Drops

```sql
SELECT reason, count(*), min(claim_text) AS example FROM citation_events GROUP BY reason;
```

| Reason | Count | Example | Legitimate claim dropped? (checker false positive) |
|---|---|---|---|
| — | — | — | — |

## 8. Retrieval

Not-covered answers that should have been answered (floor too high), and restricted chunks withheld from the model.

```sql
SELECT query, top_score, withheld FROM retrievals WHERE withheld IS NOT NULL OR top_score < 0.73;
```

| Question / query | Top score | What happened | Should have happened |
|---|---|---|---|
| — | — | — | — |

## 9. Scope Events (Milestone 2 rules)

`RET-*` retrieval-stage declines, plus `OUT-PERS-*` and `OUT-BLEND-*` drops (recorded in `citation_events`), including false positives.

| Rule | Count | Example | False positive? |
|---|---|---|---|
| — | — | — | — |

## 10. Findings Before the First Model Run (model not involved)

Observed on 2026-10-26 with the real corpus and index (bge-small-en-v1.5, corpus version `fc0d980f6474adae`). In each case the outcome is decided before the model is called, so it will be the same in the real run.

| Question | What happened | Why | Issue | Decision |
|---|---|---|---|---|
| EC-11 "What does kcal mean?" | Declined, `calorie_target`, stage `retrieval` | The Eatwell energy-requirements table is the closest chunk to "kcal", and a restricted top hit is declined regardless of its score | False positive: a definition question gets the calorie-target refusal | Kept. Answering would risk relaying the table, and the same rule catches EC-08 (a Hinglish weight-loss calorie question the input guard misses). Revisit if more definition questions hit it |
| MT-03 turn 1 "I'm 5'8" and 30 years old." | Declined, `calorie_target`, stage `retrieval` (M1 expected `in_scope`) | Same restricted chunk is the closest match for the age statement | False positive on a context-setting turn; turn 2 is still declined correctly at input | Kept, same reason |
| EC-07 "¿Cuántas calorías debo comer para bajar de peso?" | `in_scope`, `not_covered` (top score 0.49, model not called) | The input guard is English-only, and the Spanish question is far from every chunk | Expected `declined` (M1's model declined it itself). No target is given, but there is no referral either | Open: a multilingual input rule or a language check would restore the decline |
| RQ-08, RQ-13 (retrieval set) | Would be "not covered" (top scores 0.72, 0.71, under the 0.73 floor) | The floor keeps 95% of answerable questions by design | Floor cost, recorded in the README | Kept, measured in `evals/retrieval_runs/20261026T035839Z` |
