// Hand-written mirror of backend/app/schemas (AP §4.3, FAP §11). Keep in sync with api.py and model_output.py.

/** A real citation, built by the backend from the document registry and the retrieved chunk. */
export type Source = {
  document_id: string;
  document_name: string;
  publisher: string;
  publisher_short: string;
  // Null only with an unverified development registry.
  year: number | null;
  url: string | null;
  section: string;
  page: number | null;
  chunk_id: string;
  /** "S3": matches the retrieved chunk in `sources`; the citation marker is [3]. */
  label: string;
  excerpt: string;
};

export type Claim = {
  text: string;
  // Null on the Milestone 1 path (no retrieval); grounded claims always carry a Source.
  source: Source | null;
};

export type ScopeCategory = "calorie_target" | "weight_target" | "medical_advice";

export type ScopeInfo = {
  status: "in_scope" | "declined";
  category: ScopeCategory | null;
  stage: "input" | "output" | "model" | "retrieval" | null;
};

export type Meta = {
  prompt_version: string;
  model: string | null;
  latency_ms: number | null;
  claims_dropped?: number | null;
  corpus_version?: string | null;
};

export type SearchedDocument = {
  document_id: string;
  document_name: string;
  publisher: string;
  year: number | null;
  url: string | null;
};

export type Grounding = {
  status: "grounded" | "not_covered";
  filter_document_id: string | null;
  searched: SearchedDocument[];
  top_score: number | null;
};

/** One retrieved chunk behind an answer, as the sources panel shows it. */
export type RetrievedSource = {
  label: string;
  chunk_id: string;
  document_id: string;
  document_name: string;
  publisher: string;
  publisher_short: string;
  year: number | null;
  url: string | null;
  section: string;
  page: number | null;
  text: string;
  score: number;
  cited: boolean;
};

export type ChatResponse = {
  conversation_id: string;
  message_id: string;
  answer: string;
  claims: Claim[];
  scope: ScopeInfo;
  meta: Meta;
  // Milestone 2, optional: absent when the backend runs without retrieval.
  grounding?: Grounding | null;
  sources?: RetrievedSource[];
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
  grounding?: Grounding | null;
  sources?: RetrievedSource[];
  created_at: string;
};

export type ConversationOut = {
  id: string;
  messages: MessageOut[];
};

export type DocumentOut = {
  document_id: string;
  title: string;
  publisher: string;
  publisher_short: string;
  year: number | null;
  url: string | null;
  chunk_count: number;
};

export type DocumentsOut = {
  documents: DocumentOut[];
};

/** A message as the UI holds it. */
export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  claims: Claim[];
  scope: ScopeInfo | null;
  grounding: Grounding | null;
  sources: RetrievedSource[];
};

/** "S3" → 3, the number shown in citation markers and chips. */
export function labelNumber(label: string): number | null {
  const match = /^S(\d+)$/.exec(label);
  return match ? Number(match[1]) : null;
}

/** "[3] WHO, 2020": the citation chip text (FAP §12). */
export function citationText(source: Pick<Source, "label" | "publisher_short" | "year">): string {
  const n = labelNumber(source.label);
  const year = source.year != null ? `, ${source.year}` : "";
  return `${n != null ? `[${n}] ` : ""}${source.publisher_short}${year}`;
}
