# AI Nutrition Assistant (Milestone 2: grounded answers)

A chat assistant for general questions about food, nutrition and food safety.

- **Milestone 1** was deliberately **ungrounded**: answers came from the model's memory and every `source` was `null` ([Docs/problemStatement.md](Docs/problemStatement.md)).
- **Milestone 2** answers **only from 7 official public guidance documents**. Every claim carries a citation (document, publisher, year, link), cross-document answers stay separate per document, and when the guidance doesn't cover a question the assistant says so and names what it searched ([Docs/featureProblemStatement.md](Docs/featureProblemStatement.md), [plan](Docs/featureImplementationPlan.md)).

- **Frontend:** Next.js + Tailwind, deployed to Vercel ([frontend/](frontend/))
- **Backend:** FastAPI + SQLAlchemy, deployed to Railway with Postgres ([backend/](backend/))
- **Evals:** fixed regression question set and runner ([evals/](evals/))
- **Corpus:** 1,001 parsed blocks from 7 documents, plus a document registry ([backend/corpus/](backend/corpus/))
- **Plans:** M1 [architecturePlan.md](Docs/architecturePlan.md), [implementationPlan.md](Docs/implementationPlan.md), [edgeCases.md](Docs/edgeCases.md); M2 [featureArchitecturePlan.md](Docs/featureArchitecturePlan.md), [featureImplementationPlan.md](Docs/featureImplementationPlan.md)

Public URLs: _to be added after the Phase 9 deploy._

## How a request flows

**Grounded (M2, `RAG_ENABLED=true`, the default):** `POST /api/chat` → input scope guard → retrieve (embed query → exact cosine search, k=6, at most 2 per document) → restricted top hit? decline → top score under the floor? "not covered" → Groq with strict structured output over labelled sources `S1..S6` → strict validation → citation checks → answer composed by the backend, grouped per document → output scope guard → Postgres → JSON envelope with `grounding` and `sources`.

**M1 (`RAG_ENABLED=false` and `PROMPT_VERSION=v1`):** `POST /api/chat` → input scope guard → Groq with strict structured output → strict Pydantic validation → output scope guard → Postgres → the exact M1 envelope. This is the kill switch: it needs no redeploy.

- Calorie targets, weight targets and medical advice are declined **in code** (`backend/app/guards/`), before and after the model call. Every decline records a rule ID in `scope_events`.
- An invalid, refused or truncated model response is **never repaired or retried**: it becomes a `failures` row and the client gets `502` with a `failure_id`.
- `backend/app/llm/client.py` is the only module that imports `groq`. The API key exists only on the backend.
- **A claim with no valid citation never ships** (`backend/app/rag/citations.py`): a claim citing a label that wasn't retrieved, a number that isn't in the cited chunk, the wrong publisher, blended attribution ("the guidelines say…") or personal framing ("you should eat 30 g") is dropped and recorded in `citation_events`. If no claim survives, the request is a `502` with a `no_valid_claims` failure row.
- **Two refusals that look different:** "not covered" (in scope, `grounding.status=not_covered`, lists the documents searched) and "declined" (out of scope, referral to a professional). The corpus's own energy-requirements table is tagged restricted: if it is the best match the question is declined, and it is never shown to the model.

## Retrieval parameters (FPS §6 Rule 7)

| Parameter | Value |
|---|---|
| Chunking strategy | Structure-aware (`backend/app/rag/chunker.py`): sections from `heading_path`; a paragraph, a run of list items (with its ":" lead-in) and a table are indivisible units, packed greedily per section; an oversize table is split by row with its caption and header repeated, an oversize list between items with its lead-in repeated; sections under 60 tokens merge into the next sibling under the same parent. |
| Chunk size | Target 350, hard maximum 480 tokens, counted with the embedder's own tokenizer on the chunk text plus its context header. 209 chunks: min 43, median 189, max 480 ([build report](backend/corpus/build_report.md)). |
| Overlap | 0 tokens. Chunks end on unit boundaries; a context header (document title › section path) is prepended to every chunk instead. |
| Embedding model | `BAAI/bge-small-en-v1.5` (sentence-transformers, local, 384 dimensions, normalised, cosine). |
| Index type | pgvector on Postgres with **exact** (flat) cosine search, no ANN index; NumPy exact search on SQLite. |
| k | **6** chunks from 20 candidates, at most **2 per document** in all-documents mode (no cap when filtered to one document). |
| Score floor | **0.73**, applied in all-documents mode only. |
| Calibration run | [`evals/retrieval_runs/20261026T035839Z`](evals/retrieval_runs/20261026T035839Z/summary.md): document hit@6 100%, document recall@6 0.964, MRR 0.99. The floor keeps 95.6% of answerable questions and rejects 100% of not-in-corpus ones. The per-document cap of 2 beat 3 at every k; k=8 finds every document on more cross-document questions (0.8 vs 0.6) but adds a third more context per call. |

**What the chunking strategy cost:**

- **Uneven chunk sizes** (43–480 tokens). Small chunks embed with less context; large ones can dilute one specific fact.
- **Split tables lose cross-row context.** The cold-storage chart and the Eatwell "8 tips" table are each 4 parts, and a question spanning rows may need two chunks.
- **Lopsided list splits.** WHO's "FOR ADULTS" list splits 458 + 55 tokens, leaving the salt item alone with its lead-in.
- **Merged tiny sections** (6 merges) make the cited `section` less precise ("Glossary; Resources").
- **11 chunks stay under 60 tokens**, because they have no sibling to merge into.
- **A custom splitter** is code we maintain and test, unlike an off-the-shelf splitter.

**What the floor costs:** two answerable questions score under it ("Should non-sugar sweeteners be used to control body weight?" 0.72, "Why should raw and cooked food be kept separate?" 0.71) and get "not covered". It is not applied to filtered requests, whose top score is limited to one document; there the model's own `not_covered` is the check.

The floor is calibrated for this embedding model. Changing `EMBEDDING_MODEL` means re-running `evals/run_retrieval_eval.py` and re-setting the floor.

## Schema change (Milestone 2)

`backend/app/schemas/model_output.py` changed as M1 anticipated (FPS §4.6):

1. `claims[].source` widened from `null` to `Source | null`. Grounded claims always carry a `Source`; it is null only on the M1 path.
2. `Source` has `document_id`, `document_name`, `publisher`, `publisher_short`, `year`, `url`, `section`, `page`, `chunk_id`, `label` (the `S3` shown in the sources panel) and `excerpt`. That is more than the AP §4.1 sketch.
3. In grounded mode the model returns `GroundedOutput` (`coverage` plus claims that cite a `source_label`), not `AssistantOutput`. The backend builds `AssistantOutput` from the claims that pass the citation checks, filling `Source` from the registry and the retrieved chunk. **The model never writes a publisher, year or URL.**
4. The M1 model-facing types are kept as `UngroundedClaim` / `UngroundedOutput` (`source: null`), so the M1 path and its schema test still hold.

The API envelope gained optional fields: `grounding` (status, filter, searched documents, top score), `sources` (the retrieved chunks with a `cited` flag), `meta.claims_dropped`, `meta.corpus_version`, the `retrieval` scope stage, and `document_id` on the request. New endpoint: `GET /api/documents`. `/api/health` now reports the index.

## Local setup

Requirements: Python 3.12+, Node 20+, a Groq API key.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -e ".[embed]"   # local embedding model
# create backend/.env with the variables below (at least GROQ_API_KEY; ALLOW_UNVERIFIED_REGISTRY=true until
# the registry is verified, see backend/corpus/README.md)
alembic upgrade head
python -m app.rag.build_index --if-changed   # chunk, tag, embed, store; skips if the index is current
uvicorn app.main:app --reload            # http://localhost:8000/api/health
```

| Variable | Default | Notes |
|---|---|---|
| `GROQ_API_KEY` | — | **Required.** The server refuses to start without it. Railway only in production. |
| `MODEL_ID` | `openai/gpt-oss-120b` | Must be a Groq model that supports **strict** structured outputs (`openai/gpt-oss-120b`, `openai/gpt-oss-20b`; see Groq's structured-outputs docs). |
| `PROMPT_VERSION` | `v2` | Loads `app/llm/prompts/system_<version>.md`. Checked at startup: `v2`+ needs `RAG_ENABLED=true`, `v1` needs `false`. |
| `RAG_ENABLED` | `true` | Grounded answers. `false` (with `PROMPT_VERSION=v1`) restores M1 exactly. |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | `fake` selects the deterministic test embedder. Changing it means re-calibrating the floor. |
| `RETRIEVAL_K` / `RETRIEVAL_CANDIDATES` / `RETRIEVAL_MAX_PER_DOC` / `RETRIEVAL_MIN_SCORE` | `6` / `20` / `2` / `0.73` | From the calibration run above. |
| `CHUNK_TARGET_TOKENS` / `CHUNK_MAX_TOKENS` / `CHUNK_MIN_TOKENS` | `350` / `480` / `60` | Changing any of them changes `corpus_version` and rebuilds the index. |
| `CORPUS_DIR` | `backend/corpus` | Set to `/app/corpus` in the Docker image. |
| `ALLOW_UNVERIFIED_REGISTRY` | `false` | `true` only for local development; the index build refuses unverified registry entries otherwise. |
| `DATABASE_URL` | `sqlite:///./dev.db` | Railway's `postgres://` / `postgresql://` URLs are converted to psycopg automatically. |
| `CORS_ORIGINS` | `http://localhost:3000` | Exact origins, comma-separated. Never `*`. |
| `RATE_LIMIT` | `20/minute` | Per IP, on `/api/chat`. |
| `TRUST_PROXY` | `false` | Set `true` on Railway so the rate limit uses the real client IP (right-most `X-Forwarded-For`). |
| `LOG_LEVEL` | `INFO` | JSON logs with a request ID on every line. |

Check the key, the model ID and the schema against the real API (one call):

```bash
python scripts/smoke_llm.py "How much fibre is in oats?"
```

### Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev                              # http://localhost:3000
```

`NEXT_PUBLIC_API_BASE_URL` is fixed at **build** time, so changing it on Vercel needs a redeploy.

## Tests

```bash
cd backend && ruff check . && pytest            # corpus, chunker, tagger, index, retriever, citations, API (no torch needed)
cd backend && python -m app.rag.report --check   # corpus/build_report.md is up to date
python evals/run_retrieval_eval.py              # recall@k, MRR, floor calibration (free: local embeddings)
cd frontend && npm run lint && npx tsc --noEmit && npm test && npm run build
```

The scope-guard cases live in [backend/tests/guard_cases.yaml](backend/tests/guard_cases.yaml). A test fails if any rule in `rules.py` has no positive case. **Every missed phrasing found in evals or in production gets added there.**

## Evals and the prompt-change workflow

```bash
backend/.venv/bin/python evals/run_evals.py --base-url http://localhost:8000 [--repeat 3] [--only NUT-01,MT-02]
```

Each run writes `evals/runs/<UTC timestamp>_<prompt_version>/` with `results.jsonl`, `summary.md` and `meta.json`. The summary diffs against the latest complete run **with the same model**. The runner throttles to one request every 3.5 s to stay under the rate limit, retries `429`s, and records them separately from model results. Exit code `1` means regressions, `2` means the run was interrupted (never use a partial run as a baseline).

The runner asks the target's `/api/health` whether it is grounded (`--mode auto`). Grounded runs add the Milestone 2 groups (`GRD`, `XDOC`, `NIC`, `FILT`, `RESTR`, `CITE`) and checks: every claim has a complete source, no blend phrases, filters respected, `claims_dropped` reported. They also add the T8–T14 table, and diff only against earlier grounded runs.

[evals/questions.yaml](evals/questions.yaml) is **append-only**. To fix a question, mark it `deprecated: true` and add a new ID.

To change the system prompt:

1. Copy `backend/app/llm/prompts/system_vN.md` to `system_vN+1.md` and edit the copy.
2. Bump `PROMPT_VERSION`.
3. Run the evals.
4. Commit the prompt, its [CHANGELOG](backend/app/llm/prompts/CHANGELOG.md) entry and the eval run together, and update [Docs/evalResults.md](Docs/evalResults.md).
5. Merge only if the run has no regressions.

The `Evals` GitHub workflow runs the suite against a deployed URL. It is manual-trigger only because it spends API credits.

## Deploy (Phase 9; Milestone 2 changes in Phase 10)

**Milestone 2 changes:**

- **Image:** the image installs CPU-only torch and bakes the bge model in (`HF_HUB_OFFLINE=1`). It also copies `corpus/`, and its start command builds the index (`--if-changed`) before uvicorn.
- **Health check:** `railway.json` waits up to 300 s, and `/api/health` returns `503` until the index is ready, so a broken build never takes traffic.
- **Postgres:** Railway Postgres needs the `vector` extension. Check that `CREATE EXTENSION vector` works, or move to Railway's pgvector template.
- **Railway variables:** add `RAG_ENABLED=true`, `PROMPT_VERSION=v2`, the retrieval settings above and `ALLOW_UNVERIFIED_REGISTRY=false`.
- **Memory:** the embedder and torch need roughly 0.5–1 GB more RAM, so check the plan.
- **Registry:** the production start fails until every registry entry is verified (`backend/corpus/README.md`).
- **Kill switch:** set `RAG_ENABLED=false` and `PROMPT_VERSION=v1`. Migration `0002` is additive, so the M1 image also runs on the M2 schema.

**Steps:**

1. **Railway:** create a project from this repo with root directory `backend/` (it uses `Dockerfile` and `railway.json`), and add the Postgres plugin.
   - Set `GROQ_API_KEY`, `MODEL_ID`, `PROMPT_VERSION=v1`, `TRUST_PROXY=true`, `CORS_ORIGINS=https://<prod>.vercel.app` and reference `DATABASE_URL`.
   - Migrations run on every start, so keep **one replica**.
2. **Vercel:** import the repo with root directory `frontend/` and set `NEXT_PUBLIC_API_BASE_URL=https://<backend>.up.railway.app`.
3. **Checks:**
   - There is no `gsk_` string (Groq key prefix) in the JS bundle (CI also checks this).
   - The browser only calls the Railway domain.
   - 21 fast requests produce a `429`.
   - The production eval run is committed.

If requests suddenly fail with `api_error`, check the Groq usage limits before debugging the code.

## Decisions taken on open edge cases

These close the ❓ and ⚠️ items in [edgeCases.md](Docs/edgeCases.md). Record them there too.

**Request input**

| Case | Decision |
|---|---|
| IN-06 | Control characters (except `\n`, `\t`) are stripped from messages. |
| IN-08 | Unknown request fields return `422`. |
| CONV-01 | One turn is one user message. The cap is 50, and going over it returns `422 conversation_turn_limit`. |
| CONV-03/04 | The history window always starts on a user turn. An unanswered user turn (its request failed) is dropped. |
| CONV-05, SCOPE-09 | Declined exchanges are left out of the history sent to the model. A short follow-up after a decline ("just a rough number") stays declined in the same category. |

**Scope rules**

| Case | Decision |
|---|---|
| SCOPE-05 | An exception cancels only the match it overlaps, and rules are tried at every position. |
| SCOPE-08 | If the new message passes, it is checked again together with the previous user turn. |
| SCOPE-12 | A model answer with no claims, a refusal and a referral is reported as `declined`, `stage: "model"`, rule `OUT-MODEL-01`. |
| SCOPE-18 | Calories burned by an activity is allowed. |
| SCOPE-20 | Sentences where the model refuses are skipped by the output guard. |
| SCOPE-27 | Category priority is medical > weight > calorie. Every matched rule is stored in `scope_events.matched_rules`. |

**Borderline questions (§4.3)**

| Case | Decision |
|---|---|
| SCOPE-B1 | Pregnancy food-safety questions about a named food are allowed. |
| SCOPE-B2 | A general BMI range is allowed. |
| SCOPE-B3, SCOPE-22 | Population calorie figures are declined, both at input and output. |
| B4, B5, B7 | Declined as `medical_advice` when a condition is disclosed or management is asked for. |
| B6 | "Is gluten bad for you?" is allowed; the celiac question is declined. |

**Frontend**

| Case | Decision |
|---|---|
| FE-04 | Retry after a `502` sends the message again, so the server stores two copies of the user message. Accepted for M1. |
| FE-07 | Every error status uses `{error, failure_id, detail}`. |
| FE-10 | Answers render as plain text. |

**Model call**

| Case | Decision |
|---|---|
| LLM-04 | Any `stop_reason` other than `end_turn`, `max_tokens` or `refusal` is recorded as `schema_invalid`. |

**Structured output:** the model runs on Groq via the official `groq` SDK: `chat.completions.create` with `response_format={"type": "json_schema", "json_schema": {"strict": true, "schema": <AP §4.1 schema>}}`. The raw text is validated by us, so `finish_reason` is checked first (`length` → `truncated_output`; `content_filter` or a `refusal` field → `model_refusal`; anything but `stop` → failure) and the raw text is kept for the `failures` row. `reasoning_effort="low"` and `include_reasoning=false` are sent alongside the format.

**Known gaps:**

- The regex guards only know English. EC-07 and EC-08 in the evals measure this.
- Two simultaneous requests on one conversation can exceed the turn cap by one (accepted for M1).
- Conversations are anonymous: anyone with the ID can read one.
