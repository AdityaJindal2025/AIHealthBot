# Retrieval Eval Run 20261026T035839Z

- Embedding model: `BAAI/bge-small-en-v1.5`
- Corpus version: `066b9e19fa0e79ed` (209 chunks)
- Questions: 62 (answerable 40, filtered 4, not_in_corpus 11, restricted 2, xdoc 5)
- Reported configuration: k=6, max per document=2

## Metrics

| Metric | Value | Baseline |
|---|---|---|
| doc_hit_at_k | 1.0 | – |
| doc_recall_at_k | 0.9643 | – |
| xdoc_recall_at_k | 0.8667 | – |
| xdoc_all_found | 0.6 | – |
| chunk_recall_at_k | 1.0 | – |
| mrr | 0.9898 | – |
| filter_respected | 1.0 | – |
| restricted_ok | 1.0 | – |

## Sweep (k × per-document cap)

| k | cap | doc hit@k | doc recall@k | xdoc all found | chunk recall@k | MRR |
|---|---|---|---|---|---|---|
| 4 | 2 | 1.0 | 0.9388 | 0.6 | 1.0 | 0.9898 |
| 4 | 3 | 1.0 | 0.9388 | 0.6 | 1.0 | 0.9898 |
| 6 | 2 | 1.0 | 0.9643 | 0.6 | 1.0 | 0.9898 |
| 6 | 3 | 1.0 | 0.949 | 0.6 | 1.0 | 0.9898 |
| 8 | 2 | 1.0 | 0.9711 | 0.8 | 1.0 | 0.9898 |
| 8 | 3 | 1.0 | 0.9643 | 0.6 | 1.0 | 0.9898 |

## Top-1 Score Distributions

| Set | n | min | p05 | p25 | median | p75 | max |
|---|---|---|---|---|---|---|---|
| answerable (all documents) | 45 | 0.7105 | 0.7309 | 0.7741 | 0.8094 | 0.8494 | 0.8911 |
| filtered (not floored) | 4 | 0.6773 | 0.6773 | 0.6821 | 0.8265 | 0.898 | 0.898 |
| not in corpus | 11 | 0.6019 | 0.6019 | 0.6083 | 0.6247 | 0.6339 | 0.6759 |

## Score Floor

Suggested `RETRIEVAL_MIN_SCORE`: **0.7308** (keeps 96% of answerable all-documents questions; rejects 100% of not-in-corpus questions). The floor applies in all-documents mode only.

Not-in-corpus questions still above the floor (the model's `not_covered` is the second check): none

## Misses (reported configuration)

| ID | Group | Question | Top score | Retrieved documents |
|---|---|---|---|---|
| RX-01 | xdoc | What do the guidelines say about cooking oil and fats? | 0.7329 | eatwell-guide, fao-who-healthy-diets, kitchen-companion |
| RX-05 | xdoc | How should food be kept at safe temperatures? | 0.8553 | fsa-chill, kitchen-companion |
