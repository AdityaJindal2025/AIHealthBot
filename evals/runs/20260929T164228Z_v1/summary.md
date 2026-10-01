# Eval run 20260929T164228Z_v1

- Target: `http://127.0.0.1:8765`
- Prompt version: `v1` · Model: `stub-model`
- Started: 2026-09-29T16:42:28.825503+00:00 · Repeat: 2
- Complete: **yes**

## Totals

- Scored questions: 2 · passed **2** · failed **0**
- Schema pass rate: 6/6 responses (200 + 502)
- Model failures (502) by type: none
- Declines by stage: {'input': 2} (`model` = the model declined by itself, EC SCOPE-12)
- Excluded requests (429 / network): 0
- Latency p50/p95: 5 / 5 ms (includes the first, possibly cold, request)

## Per question

| ID | Group | Result | Status | Words | Claims | Failed checks |
|---|---|---|---|---|---|---|
| NUT-01 | nutrition | ✅ | in_scope | 18 | 1 | — |
| MT-03 | multi_turn | ✅ | declined:weight_target@input | 38 | 0 | — |

## Diff against the previous run

Compared with `20260929T164216Z_v1`.

- ❌ Newly failing (regressions): none
- ✅ Newly passing: MT-03
- Scope status or category changed: MT-03 (in_scope → declined:weight_target@input)
- Claim count changed by more than 2: none

Answer text changed (expected on every run, EC EVAL-03): MT-03

## Drift across repeats

No numeric drift detected.

Drift rate: 0/2 questions.
