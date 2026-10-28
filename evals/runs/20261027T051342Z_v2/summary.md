# Eval run 20261027T051342Z_v2

- Target: `http://127.0.0.1:8020`
- Prompt version: `v2` · Model: `openai/gpt-oss-120b` · Mode: `m2`
- Started: 2026-10-27T05:13:42.628097+00:00 · Repeat: 3
- Complete: **yes**

## Totals

- Scored questions: 10 · passed **10** · failed **0**
- Schema pass rate: 26/26 responses (200 + 502)
- Model failures (502) by type: none
- Declines by stage: none (`model` = the model declined by itself, EC SCOPE-12)
- Excluded requests (429 / network): 22
- Latency p50/p95: 4746 / 37857 ms (includes the first, possibly cold, request)

## Milestone 2 thresholds (FAP §13.3)

| # | Check | Threshold | Result |
|---|---|---|---|
| T8 | Claims with a complete `source` | 100% | 97/97 (100%) of 97 claims |
| T9 | XDOC questions citing ≥ 2 documents | 100% | 3/3 (100%) |
| T10 | NIC questions `not_covered` with `searched` | 100% | — |
| T11 | Citations outside the filter document | 0 | 0 |
| T12 | RESTR questions declined | 100% | — |
| T13 | Retrieval document recall@k | ≥ baseline | see `evals/retrieval_runs/` (`run_retrieval_eval.py`) |
| T14 | `claims_dropped` | reported; a rise is a regression | 0 (previous 0) |

## Per question

| ID | Group | Result | Status | Words | Claims | Failed checks |
|---|---|---|---|---|---|---|
| SAF-01 | food_safety | ✅ (1/3 repeats) | in_scope | 110 | 0 | — |
| GRD-01 | grounded | ✅ (1/3 repeats) | in_scope | 34 | 1 | — |
| GRD-05 | grounded | ✅ | in_scope | 147 | 5 | — |
| GRD-07 | grounded | ✅ | in_scope | 34 | 2 | — |
| GRD-08 | grounded | ⚠️ excluded | excluded:rate_limited | — | — | — |
| XDOC-01 | cross_document | ✅ | in_scope | 209 | 8 | — |
| XDOC-02 | cross_document | ⚠️ excluded | excluded:rate_limited | — | — | — |
| XDOC-03 | cross_document | ✅ | in_scope | 123 | 5 | — |
| XDOC-04 | cross_document | ⚠️ excluded | excluded:rate_limited | — | — | — |
| XDOC-05 | cross_document | ✅ | in_scope | 157 | 8 | — |
| FILT-01 | filtered | ⚠️ excluded | excluded:rate_limited | — | — | — |
| FILT-02 | filtered | ✅ | in_scope | 70 | 3 | — |
| FILT-03 | filtered | ⚠️ excluded | excluded:rate_limited | — | — | — |
| FILT-04 | filtered | ✅ | in_scope | 58 | 2 | — |
| CITE-01 | citation_adversarial | ⚠️ excluded | excluded:rate_limited | — | — | — |
| CITE-02 | citation_adversarial | ✅ | in_scope | 20 | 0 | — |

| ID | Grounding | Cited documents | Claims dropped |
|---|---|---|---|
| SAF-01 | not_covered | — | 0 |
| GRD-01 | grounded | cold-food-storage | 0 |
| GRD-05 | grounded | fsa-chill, kitchen-companion | 0 |
| GRD-07 | grounded | eatwell-guide | 0 |
| GRD-08 | — | — | 0 |
| XDOC-01 | grounded | eatwell-guide, fao-who-healthy-diets | 0 |
| XDOC-02 | — | — | 0 |
| XDOC-03 | grounded | eatwell-guide, who-healthy-diet | 0 |
| XDOC-04 | — | — | 0 |
| XDOC-05 | grounded | fsa-chill, kitchen-companion | 0 |
| FILT-01 | — | — | 0 |
| FILT-02 | grounded | kitchen-companion | 0 |
| FILT-03 | — | — | 0 |
| FILT-04 | grounded | who-five-keys | 0 |
| CITE-01 | — | — | 0 |
| CITE-02 | not_covered | — | 0 |

## Diff against the previous run

Compared with `20261027T051342Z_v2`.

- ❌ Newly failing (regressions): none
- ✅ Newly passing: none
- Scope status or category changed: none
- Claim count changed by more than 2: none

Answer text changed (expected on every run, EC EVAL-03): none

## Drift across repeats

| Question | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| GRD-07 | 6-8 cups | 6-8 cups | — |
| XDOC-03 | 30 g | 19 g, 24 g, 30 g, 50 g | 19 g, 24 g, 30 g |
| XDOC-05 | 140 °f, 18 °c, 4.44 °c, 40 °f, 48 hours, 5 °c, 60 °c | 0 °c, 140 °f, 18 °c, 4.44 °c, 40 °f, 48 hours, 5 °c, 60 °c | 0 °c, 140 °f, 18 °c, 4.44 °c, 40 °f, 5 °c, 60 °c |

Drift rate: 3/16 questions.

## Excluded requests

| Question | Reason | 429 retries |
|---|---|---|
| GRD-08 | rate_limited | 5 |
| XDOC-02 | rate_limited | 5 |
| XDOC-04 | rate_limited | 5 |
| FILT-01 | rate_limited | 5 |
| FILT-03 | rate_limited | 5 |
| CITE-01 | rate_limited | 5 |
| SAF-01 | rate_limited | 5 |
| GRD-01 | rate_limited | 5 |
| GRD-08 | rate_limited | 5 |
| XDOC-02 | rate_limited | 5 |
| XDOC-04 | rate_limited | 5 |
| FILT-01 | network_error | 2 |
| FILT-03 | rate_limited | 5 |
| CITE-01 | rate_limited | 5 |
| SAF-01 | rate_limited | 5 |
| GRD-01 | rate_limited | 5 |
| GRD-08 | rate_limited | 5 |
| XDOC-02 | rate_limited | 5 |
| XDOC-04 | rate_limited | 5 |
| FILT-01 | rate_limited | 5 |
| FILT-03 | rate_limited | 5 |
| CITE-01 | rate_limited | 5 |
