# AI Nutrition Assistant (Milestone 2: grounded answers)

A chat assistant for general questions about food, nutrition and food safety.

- **Milestone 1** was deliberately **ungrounded**: answers came from the model's memory and every `source` was `null` ([Docs/problemStatement.md](Docs/problemStatement.md)).
- **Milestone 2** answers **only from 7 official public guidance documents**. Every claim carries a citation (document, publisher, year, link), cross-document answers stay separate per document, and when the guidance doesn't cover a question the assistant says so and names what it searched ([Docs/featureProblemStatement.md](Docs/featureProblemStatement.md), [plan](Docs/featureImplementationPlan.md)).

- **Frontend:** Next.js 16 + Tailwind, to be deployed on Vercel ([frontend/](frontend/)). Chat with citation chips, a sources panel showing the retrieved excerpts, and a **"Select theme"** filter (5 themes, each a group of the 7 documents).
- **Backend:** FastAPI + SQLAlchemy, to be deployed on Railway with Postgres + pgvector ([backend/](backend/)). The embedding model runs inside the backend container.
- **Model:** `openai/gpt-oss-120b` on **Groq**, with strict structured output. The brief allowed the Anthropic or OpenAI API; Groq is a documented deviation ([problemStatement.md](Docs/problemStatement.md) §4).
- **Evals:** fixed, append-only regression question set (83 entries) and runner ([evals/](evals/)), plus a retrieval eval.
- **Corpus:** 1,001 parsed blocks from 7 documents, a verified document registry and the theme list ([backend/corpus/](backend/corpus/)).
- **Plans:** M1 [problemStatement.md](Docs/problemStatement.md), [architecturePlan.md](Docs/architecturePlan.md), [implementationPlan.md](Docs/implementationPlan.md) (Phase 9 is the deploy plan), [edgeCases.md](Docs/edgeCases.md); M2 [featureProblemStatement.md](Docs/featureProblemStatement.md), [featureArchitecturePlan.md](Docs/featureArchitecturePlan.md), [featureImplementationPlan.md](Docs/featureImplementationPlan.md). Results: [evalResults.md](Docs/evalResults.md), [failureLog.md](Docs/failureLog.md).

Public URLs: _not deployed yet; added after the [Phase 9](Docs/implementationPlan.md#phase-9-production-deploy) deploy._

## Status (2026-10-28)

| Milestone | State | Open |
|---|---|---|
| **1: ungrounded baseline** ([PS](Docs/problemStatement.md)) | Built and measured. 9 of 12 acceptance items ticked with evidence ([PS §6](Docs/problemStatement.md#6-acceptance-checklist)) | Public deploy; human review of the M1 claims ([failureLog.md](Docs/failureLog.md) §1–§4); push and merge the M2 branch |
| **2: grounded answers** ([FPS](Docs/featureProblemStatement.md)) | Built. Grounded real-model runs on 2026-10-27 met T8–T12 | Public deploy; human citation review ([failureLog.md](Docs/failureLog.md) §6) |

**What grounding changed** (same 55 questions, same model, 3 repeats each; [failureLog.md](Docs/failureLog.md) §5):

| Measure | M1 (model memory) | M2 (grounded) |
|---|---|---|
| Claims with a source | 0 of 333 | every claim (173 of 173 across all 83 questions) |
| Questions whose numbers changed between repeats | 17 of 55 (a banana was 90, 105, 120, 130 or 135 calories) | 0 of 55 |
| In-scope questions answered | 24, all unverifiable | 7 grounded with citations; 16 "not covered", naming the documents searched |

The cost of grounding is coverage: the 7 documents hold no food-composition data and few food-safety specifics, so those questions are now answered "not covered" instead of with invented numbers.

## How a request flows

**Grounded (M2, `RAG_ENABLED=true`, the default):** `POST /api/chat` → input scope guard → retrieve (embed query → exact cosine search over all documents, or only the chosen theme's or document's, k=6, at most 2 per document) → restricted top hit? decline → top score under the floor? "not covered" → Groq with strict structured output over labelled sources `S1..S6` → strict validation → citation checks → answer composed by the backend, grouped per document → output scope guard → Postgres → JSON envelope with `grounding` and `sources`.

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

The API envelope gained optional fields: `grounding` (status, filter, searched documents, top score), `sources` (the retrieved chunks with a `cited` flag), `meta.claims_dropped`, `meta.corpus_version`, the `retrieval` scope stage, and `document_id` and `theme_id` on the request (one or the other). New endpoints: `GET /api/documents` and `GET /api/themes`. `/api/health` now reports the index.

**Themes.** The UI's "Select theme" filter offers the 5 themes in `backend/corpus/themes.json`. Each names a group of registry documents; a themed request searches only those documents (the 0.73 floor still applies, and the per-document cap rises to `ceil(k / documents)` so a two-document theme can fill k slots). The file is checked against the registry when loaded, and a test requires every document to be in some theme.

## Local setup

Requirements: Python 3.12+, Node 20+, a Groq API key.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -e ".[embed]"   # local embedding model
# create backend/.env with the variables below (at least GROQ_API_KEY)
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

Each run writes `evals/runs/<UTC timestamp>_<prompt_version>/` with `results.jsonl`, `summary.md` and `meta.json`. The summary diffs against the latest complete run **with the same model**. The runner paces requests (one every 3.5 s in M1 mode, 10 s in grounded mode; `--delay` overrides) and slows down by itself after a rate limit. It retries `429`s and Groq's `503 upstream_rate_limited`, honouring `Retry-After`. Requests that never get an answer are recorded as excluded, separately from model results, and a question is scored on the repeats that were answered. `--rescore RUN_DIR` rebuilds a run's summary from its stored results without calling the model. Exit code `1` means regressions, `2` means the run was interrupted (never use a partial run as a baseline).

The runner asks the target's `/api/health` whether it is grounded (`--mode auto`). Grounded runs add the Milestone 2 groups (`GRD`, `XDOC`, `NIC`, `FILT`, `RESTR`, `CITE`) and checks: every claim has a complete source, no blend phrases, filters respected, `claims_dropped` reported. They also add the T8–T14 table, and diff only against earlier grounded runs.

[evals/questions.yaml](evals/questions.yaml) is **append-only**. To fix a question, mark it `deprecated: true` and add a new ID.

To change the system prompt:

1. Copy `backend/app/llm/prompts/system_vN.md` to `system_vN+1.md` and edit the copy.
2. Bump `PROMPT_VERSION`.
3. Run the evals.
4. Commit the prompt, its [CHANGELOG](backend/app/llm/prompts/CHANGELOG.md) entry and the eval run together, and update [Docs/evalResults.md](Docs/evalResults.md).
5. Merge only if the run has no regressions.

The `Evals` GitHub workflow runs the suite against a deployed URL. It is manual-trigger only because it spends API credits.

**Groq quota.** The free tier allows `openai/gpt-oss-120b` 8,000 tokens a minute and **200,000 tokens a day**. A grounded answer uses about 3,000 tokens, so a full grounded run with `--repeat 3` (about 200 model calls) does not fit in one day. Use `--repeat 1`, split the run across days, or upgrade the tier. When Groq refuses a request, the failure's `error_detail` names the limit that was hit.

## Deploy

Backend and Postgres on **Railway**, frontend on **Vercel**. The full checklist (order, every setting and variable, the checks, release and rollback, and troubleshooting) is **Phase 9 of [implementationPlan.md](Docs/implementationPlan.md#phase-9-production-deploy)**. This is the summary.

| Piece | Host | Built from |
|---|---|---|
| Frontend | Vercel, `https://<project>.vercel.app` | `frontend/` |
| Backend | Railway, `https://<backend>.up.railway.app` | `backend/Dockerfile` + `backend/railway.json` |
| Database | Railway Postgres **with pgvector**, same project | Railway template |

**On every start** the backend container runs `alembic upgrade head` → `python -m app.rag.build_index --if-changed` (rebuilds the 209-chunk index only if the corpus, chunker settings or model changed) → uvicorn. The image has CPU-only torch and the bge model baked in (`HF_HUB_OFFLINE=1`), so nothing is downloaded at runtime. `/api/health` returns `503` until the database and the index are ready, and `railway.json` gives the health check 300 s.

**Order:** database → backend → frontend → CORS. Each step needs a value from the one before.

1. **Railway database:** add PostgreSQL (name it `Postgres`) and run `CREATE EXTENSION IF NOT EXISTS vector;` in its SQL console. If that fails, use Railway's pgvector template instead.
2. **Railway backend:** deploy from this repo with **Root Directory** `/backend`, **Config File Path** `/backend/railway.json`, **Watch Paths** `/backend/**`, **Wait for CI** on, no custom start command, one replica, at least 1 GB of memory. Variables:
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`, `GROQ_API_KEY` (sealed), `MODEL_ID=openai/gpt-oss-120b`
   - `RAG_ENABLED=true`, `PROMPT_VERSION=v2`, `ALLOW_UNVERIFIED_REGISTRY=false`
   - `CORS_ORIGINS=https://<project>.vercel.app`, `TRUST_PROXY=true`
   - leave the `RETRIEVAL_*`, `CHUNK_*` and `EMBEDDING_MODEL` settings unset (the defaults are the calibrated values) and don't set `PORT`
3. **Vercel frontend:** import the repo with **Root Directory** `frontend` and set `NEXT_PUBLIC_API_BASE_URL=https://<backend>.up.railway.app` for Production. It is inlined at build time, so redeploy after changing it. Use the same Node major version as CI.
4. **CORS:** make sure `CORS_ORIGINS` is the exact Vercel production origin, then check the preflight with `curl -si -X OPTIONS …/api/chat -H "Origin: https://<project>.vercel.app" -H "Access-Control-Request-Method: POST"`.

**Checks after deploying:**

- `/api/health` shows `db: ok` and the index `ready` with 209 chunks; `/api/documents` lists 7 documents with years and links; `/api/themes` lists 5 themes.
- In the browser: the theme dropdown appears, an answer shows citation chips and sources, an off-theme question gets "not covered" naming only that theme's documents, and a calorie-target question is declined.
- There is no `gsk_` string (the Groq key prefix) in the JS bundle (CI also checks this), and the browser calls only the Railway domain.
- 21 fast requests produce a `429` (use a declined question, which never calls Groq).
- Run the evals against production with `--repeat 1`, commit the run and update [evalResults.md](Docs/evalResults.md). Then add the public URLs above.

**Before real use:** the free Groq tier gives the whole deployment about 60 grounded answers a day. After that the UI shows "The assistant is busy right now". Upgrade the Groq tier and set a spend limit.

**Release and rollback:**

- **Release:** merging to `main` deploys only what changed. Railway redeploys `backend/` after CI passes, and Vercel rebuilds `frontend/`.
- **Kill switch:** `RAG_ENABLED=false` with `PROMPT_VERSION=v1` restores the exact M1 behaviour with no code deploy. The theme filter hides itself.
- **Rollback:** migrations are additive, so Railway can redeploy an older image on the newer schema. Vercel has Instant Rollback.
- **Registry changes:** any new or edited registry entry must be verified (`backend/corpus/README.md`), or the production start refuses it.

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
