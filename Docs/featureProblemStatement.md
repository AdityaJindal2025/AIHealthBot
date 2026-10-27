# AI Nutrition Assistant: Problem Statement (Milestone 2: Grounded Answers)

## 1. Brief

Add a **retrieval layer** under the existing chatbot so that it answers **only from official public dietary guidance documents**.

- **Every claim carries a citation.**
- When the guidance **doesn't cover** a question, the assistant **says so**.

In Milestone 1 the model answered from its own memory and every `source` was `null`. Milestone 2 replaces model memory with retrieved text and fills in `source` with a real citation.

---

## 2. Why This Milestone

- Milestone 1 measured how an ungrounded model behaves: specific-sounding answers that **come from nobody**.
- In this milestone every answer has to be **traceable to a named document, publisher and year** that a reader can open and check.
- **Model knowledge is no longer a source.** If the retrieved text doesn't say it, the assistant doesn't say it.

---

## 3. Corpus

**Source file:** [`backend/corpus/blocks.jsonl`](../backend/corpus/blocks.jsonl) (moved from `Docs/blocks.json` so it is inside the backend build context; there is only one copy). Use it as the corpus. No separate PDF parsing is needed for these documents.

**Format:** JSON Lines (one JSON object per line), **1,001 blocks** across **7 documents**. That falls within the 5 to 7 document limit.

### 3.1 Block fields

| Field | Present on | Notes |
|---|---|---|
| `document_id` | all | Slug identifying the source document |
| `ordinal` | all | Order of the block within its document |
| `type` | all | `heading` (176), `paragraph` (383), `list_item` (430), `table` (12) |
| `text` | all | Block text |
| `heading_path` | all | Breadcrumb of section headings, e.g. `["Cold Food Storage Chart"]` |
| `level` | headings | Heading depth (1 to 6) |
| `page` | 953 of 1,001 | Page number in the original document |
| `header`, `rows` | tables | Table column headers and row cells |
| `caption` | some tables | e.g. "Turkey Thawing Chart: Approximate Timelines" |

### 3.2 Documents in the corpus

| `document_id` | Blocks | Topic area |
|---|---|---|
| `kitchen-companion` | 469 | Food safety (handling, cooking temperatures, storage, turkey charts) |
| `who-five-keys` | 174 | Food safety (Five Keys to Safer Food) |
| `eatwell-guide` | 120 | Healthy eating (food groups, sugar, salt) |
| `fao-who-healthy-diets` | 98 | Healthy / sustainable diets |
| `who-healthy-diet` | 92 | Healthy diet fact sheet (sugar, salt, fats) |
| `fsa-chill` | 45 | Chilling, freezing and defrosting |
| `cold-food-storage` | 3 | Fridge and freezer storage chart (one large table) |

### 3.3 Gap: citation metadata is not in the corpus

Each citation must show **document name, publisher, year and a link**. `blocks.json` holds **none of these**; it only has a `document_id` slug.

**Required:** add a **document registry** (for example `documents.json` or a DB table) keyed by `document_id`, with:

| Field | Example |
|---|---|
| `document_id` | `who-healthy-diet` |
| `title` | Healthy diet (Fact sheet N°394) |
| `publisher` | World Health Organization |
| `year` | *(confirm from the source)* |
| `url` | *(official public URL)* |

Check each value against the original published document. **Don't fill this in from model memory**, which is exactly the failure Milestone 1 recorded.

---

## 4. What to Build

### 4.1 Chunking

- **Every chunk carries metadata:** document name, publisher, year and section heading (from `heading_path`), plus `document_id`, `page` and block ordinals for traceability.
- These documents are **full of tables and numbered recommendations**. Fixed-size chunking will cut them in half.
  - A table (`type: table`) must stay **whole**, or be split by row with the header repeated on every piece.
  - A run of `list_item` blocks under one heading (for example a numbered recommendation list) should stay **together**.
  - The structure in `heading_path` and `type` is already there; use it instead of splitting on character counts.
- **README:** say which strategy you chose and **what it cost you** (for example uneven chunk sizes, very large table chunks, or worse recall on tiny sections).

### 4.2 Retrieval

- A **vector index** over the chunks.
- It supports two modes:
  1. **Retrieval across all documents.**
  2. **Retrieval filtered to one named document** (a metadata filter on `document_id`).

### 4.3 Answer Layer

- The assistant answers **only from retrieved chunks**.
- **Every claim carries a citation** with document name, publisher, year and link.
- **A claim with no citation does not ship.** Enforce this in code: reject or strip uncited claims, and record the failure instead of hiding it.
- **Population-level guidance stays population-level.** "WHO recommends adults limit free sugars to less than 10% of total energy intake" is fine. "You should eat X grams of sugar" is not.

### 4.4 Cross-Document Questions

Some questions have **two documents** with something to say. The brief's example is cooking oil, where a nutrition institute and a food safety regulator both weigh in.

- **Answer per document, with separate citations.**
- **Never blend two sources** into one claim about what "the guidelines say".
- **When two documents disagree, show both** with their publishers and years. **Don't pick a winner.**

Topics in this corpus where several documents overlap:

| Topic | Documents |
|---|---|
| Cooking oil / fats | `eatwell-guide`, `who-healthy-diet`, `kitchen-companion`, `who-five-keys` |
| Fridge temperature and storage times | `fsa-chill`, `kitchen-companion`, `cold-food-storage`, `who-five-keys` |
| Sugar | `who-healthy-diet`, `eatwell-guide`, `fao-who-healthy-diets` |
| Salt | `who-healthy-diet`, `eatwell-guide`, `fao-who-healthy-diets` |

These are good candidates for the regression question set.

### 4.5 Two Kinds of Refusal (Both Required)

| Refusal | When | What the assistant does |
|---|---|---|
| **Not in the corpus** | The retrieved chunks don't hold the answer | Says the guidance **doesn't cover it** and **names what it searched** (which documents, or the one filtered document) |
| **Out of scope by design** | Medical advice, calorie or weight targets, what anyone should weigh | **Declines** and points the person to a **qualified professional**. **Enforce this in code**, the same as Milestone 1 (`backend/app/guards/`). |

The two refusals must look different to the user. "We don't have guidance on that" and "We won't answer that" are not the same message.

**Watch out:** the corpus itself contains material that is out of scope if presented as a personal target. For example, `eatwell-guide` has a table of **daily energy requirements in kcal by age**, and several documents talk about weight. Retrieving that text does **not** permit the assistant to give a calorie or weight target. The scope guard runs **regardless of what retrieval returns**.

### 4.6 Filling in the Shell

**Don't rebuild the frontend or the backend.** Extend what Milestone 1 built.

- **Sources panel:** the panel left empty in Milestone 1 now shows the **retrieved chunks behind each answer**.
- **`claims[].source`:** carries a **real citation** instead of `null`.
- **Schema change:** if the Milestone 1 schema doesn't fit real citations, change it and **document what changed**. `backend/app/schemas/model_output.py` currently types `source` as `None` and expects only this milestone to change it. A likely shape:

```json
{
  "answer": "...",
  "claims": [
    {
      "text": "WHO recommends limiting free sugars to less than 10% of total energy intake.",
      "source": {
        "document_id": "who-healthy-diet",
        "document_name": "Healthy diet (Fact sheet N°394)",
        "publisher": "World Health Organization",
        "year": 0,
        "url": "https://...",
        "section": "...",
        "chunk_id": "..."
      }
    }
  ]
}
```

Validate the model's `chunk_id` / `document_id` against the chunks **actually retrieved** for that request. A citation pointing to something that wasn't retrieved counts as a failure.

---

## 5. Allowed Tools

| Area | Options |
|---|---|
| PDF parsing | PyMuPDF, Unstructured, Docling or LlamaParse *(not needed for this corpus, which is already parsed into `blocks.json`)* |
| Chunking | LangChain text splitters, or your own splitter that breaks on section headings |
| Embeddings | OpenAI `text-embedding-3-small`, Cohere embed, or sentence-transformers (local and free) |
| Vector store | Supabase pgvector, Pinecone, or Qdrant (if hosted) |
| Orchestration | LangChain, or plain Python to see every step |
| Everything else | Same stack as Milestone 1 |

---

## 6. Rules (Non-Negotiable)

1. **Answers come from retrieved text only.** Model knowledge is not a source.
2. **Every claim carries a citation.** No citation means the claim doesn't ship.
3. **Population-level guidance stays population-level.** No turning it into a personal recommendation.
4. **No calorie targets, no weight targets, no medical advice** anywhere in the conversation.
5. **When two documents disagree, show both** with their publishers and years. Don't pick a winner.
6. **5 to 7 documents** in the corpus (this corpus has 7).
7. **The README states** chunk size, overlap, embedding model, index type and k value.

---

## 7. Acceptance Checklist

- [x] Corpus loaded from `backend/corpus/blocks.jsonl`, formerly `Docs/blocks.json` (7 documents) *(evidence: `backend/app/rag/corpus.py`, `tests/test_corpus.py`)*
- [x] Document registry with verified title, publisher, year and URL for each `document_id` *(evidence: `backend/corpus/documents.json` + verification record in `backend/corpus/README.md`, 2026-10-27)*
- [x] Structure-aware chunking: tables and numbered/list recommendations are not split mid-item *(evidence: `backend/app/rag/chunker.py`, `tests/test_chunker.py`, `backend/corpus/build_report.md`)*
- [x] Every chunk carries document name, publisher, year and section heading *(evidence: `Chunk` record in `app/rag/chunker.py`, verified registry, `build_report.md`)*
- [x] Vector index built; retrieval works across all documents and filtered to one document *(evidence: `app/rag/build_index.py`, `app/rag/retriever.py`, `tests/test_retriever.py`, `evals/retrieval_runs/20261026T035839Z`)*
- [ ] Answers use retrieved chunks only *(built: system_v2 prompt + citation checks; open: needs a real-model grounded run and the citation review)*
- [ ] Every claim has a citation (name, publisher, year, link); uncited claims are blocked in code *(built: uncited claims are blocked in code, and sources carry the verified year and link; open: confirm T8 = 100% in a real grounded run)*
- [x] Citations are checked against the chunks retrieved for that request *(evidence: `app/rag/citations.py`, `tests/test_citations.py`, `tests/test_rag_api.py`)*
- [x] Cross-document questions are answered per document with separate citations, never blended *(evidence: `app/rag/composer.py` builds one block per document; blend phrases dropped by `OUT-BLEND-01`; `tests/test_composer.py`)*
- [x] Disagreements show both sources with publisher and year, with no winner picked *(evidence: the composer never merges or ranks blocks; ranking phrases are dropped by `OUT-BLEND-01`)*
- [x] "Not in corpus" refusal names what was searched *(evidence: `compose_not_covered`, `grounding.searched`; `tests/test_rag_api.py`)*
- [x] "Out of scope" refusal is enforced in code and refers the person to a professional, even when retrieved text contains kcal or weight figures *(evidence: `app/rag/tagger.py` + retrieval-stage decline; restricted chunks are never sent to the model; `tests/test_tagger.py`, `tests/test_rag_api.py`)*
- [x] Sources panel shows the chunks behind each answer *(evidence: `frontend/components/SourcesPanel.tsx`, `frontend/__tests__/components.test.tsx`)*
- [ ] `claims[].source` holds a real citation; any schema change is documented *(schema change documented in README; open: confirm with a real grounded run)*
- [x] README states the chunking strategy and its cost, chunk size, overlap, embedding model, index type and k *(evidence: README "Retrieval parameters")*
- [ ] Regression question set extended with grounded, cross-document, not-in-corpus and out-of-scope cases, and re-run after every change *(extended: 28 questions in 6 new groups; open: no grounded real-model run yet)*
- [ ] Still deployed at the public URL *(open: Phase 10 deploy)*

---

## 8. Roadmap

| Milestone | Focus |
|---|---|
| **1 (done)** | Ungrounded chatbot. Fixed schema, `source: null`, scope guardrails, deployed. Record what the model makes up. |
| **2 (this brief)** | Retrieval over 7 official guidance documents. Real citations on every claim, populated sources panel, per-document answers, two kinds of refusal. |
