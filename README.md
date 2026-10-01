# AI Nutrition Assistant (Milestone 1 prototype)

A chat assistant for general questions about food, nutrition and food safety. Milestone 1 is deliberately **ungrounded**: answers come from the model's memory, every answer is split into claims whose `source` is always `null`, and the goal is to record what the model makes up (see [Docs/problemStatement.md](Docs/problemStatement.md)).

- **Frontend:** Next.js + Tailwind, deployed to Vercel ([frontend/](frontend/))
- **Backend:** FastAPI + SQLAlchemy, deployed to Railway with Postgres ([backend/](backend/))
- **Evals:** fixed regression question set and runner ([evals/](evals/))
- **Plans:** [architecturePlan.md](Docs/architecturePlan.md), [implementationPlan.md](Docs/implementationPlan.md), [edgeCases.md](Docs/edgeCases.md)

Public URLs: _to be added after the Phase 9 deploy._

## How a request flows

`POST /api/chat` → input scope guard → Claude with structured output → strict Pydantic validation → output scope guard → Postgres → JSON envelope.

- Calorie targets, weight targets and medical advice are declined **in code** (`backend/app/guards/`), before and after the model call. Every decline records a rule ID in `scope_events`.
- An invalid, refused or truncated model response is **never repaired or retried**: it becomes a `failures` row and the client gets `502` with a `failure_id`.
- `backend/app/llm/client.py` is the only module that imports `anthropic`. The API key exists only on the backend.

## Local setup

Requirements: Python 3.12+, Node 20+, an Anthropic API key.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# create backend/.env with the variables below (at least ANTHROPIC_API_KEY)
alembic upgrade head
uvicorn app.main:app --reload            # http://localhost:8000/api/health
```

| Variable | Default | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** The server refuses to start without it. Railway only in production. |
| `MODEL_ID` | `claude-opus-5` | Any current Claude model ID. |
| `PROMPT_VERSION` | `v1` | Loads `app/llm/prompts/system_<version>.md`. Checked at startup. |
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
cd backend && ruff check . && pytest            # schema, repo, model client (mocked), guards, API
cd frontend && npm run lint && npx tsc --noEmit && npm test && npm run build
```

The scope-guard cases live in [backend/tests/guard_cases.yaml](backend/tests/guard_cases.yaml). A test fails if any rule in `rules.py` has no positive case. **Every missed phrasing found in evals or in production gets added there.**

## Evals and the prompt-change workflow

```bash
backend/.venv/bin/python evals/run_evals.py --base-url http://localhost:8000 [--repeat 3] [--only NUT-01,MT-02]
```

Each run writes `evals/runs/<UTC timestamp>_<prompt_version>/` with `results.jsonl`, `summary.md` and `meta.json`. The summary diffs against the latest complete run **with the same model**. The runner throttles to one request every 3.5 s to stay under the rate limit, retries `429`s, and records them separately from model results. Exit code `1` means regressions, `2` means the run was interrupted (never use a partial run as a baseline).

[evals/questions.yaml](evals/questions.yaml) is **append-only**. To fix a question, mark it `deprecated: true` and add a new ID.

To change the system prompt:

1. Copy `backend/app/llm/prompts/system_vN.md` to `system_vN+1.md` and edit the copy.
2. Bump `PROMPT_VERSION`.
3. Run the evals.
4. Commit the prompt, its [CHANGELOG](backend/app/llm/prompts/CHANGELOG.md) entry and the eval run together, and update [Docs/evalResults.md](Docs/evalResults.md).
5. Merge only if the run has no regressions.

The `Evals` GitHub workflow runs the suite against a deployed URL. It is manual-trigger only because it spends API credits.

## Deploy (Phase 9)

1. **Railway:** create a project from this repo with root directory `backend/` (it uses `Dockerfile` and `railway.json`), and add the Postgres plugin.
   - Set `ANTHROPIC_API_KEY`, `MODEL_ID`, `PROMPT_VERSION=v1`, `TRUST_PROXY=true`, `CORS_ORIGINS=https://<prod>.vercel.app` and reference `DATABASE_URL`.
   - Migrations run on every start, so keep **one replica**.
2. **Vercel:** import the repo with root directory `frontend/` and set `NEXT_PUBLIC_API_BASE_URL=https://<backend>.up.railway.app`.
3. **Checks:**
   - There is no `sk-ant` string in the JS bundle (CI also checks this).
   - The browser only calls the Railway domain.
   - 21 fast requests produce a `429`.
   - The production eval run is committed.

If requests suddenly fail with `api_error`, check the Anthropic spend limit before debugging the code.

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

**Structured output:** the model call uses `messages.create` with `output_config.format` (the hand-written AP §4.1 schema) instead of `messages.parse`. In the installed SDK, `parse()` validates inside the call, so a truncated or refused response would raise before `stop_reason` could be checked and the raw text would be lost. `output_config.effort = "low"` is sent alongside the format.

**Known gaps:**

- The regex guards only know English. EC-07 and EC-08 in the evals measure this.
- Two simultaneous requests on one conversation can exceed the turn cap by one (accepted for M1).
- Conversations are anonymous: anyone with the ID can read one.
