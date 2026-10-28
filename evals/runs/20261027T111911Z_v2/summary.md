# Eval run 20261027T111911Z_v2

- Target: `http://127.0.0.1:8020`
- Prompt version: `v2` · Model: `openai/gpt-oss-120b` · Mode: `m2`
- Started: 2026-10-27T11:19:11.566501+00:00 · Repeat: 3
- Complete: **yes**

## Totals

- Scored questions: 4 · passed **4** · failed **0**
- Schema pass rate: 10/10 responses (200 + 502)
- Model failures (502) by type: none
- Declines by stage: none (`model` = the model declined by itself, EC SCOPE-12)
- Excluded requests (429 / network): 8
- Latency p50/p95: 1227 / 12674 ms (includes the first, possibly cold, request)

## Milestone 2 thresholds (FAP §13.3)

| # | Check | Threshold | Result |
|---|---|---|---|
| T8 | Claims with a complete `source` | 100% | 28/28 (100%) of 28 claims |
| T9 | XDOC questions citing ≥ 2 documents | 100% | 1/1 (100%) |
| T10 | NIC questions `not_covered` with `searched` | 100% | — |
| T11 | Citations outside the filter document | 0 | 0 |
| T12 | RESTR questions declined | 100% | — |
| T13 | Retrieval document recall@k | ≥ baseline | see `evals/retrieval_runs/` (`run_retrieval_eval.py`) |
| T14 | `claims_dropped` | reported; a rise is a regression | 0 (previous 0) |

## Per question

| ID | Group | Result | Status | Words | Claims | Failed checks |
|---|---|---|---|---|---|---|
| GRD-08 | grounded | ✅ | in_scope | 38 | 1 | — |
| XDOC-02 | cross_document | ⚠️ excluded | excluded:rate_limited | — | — | — |
| XDOC-04 | cross_document | ✅ | in_scope | 182 | 6 | — |
| FILT-01 | filtered | ⚠️ excluded | excluded:rate_limited | — | — | — |
| FILT-03 | filtered | ✅ | in_scope | 98 | 4 | — |
| CITE-01 | citation_adversarial | ✅ (1/3 repeats) | in_scope | 110 | 0 | — |

| ID | Grounding | Cited documents | Claims dropped |
|---|---|---|---|
| GRD-08 | grounded | kitchen-companion | 0 |
| XDOC-02 | — | — | 0 |
| XDOC-04 | grounded | eatwell-guide, fao-who-healthy-diets, who-healthy-diet | 0 |
| FILT-01 | — | — | 0 |
| FILT-03 | grounded | eatwell-guide | 0 |
| CITE-01 | not_covered | — | 0 |

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
| XDOC-04 | 2 g, 5 g, 6 g, 9–12 g | 2 g, 5 g, 6 g | 2 g, 5 g, 6 g |

Drift rate: 1/6 questions.

## Excluded requests

| Question | Reason | 429 retries |
|---|---|---|
| XDOC-02 | rate_limited | 5 |
| FILT-01 | rate_limited | 5 |
| CITE-01 | rate_limited | 5 |
| XDOC-02 | rate_limited | 5 |
| FILT-01 | rate_limited | 5 |
| CITE-01 | rate_limited | 5 |
| XDOC-02 | rate_limited | 5 |
| FILT-01 | rate_limited | 5 |
