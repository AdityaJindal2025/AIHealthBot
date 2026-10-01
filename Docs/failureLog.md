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
