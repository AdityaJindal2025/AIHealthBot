// Hand-written mirror of backend/app/schemas (AP §4.3). Keep in sync with api.py and model_output.py.

export type Claim = {
  text: string;
  // Always null in Milestone 1. Milestone 2 widens this to `Source | null`.
  source: null;
};

export type ScopeCategory = "calorie_target" | "weight_target" | "medical_advice";

export type ScopeInfo = {
  status: "in_scope" | "declined";
  category: ScopeCategory | null;
  stage: "input" | "output" | "model" | null;
};

export type Meta = {
  prompt_version: string;
  model: string | null;
  latency_ms: number | null;
};

export type ChatResponse = {
  conversation_id: string;
  message_id: string;
  answer: string;
  claims: Claim[];
  scope: ScopeInfo;
  meta: Meta;
};

export type ErrorResponse = {
  error: string;
  failure_id: string | null;
  detail: string | null;
};

export type MessageOut = {
  id: string;
  role: "user" | "assistant";
  content: string;
  claims: Claim[] | null;
  scope: ScopeInfo | null;
  meta: Meta | null;
  created_at: string;
};

export type ConversationOut = {
  id: string;
  messages: MessageOut[];
};

/** A message as the UI holds it. */
export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  claims: Claim[];
  scope: ScopeInfo | null;
};
