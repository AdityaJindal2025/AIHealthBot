# Eval run 20261027T164703Z_v2

- Target: `http://127.0.0.1:8020`
- Prompt version: `v2` · Model: `openai/gpt-oss-120b` · Mode: `m2`
- Started: 2026-10-27T16:47:03.786491+00:00 · Repeat: 3
- Complete: **yes**

## Totals

- Scored questions: 2 · passed **2** · failed **0**
- Schema pass rate: 5/5 responses (200 + 502)
- Model failures (502) by type: none
- Declines by stage: none (`model` = the model declined by itself, EC SCOPE-12)
- Excluded requests (429 / network): 1
- Latency p50/p95: 1355 / 1634 ms (includes the first, possibly cold, request)

## Milestone 2 thresholds (FAP §13.3)

| # | Check | Threshold | Result |
|---|---|---|---|
| T8 | Claims with a complete `source` | 100% | 27/27 (100%) of 27 claims |
| T9 | XDOC questions citing ≥ 2 documents | 100% | 1/1 (100%) |
| T10 | NIC questions `not_covered` with `searched` | 100% | — |
| T11 | Citations outside the filter document | 0 | 0 |
| T12 | RESTR questions declined | 100% | — |
| T13 | Retrieval document recall@k | ≥ baseline | see `evals/retrieval_runs/` (`run_retrieval_eval.py`) |
| T14 | `claims_dropped` | reported; a rise is a regression | 0 (previous 0) |

## Per question

| ID | Group | Result | Status | Words | Claims | Failed checks |
|---|---|---|---|---|---|---|
| XDOC-02 | cross_document | ✅ | in_scope | 167 | 8 | — |
| FILT-01 | filtered | ✅ (2/3 repeats) | in_scope | 58 | 2 | — |

| ID | Grounding | Cited documents | Claims dropped |
|---|---|---|---|
| XDOC-02 | grounded | cold-food-storage, fsa-chill, kitchen-companion | 0 |
| FILT-01 | grounded | fsa-chill | 0 |

## Diff against the previous run

Compared with `20261027T111911Z_v2`.

- ❌ Newly failing (regressions): none
- ✅ Newly passing: none
- Scope status or category changed: none
- Claim count changed by more than 2: none

Answer text changed (expected on every run, EC EVAL-03): none

## Drift across repeats

| Question | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| XDOC-02 | 3to4 days, 4.44 °c, 40 °f, 48 hours, 5 °c | 3to4 days, 4.44 °c, 40 °f, 48 hours, 5 °c | 3to4 days, 3to5 days, 4.44 °c, 40 °f, 48 hours, 5 °c |
| FILT-01 | 63 °c | 63 °c, 8 °c |

Drift rate: 2/2 questions.

## Excluded requests

| Question | Reason | 429 retries |
|---|---|---|
| FILT-01 | rate_limited | 5 |
