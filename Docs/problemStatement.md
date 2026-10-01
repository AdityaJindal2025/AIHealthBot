# AI Nutrition Assistant: Problem Statement (Milestone 1)

## 1. Brief

Build a prototype chatbot that answers questions about **food, nutrition, and food safety**.

In this milestone nothing supports the model, so there is no retrieval, no knowledge base and no citations. The assistant answers **only from the model's own memory**. It will make things up. Part of the job is to **write down what it makes up**.

---

## 2. Why This Milestone Comes First

- Ask a model how much protein a vegetarian adult needs. It answers in about 2 seconds, the answer sounds specific, and **it comes from nobody**.
- Ask again tomorrow and the number has **moved**.
- Ask what a health authority recommends and it will name a recommendation **whether or not that authority ever made it**.
- Food is a bad place for this. **A wrong answer reads exactly like a right one**, and almost nobody checks.

**Goal of Milestone 1:** build the product shell, fix the response contract and put guardrails in place. Then measure and record how an ungrounded model behaves, so later milestones have a baseline to improve on.

---

## 3. What to Build

### 3.1 Chat Frontend

- A **message list** showing the conversation.
- An **input box** for sending messages.
- A **sources panel** next to the conversation.
  - It **stays empty** in this milestone.
  - Build it now anyway. **Milestone 2 fills it**.

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

### 3.5 Scope Limits, Enforced in Code

The assistant must **not** provide:

- **Calorie or weight targets**
- **Recommendations about what anyone should weigh**
- **Medical advice**

For these questions it must **decline** and **point the person to a qualified professional** (for example a doctor or registered dietitian).

A line in the system prompt is not enough on its own. The scope check must **also be implemented in code** (for example a check before and/or after the model call in the backend).

### 3.6 Deploy

- Push the project to **GitHub**.
- Deploy it to a **public URL** using **Vercel** and/or **Railway**.

---

## 4. Allowed Tools and Stack

| Area | Options |
|---|---|
| Frontend and Backend | Next.js, **or** React with FastAPI |
| Scaffolding | Cursor or Anti-gravity |
| Model | Anthropic API or OpenAI API |
| Storage | Supabase, Postgres, or SQLite |
| Deployment | Vercel or Railway |

**Model requirement:** both Anthropic and OpenAI offer structured output modes. **Use structured outputs** rather than parsing prose.

---

## 5. Rules (Non-Negotiable)

1. **Every response must parse** against the schema.
2. The schema **must include a claims list** and a **source field on each claim**.
3. **Source fields must stay `null`.**
4. **Scope limits must live in code**, not only in the prompt.
5. The app **must be live at a public URL**.
6. **Failures must be recorded, not patched around.**
7. **Model calls must run behind the backend.**

---

## 6. Acceptance Checklist

- [ ] Chat UI with message list, input box and an (empty) sources panel
- [ ] Backend chat endpoint; the model is called only from the server
- [ ] Conversations are saved (Supabase, Postgres or SQLite)
- [ ] Structured output with `answer` and `claims[{ text, source }]`
- [ ] Every response is validated against the schema; invalid responses fail
- [ ] All `source` values are `null`
- [ ] System prompt covers role, answer style, answer length and exclusions
- [ ] A fixed regression question set exists and is re-run after every prompt change
- [ ] Code-level scope check for calorie or weight targets, ideal-weight questions and medical advice, with a referral to a professional
- [ ] Failures (schema failures, hallucinations, scope leaks) are logged, not hidden
- [ ] Code is on GitHub
- [ ] Deployed and reachable at a public URL (Vercel or Railway)

---

## 7. Roadmap

| Milestone | Focus |
|---|---|
| **1 (this brief)** | Ungrounded chatbot. Fixed schema, `source: null`, scope guardrails, deployed. Record what the model makes up. |
| **2** | Fill in the `source` field and the sources panel. The schema contract from Milestone 1 stays the same. |
