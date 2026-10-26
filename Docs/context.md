# AI Nutrition Assistant: Project Context

One-file summary of the project, drawn from [problemStatement.md](problemStatement.md) (**PS**), [architecturePlan.md](architecturePlan.md) (**AP**) and [implementationPlan.md](implementationPlan.md) (**IP**). Read this first; go to the source docs for full detail.

---

## 1. What the Project Is

A prototype chatbot that answers general questions about **food, nutrition and food safety**.

It is built in milestones:

| Milestone | Focus | Spec |
|---|---|---|
| **1 (current build)** | **Ungrounded** chatbot. The model answers from its own memory. Fixed response schema with `source: null` on every claim, scope guardrails in code, deployed publicly. The real deliverable is a **written record of what the model makes up**. | [problemStatement.md](problemStatement.md) |
| **2 (next)** | Retrieval over official dietary guidance documents. Real citations on every claim, populated sources panel, two kinds of refusal. | [featureProblemStatement.md](featureProblemStatement.md) |

**Why Milestone 1 exists (PS §2):** a model answers "how much protein does a vegetarian need?" in 2 seconds with a specific-sounding number that **comes from nobody**, changes from day to day, and may be attributed to an authority that never said it. In food, a wrong answer reads exactly like a right one. M1 builds the shell and guardrails, then **measures and records** this behaviour as a baseline for M2.

---

## 2. Non-Negotiable Rules (PS §5)

1. **Every response parses** against the schema. If it doesn't, the request fails.
2. The schema **has a claims list** and a **`source` field on each claim**.
3. **`source` stays `null`** in M1.
4. **Scope limits live in code**, not only in the prompt.
5. The app is **live at a public URL**.
6. **Failures are recorded, not patched around.** No silent repair, no hidden retries.
7. **Model calls run only on the backend.** The API key never reaches the browser.

**Out of scope (PS §3.5):** calorie targets, weight targets, what anyone should weigh, medical advice. The assistant declines these and refers the person to a **qualified professional** (registered dietitian, doctor, pharmacist).

---

## 3. Stack (AP §1)

| Area | Choice |
|---|---|
| Frontend | Next.js (App Router, TypeScript) + Tailwind, on **Vercel** |
| Backend | FastAPI (Python 3.12) + Pydantic, on **Railway** |
| Model | **Groq** via the official `groq` SDK (`chat.completions.create`) with **strict structured outputs** (`response_format` `json_schema`, `strict: true`). Model ID from env `MODEL_ID` (code default `openai/gpt-oss-120b`; must be a Groq model that supports strict mode). Switched from Anthropic Claude on 2026-10-26 |
| Storage | SQLAlchemy 2 + Alembic: **SQLite** locally, **Postgres** on Railway |
| Repo | One GitHub monorepo: `frontend/`, `backend/`, `evals/`, `Docs/` |

Trust boundary: browser → our backend only. `GROQ_API_KEY` exists only in Railway env vars.

---

## 4. Request Flow (AP §2, §5.2)

```
POST /api/chat
  → load/create conversation, save user message
  → input scope guard ──(out of scope)──► decline envelope (model NOT called), scope_event(stage=input)
  → Groq model, strict structured output (system prompt + last 10 turns)
  → stop_reason check + strict Pydantic re-validation
        └─(invalid / refusal / truncated / API error)──► failures row, HTTP 502 {error, failure_id}
  → output scope guard ──(leak)──► discard output, decline envelope, scope_event(stage=output, raw_output kept)
  → save assistant message → 200 envelope
```

### Endpoints (AP §5.1)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/chat` | `{conversation_id?, message}` → envelope. Message 1–2,000 chars; 50-turn cap; 20 req/min per IP (`429`) |
| `GET` | `/api/conversations/{id}` | Full history, used to restore the chat after reload |
| `GET` | `/api/health` | Liveness + DB check (`{"status":"ok","db":"ok"}`) |

---

## 5. Response Contract (PS §3.3, AP §4)

**Model output** (`backend/app/schemas/model_output.py`, the only place it is defined):

```python
class Claim(BaseModel):            # extra="forbid"
    text: str                      # min_length=1
    source: None = None            # JSON Schema {"type": "null"}; any non-null value fails

class AssistantOutput(BaseModel):  # extra="forbid"
    answer: str                    # min_length=1
    claims: list[Claim]
```

- `source` is typed **`null`**, so Rule 3 is enforced by the type system, not by the prompt.
- This file **changes only in Milestone 2** (`source: None` → `source: Source | None`). Any earlier change needs a written reason in the PR.

**Validation (AP §4.2):** check `stop_reason` first (`max_tokens` → `truncated_output`, `refusal` → `model_refusal`), then re-validate `parsed_output` strictly. Any failure writes a `failures` row and returns `502`. **No repair, no hidden retries**; SDK retries (`max_retries=2`) cover transport errors only.

**API envelope (backend → frontend):**

```json
{
  "conversation_id": "…", "message_id": "…",
  "answer": "…",
  "claims": [{ "text": "…", "source": null }],
  "scope": { "status": "in_scope" },
  "meta": { "prompt_version": "v1", "model": "…", "latency_ms": 1840 }
}
```

A decline uses the **same shape**: `scope = {status: "declined", category, stage}`, `claims: []`, `answer` = referral text. The frontend has one rendering path.

---

## 6. Scope Enforcement in Code (AP §6, IP Phase 5)

Three layers: prompt, **input guard**, **output guard**. The code layers work even if the prompt is ignored.

| Category | Declined | Stays in scope |
|---|---|---|
| `calorie_target` | "How many calories should I eat to lose weight?" | "How many calories are in an avocado?", "What is a calorie?" |
| `weight_target` | "What's my ideal weight?", "How much should I lose?" | "What is BMI?" |
| `medical_advice` | condition + advice verb ("I have diabetes, can I eat mangoes?"), medication changes | "Which foods contain vitamin D?", "How long can cooked rice sit out?" |

- **Input guard** (`guards/input_guard.py`): normalise text (`normalize.py`: lowercase, `kcal`→`calories`, units), match regex rules from `rules.py`, apply allow-list exceptions (composition and definition questions). Rule IDs: `IN-CAL-*`, `IN-WT-*`, `IN-MED-*`.
- **Output guard** (`guards/output_guard.py`): scans `answer` and every `claims[].text` for personal targets, weight prescriptions and medical directives. Rule IDs: `OUT-CAL-*`, `OUT-WT-*`, `OUT-MED-*`. A hit discards the output and stores it in `scope_events.raw_output`.
- **Decline texts** (`guards/decline.py`): fixed, schema-valid, `claims: []`, **no digits**. Calorie/weight variant → registered dietitian or doctor; medical variant → doctor or pharmacist.
- Rules are data, every decline traces to a rule ID, and a test fails if any rule has no positive case in `backend/tests/guard_cases.yaml` (40+ cases).
- Optional hardening if regexes miss too much: a small structured-output classifier call, with regex kept as the floor.

---

## 7. Data Model (AP §7)

| Table | Key fields |
|---|---|
| `conversations` | `id`, `created_at`, `updated_at` |
| `messages` | `conversation_id`, `role` (user/assistant), `content`, `claims` (JSON), `status` (ok/declined), `prompt_version`, `model`, `latency_ms`, `input_tokens`, `output_tokens` |
| `failures` | `type` (`schema_invalid` / `model_refusal` / `truncated_output` / `api_error`), `error_detail`, `raw_output`, `request_context` |
| `scope_events` | `stage` (input/output), `category`, `rule_id`, `raw_output` (output stage only) |

`claims` is JSON (JSONB on Postgres), so M2 source objects need no migration. Every assistant message records `prompt_version` and `model`. M1 migrations are **additive only**, so a rolled-back backend still works on the newer schema.

---

## 8. System Prompt (PS §3.4, AP §8)

Lives in `backend/app/llm/prompts/system_v1.md`, versioned by filename. Five sections:

1. **Role:** general-information assistant for food, nutrition and food safety.
2. **How to answer:** plain language; state uncertainty; no invented statistics or authority attributions; break every factual statement into atomic `claims`, `source` always null. Opinions and caveats are not claims.
3. **Length:** usually 60–150 words, max 200; short paragraphs or up to 5 bullets; no preamble.
4. **Won't touch:** calorie/weight targets, BMI goals, medical advice → brief decline + referral. Off-domain → one-line redirect.
5. **Format:** respond only in the required JSON schema.

**Prompt-change workflow:** copy to `system_vN+1.md` → bump `PROMPT_VERSION` → run evals → commit the prompt, a `CHANGELOG.md` entry and the eval run together → merge only with **no regressions**.

---

## 9. Evals and the Failure Log (AP §9, IP Phases 8 & 10)

- **Question set** `evals/questions.yaml`: ~30 base questions (now 55 entries), **append-only** (fix a question by marking it `deprecated: true` and adding a new ID). Groups: general nutrition, food safety, food composition (must **not** be declined), calorie targets, weight targets, medical, off-domain/adversarial, plus multi-turn cases.
- **Runner** `evals/run_evals.py --base-url … [--repeat N] [--only IDs]`: one fresh conversation per question against the real `/api/chat`. Automatic checks: HTTP 200, envelope validates, every `source is None`, scope status/category match, word and claim counts. Writes `evals/runs/<UTC timestamp>_<prompt_version>/` (`results.jsonl`, `summary.md`, `meta.json`) with a diff against the previous complete run on the same model. Exit `1` = regressions, `2` = interrupted run (never a baseline). `--repeat` flags **drift** (numbers that change between repeats).
- **Acceptance thresholds** ([evalResults.md](evalResults.md)): 100% schema pass, 100% `source === null`, 100% decline recall, 0 composition/must-allow false positives, 0 regressions, all failures recorded.
- **Failure log** ([failureLog.md](failureLog.md)): the M1 deliverable. A person reviews in-scope answers and logs doubtful claims as `fabricated_number`, `fake_authority`, `drift`, `overconfident`, `outdated` or `unverified_by_reviewer`, plus summaries of the `failures` and `scope_events` tables and headline metrics (schema pass rate, decline precision/recall, claims reviewed, claims flagged, drift rate).

---

## 10. Frontend (PS §3.1, AP §10, IP Phase 7)

Two-column layout on desktop (chat ~65%, sources ~35%); on mobile the sources panel is a drawer.

| Component | Behaviour |
|---|---|
| `MessageList` | Auto-scroll, typing indicator, example-question chips when empty, `aria-live="polite"` |
| `MessageBubble` | Answer + collapsible "Claims (n)", each with an **"Unverified"** badge; declines in a distinct (amber) style with no claims |
| `ChatInput` | Enter sends, Shift+Enter newline, 2,000-char counter, disabled while sending |
| `SourcesPanel` | Renders `claims.filter(c => c.source !== null)` for the selected message. Always empty in M1: *"No sources yet. Answers are currently generated from the model's memory and are not verified."* M2 needs no component change |
| `ErrorBanner` | `502` → "invalid response (ref: failure_id)" + Retry; `429` → "Too many requests" |

`conversation_id` is kept in `localStorage` (try/catch) and history reloads via `GET /api/conversations/{id}`. Footer: "General information only, not medical advice."

---

## 11. Deployment (AP §11, IP Phase 9)

| Piece | Host | Notes |
|---|---|---|
| Frontend | Vercel, root `frontend/` | `NEXT_PUBLIC_API_BASE_URL` is inlined **at build time**, so redeploy after changing it |
| Backend | Railway, root `/backend`, config `/backend/railway.json` (set explicitly), watch `/backend/**`, 1 replica, "Wait for CI" on | Dockerfile runs `alembic upgrade head && uvicorn …` |
| Database | Railway Postgres | `DATABASE_URL=${{Postgres.DATABASE_URL}}`, normalised to `postgresql+psycopg://` |

**Backend env vars:** `GROQ_API_KEY` (sealed, required to boot), `MODEL_ID`, `PROMPT_VERSION` (must match a prompt file or startup fails), `DATABASE_URL`, `CORS_ORIGINS` (exact origins, never `*`), `TRUST_PROXY=true` on Railway, `RATE_LIMIT` (default `20/minute`), `LOG_LEVEL`.

Deploy order: backend URL → frontend env var → frontend URL → backend CORS. Vercel preview deploys can't call the prod API (accepted in M1; never open CORS to `*`). Rollback: Railway "Redeploy" a previous deployment; Vercel "Instant Rollback".

---

## 12. Build Phases (IP)

| # | Phase | Exit gate (summary) |
|---|---|---|
| 0 | Prereqs and accounts | Python 3.12, Node 20, API key in git-ignored `.env`, empty repo |
| 1 | Scaffold, CI, walking skeleton | Both apps boot; CI green; public Vercel URL shows `ok` from Railway |
| 2 | Response contract | Schema tests pass; generated schema has `source: {"type":"null"}` |
| 3 | Persistence | `alembic upgrade head` works; repo tests pass; health reports DB |
| 4 | Model client + failure recorder | Mocked tests pass; smoke script works; only `llm/client.py` imports the model SDK (now `groq`) |
| 5 | Scope guards | Guard + coverage tests pass; every "must allow" case allowed |
| 6 | Chat service + API | All API branch tests pass; manual curl works |
| 7 | Frontend | Full conversation works locally; mocked 502 shows failure ID |
| 8 | System prompt v1 + evals | First run committed; 100% schema/source checks; failures listed, not suppressed |
| 9 | Production deploy | Works from outside network; health ok; CORS correct; prod eval run committed |
| 10 | Baseline + failure log | `failureLog.md` reviewed; PS §6 ticked with evidence; `m1` tag |

Dependencies: 2 → {3, 4, 5}; {3, 4, 5} → 6; 6 → {7, 8}; {7, 8} → 9 → 10. About 9 working days for one developer.

**Practices:** one branch per phase merged by PR with CI passing; prompt changes committed with their eval run; secrets never committed; every failure and guard hit produces a DB row; usage limits set in the Groq console; eval CI job is manual-trigger only.

---

## 13. Current Status (as of 2026-10-26)

| Area | State |
|---|---|
| Backend (contract, DB, model client, guards, chat API, rate limit, logging) | Code present in `backend/app/`, with tests in `backend/tests/` |
| Frontend (all components + `useChat`, `api.ts`, `types.ts`) | Code present in `frontend/` |
| Prompt | `system_v1.md` (M1) and `system_v2.md` (grounded) + `CHANGELOG.md` |
| Evals | 83-entry question set (28 Milestone 2 questions) and runner with M1/M2 modes. **3 M1 runs committed, all against a local `stub-model`. No real-model run yet, M1 or M2** |
| Milestone 2 code | Built ([featureImplementationPlan.md](featureImplementationPlan.md) Phases 1–9). Corpus and registry, chunker, tagger, embedder, pgvector/SQLite store, migration `0002_rag`, retriever, citation checks, composer, grounded chat flow, `/api/documents`, frontend sources panel and filter. 392 backend and 22 frontend tests pass |
| Retrieval eval | Run `evals/retrieval_runs/20261026T035839Z`: doc recall@6 0.964, MRR 0.99, k=6, cap 2, floor 0.73 |
| Registry | `backend/corpus/documents.json` has `year` and `url` null and nothing verified. The production index build refuses it, so it **blocks deploy** |
| Deploy | **Not yet** (M1 or M2) |
| [evalResults.md](evalResults.md), [failureLog.md](failureLog.md) | M1 sections are templates. M2 sections hold the real retrieval run and pre-model findings only. Fill the rest from real runs, never estimate |
| `m1` / `m2` tags | Not created |

Remaining: verify the registry → real-model M1 baseline run (`RAG_ENABLED=false PROMPT_VERSION=v1`) → grounded run (`v2`) → Railway (pgvector, new image) and Vercel deploy → production eval run → citation review and failure log → tick FPS §7 → tags.

---

## 14. Key Files

| Path | Role |
|---|---|
| `backend/app/schemas/model_output.py` | The structured-output contract |
| `backend/app/schemas/api.py` | Request/response envelopes |
| `backend/app/llm/client.py` | The only module that calls the Groq SDK |
| `backend/app/llm/prompts/system_v1.md` | Versioned system prompt |
| `backend/app/guards/` | `rules.py`, `normalize.py`, `input_guard.py`, `output_guard.py`, `decline.py`, `matching.py` |
| `backend/app/services/chat_service.py` | Orchestrates guard → model → validate → guard → persist |
| `backend/app/failures.py` | Failure recorder |
| `backend/app/db/` | Models, session, repo, Alembic migrations |
| `backend/tests/guard_cases.yaml` | Table-driven guard cases; add every missed phrasing here |
| `frontend/components/`, `frontend/lib/` | Chat UI, typed API client, `useChat` hook |
| `evals/questions.yaml`, `evals/run_evals.py`, `evals/runs/` | Regression suite, runner, committed runs |
| `Docs/edgeCases.md` | Edge cases referenced as **EC** in the plans |
| `Docs/featureProblemStatement.md`, `backend/corpus/blocks.jsonl` | Milestone 2 spec and corpus (moved from `Docs/blocks.json`) |
| `backend/corpus/documents.json` | Document registry: title, publisher, year, URL per `document_id` (human-verified) |
| `backend/app/rag/` | Milestone 2 retrieval layer: corpus loader, chunker, tagger, build report |
