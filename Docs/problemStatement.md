# AI Nutrition Assistant: Problem Statement (Milestone 1)

> **Status (2026-10-28):** Milestone 1 is **built and measured**, and Milestone 2 ([featureProblemStatement.md](featureProblemStatement.md)) has been built on top of it. Open for Milestone 1: the public deploy (§3.6) and the human review in [failureLog.md](failureLog.md) §1–§4.
>
> This brief is kept as written, because it records what Milestone 1 asked for. Where Milestone 2 changed a requirement, a **Milestone 2 update** note says what changed and points to the new rule. The Milestone 1 behaviour can still be switched back on: `RAG_ENABLED=false` with `PROMPT_VERSION=v1` returns the exact Milestone 1 envelope, with every `source` null.

## 1. Brief

Build a prototype chatbot that answers questions about **food, nutrition, and food safety**.

In this milestone nothing supports the model, so there is no retrieval, no knowledge base and no citations. The assistant answers **only from the model's own memory**. It will make things up. Part of the job is to **write down what it makes up**.

> **Milestone 2 update:** the assistant now answers **only from 7 official guidance documents**, and every claim carries a citation (FPS §1). Model memory is no longer a source.

---

## 2. Why This Milestone Comes First

- Ask a model how much protein a vegetarian adult needs. It answers in about 2 seconds, the answer sounds specific, and **it comes from nobody**.
- Ask again tomorrow and the number has **moved**.
- Ask what a health authority recommends and it will name a recommendation **whether or not that authority ever made it**.
- Food is a bad place for this. **A wrong answer reads exactly like a right one**, and almost nobody checks.

**Goal of Milestone 1:** build the product shell, fix the response contract and put guardrails in place. Then measure and record how an ungrounded model behaves, so later milestones have a baseline to improve on.

**What the baseline showed** (run `20261027T034207Z_v1`, 55 questions × 3 repeats, [evalResults.md](evalResults.md)):

- **0 of 333** claims had a source, as designed.
- **17 of 55** questions gave different numbers across the 3 repeats, which is the "ask again tomorrow" problem measured. For example, calories in a banana came back as 90, 105, 120, 130 and 135.
- The decline guards in code fired the same way on every repeat.

The grounded run on the same questions had a source on every claim and drift on 0 of 55 ([failureLog.md](failureLog.md) §5).

---

## 3. What to Build

### 3.1 Chat Frontend

- A **message list** showing the conversation.
- An **input box** for sending messages.
- A **sources panel** next to the conversation.
  - It **stays empty** in this milestone.
  - Build it now anyway. **Milestone 2 fills it**.

> **Milestone 2 update:** the sources panel now shows the retrieved chunks behind each answer, with the cited ones marked. Citation chips in the answer link to them (FPS §4.6). Above the input, a **"Select theme"** filter limits retrieval to one of 5 themes, each a group of the 7 documents (`backend/corpus/themes.json`). The theme filter is the UI's form of the filtered-retrieval mode in FPS §4.2.

### 3.2 Backend

- A **chat endpoint** that the frontend calls.
- **Conversation storage**, so messages are saved.
- The **model call**, made **only on the server**. The browser never calls the model API directly, and API keys never reach the client.

### 3.3 Response Schema (Structured Output)

The model returns **structured output, not prose**.

| Field | Type | Notes |
|---|---|---|
| `answer` | string | The answer text shown to the user |
| `claims` | array | The factual claims made in the answer |
| `claims[].text` | string | The text of one claim |
| `claims[].source` | `null` | **Must be `null` in this milestone**, on purpose |

Example shape:

```json
{
  "answer": "Most adults need roughly ... (answer text)",
  "claims": [
    { "text": "Lentils are a good source of plant protein.", "source": null },
    { "text": "Cooking chicken to a safe internal temperature reduces risk of foodborne illness.", "source": null }
  ]
}
```

Requirements:
- The **contract is fixed now**, so Milestone 2 only has to fill in `source`.
- **Parse every response against the schema.** If a response does not parse, the request **fails**. Do not silently repair or skip it.
- Use the provider's **native structured output mode** (Anthropic or OpenAI). Do not parse free-form prose yourself.

> **Milestone 2 update:**
> - **`source` is now a real citation:** `document_id`, `document_name`, `publisher`, `year`, `url`, `section`, `page`, `chunk_id`, `label` and `excerpt`.
> - **The citation comes from the document registry, not the model.** The model returns only a label (`S1`…`S6`) naming one of the retrieved chunks. The backend checks that label against what was actually retrieved and builds the citation itself.
> - **The contract held.** `answer` and `claims[].text` did not change, and the change is documented in the README ("Schema change").

### 3.4 System Prompt

The system prompt must define:

1. **What the assistant does:** its role and domain (food, nutrition, food safety).
2. **How it answers:** tone, format, and how claims are broken out.
3. **How long its answers should be:** a length target.
4. **What it won't touch:** the out-of-scope topics (see 3.5).

**Regression discipline:**
- Keep a **fixed set of test questions**.
- **Re-run all of them after every prompt change.**
- The common failure is fixing one case while quietly breaking three others.

> **Milestone 2 update:** prompt `system_v2.md` answers only from the labelled sources. Prompt `system_v1.md` is kept for the Milestone 1 mode. The question set grew from 55 to 83 entries. It is still append-only and is re-run after every prompt change (`backend/app/llm/prompts/CHANGELOG.md`).

### 3.5 Scope Limits, Enforced in Code

The assistant must **not** provide:

- **Calorie or weight targets**
- **Recommendations about what anyone should weigh**
- **Medical advice**

For these questions it must **decline** and **point the person to a qualified professional** (for example a doctor or registered dietitian).

A line in the system prompt is not enough on its own. The scope check must **also be implemented in code** (for example a check before and/or after the model call in the backend).

> **Milestone 2 update:** the same guards still run, whatever retrieval returns. Two checks were added:
> - **The energy-requirements table is restricted.** The Eatwell Guide's table of daily kcal needs is tagged as off limits. If it is the best match for a question, the question is declined before the model is called, and it is never shown to the model.
> - **Personal framing is dropped.** A claim that turns population guidance into personal advice, such as "you should eat 30 g", is removed in code (FPS §4.3, §4.5).
>
> "Not covered" (in scope, but the documents don't say) is a separate response from "declined", and the two look different in the UI.

### 3.6 Deploy

- Push the project to **GitHub**.
- Deploy it to a **public URL** using **Vercel** and/or **Railway**.

> **Status:** the repository is on GitHub (`AdityaJindal2025/AIHealthBot`). Only the initial commit is on `main` there; the Milestone 2 branch is local. Nothing is deployed yet. The plan is Phase 9 of [implementationPlan.md](implementationPlan.md): backend and Postgres (with pgvector) on Railway, frontend on Vercel.

---

## 4. Allowed Tools and Stack

| Area | Options | Used |
|---|---|---|
| Frontend and Backend | Next.js, **or** React with FastAPI | Next.js (frontend) with FastAPI (backend) |
| Scaffolding | Cursor or Anti-gravity | — |
| Model | Anthropic API or OpenAI API | **Groq** serving `openai/gpt-oss-120b` (see below) |
| Storage | Supabase, Postgres, or SQLite | Postgres in production, SQLite locally |
| Deployment | Vercel or Railway | Vercel (frontend), Railway (backend + Postgres), planned |

**Model requirement:** both Anthropic and OpenAI offer structured output modes. **Use structured outputs** rather than parsing prose.

> **Deviation from this table:**
> - **Groq instead of the Anthropic or OpenAI API.** The model is OpenAI's open-weight `gpt-oss-120b`, served by Groq.
> - **The rule on structured output still holds.** Groq's strict `json_schema` mode returns schema-checked output, and every response is validated again with Pydantic.
> - **Cost: low free-tier limits.** The free tier allows 8,000 tokens a minute and 200,000 tokens a day for this model, about 60 grounded answers a day (eval results, 2026-10-27).
>
> **Milestone 2 additions to the stack:**
> - **Embeddings:** sentence-transformers running `BAAI/bge-small-en-v1.5` locally.
> - **Vector search:** pgvector exact search, with NumPy for SQLite.
> - **Orchestration:** plain Python, with no LangChain.

---

## 5. Rules (Non-Negotiable)

1. **Every response must parse** against the schema.
2. The schema **must include a claims list** and a **source field on each claim**.
3. **Source fields must stay `null`.** *(Milestone 1 only. Replaced in Milestone 2 by "every claim carries a citation; no citation means the claim doesn't ship" (FPS §6, Rule 2). It still holds in the Milestone 1 mode.)*
4. **Scope limits must live in code**, not only in the prompt.
5. The app **must be live at a public URL**.
6. **Failures must be recorded, not patched around.**
7. **Model calls must run behind the backend.**

---

## 6. Acceptance Checklist

- [x] Chat UI with message list, input box and an (empty) sources panel *(evidence: `frontend/app/page.tsx`, `components/MessageList.tsx`, `ChatInput.tsx`, `SourcesPanel.tsx`; the panel is empty in the M1 mode and filled in M2)*
- [x] Backend chat endpoint; the model is called only from the server *(evidence: `backend/app/api/chat.py`; `backend/app/llm/client.py` is the only module that imports `groq`; CI fails if `gsk_` appears in the frontend bundle)*
- [x] Conversations are saved (Supabase, Postgres or SQLite) *(evidence: `backend/app/db/models.py`, migration `0001`; Postgres in production, SQLite locally; `tests/test_repo.py`)*
- [x] Structured output with `answer` and `claims[{ text, source }]` *(evidence: `backend/app/schemas/model_output.py`, `json_schema.py`, Groq strict `json_schema` mode; `tests/test_schema.py`)*
- [x] Every response is validated against the schema; invalid responses fail *(evidence: strict Pydantic validation in `llm/client.py`; an invalid, refused or truncated response is a `502` plus a `failures` row, never repaired; `tests/test_llm_client.py`)*
- [x] All `source` values are `null` *(evidence: M1 run `20261027T034207Z_v1`: 0 of 333 claims had a source. In Milestone 2 this is deliberately reversed; see Rule 3)*
- [x] System prompt covers role, answer style, answer length and exclusions *(evidence: `backend/app/llm/prompts/system_v1.md`, `CHANGELOG.md`)*
- [x] A fixed regression question set exists and is re-run after every prompt change *(evidence: `evals/questions.yaml` (append-only, 83 entries), `evals/run_evals.py`, runs in `evals/runs/`)*
- [x] Code-level scope check for calorie or weight targets, ideal-weight questions and medical advice, with a referral to a professional *(evidence: `backend/app/guards/` input and output guards with rule IDs; `tests/test_guards.py` over `guard_cases.yaml`; identical declines across all repeats of the M1 run)*
- [ ] Failures (schema failures, hallucinations, scope leaks) are logged, not hidden *(built: `failures`, `scope_events` and `citation_events` tables, the eval runs and the M1-vs-M2 comparison in [failureLog.md](failureLog.md) §5. **Open:** the human review of the M1 claims in failureLog §1–§4)*
- [ ] Code is on GitHub *(the initial commit is on `origin/main`. **Open:** push the Milestone 2 branch and merge it)*
- [ ] Deployed and reachable at a public URL (Vercel or Railway) *(**open:** [implementationPlan.md](implementationPlan.md) Phase 9)*

---

## 7. Roadmap

| Milestone | Focus | Status |
|---|---|---|
| **1 (this brief)** | Ungrounded chatbot. Fixed schema, `source: null`, scope guardrails, deployed. Record what the model makes up. | Built and measured (baseline `20261027T034207Z_v1`). Open: deploy, failure-log review. |
| **2** ([featureProblemStatement.md](featureProblemStatement.md)) | Fill in the `source` field and the sources panel. The schema contract from Milestone 1 stays the same. | Built: retrieval over 7 verified documents, real citations on every claim, a populated sources panel, per-document answers, two kinds of refusal, and a theme filter. Grounded runs on 2026-10-27 met T8–T12. Open: deploy and the human citation review. |
