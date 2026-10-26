import type { ChatResponse, ConversationOut, DocumentsOut } from "./types";

// Inlined at build time: changing it on Vercel needs a redeploy (EC OPS-05).
const BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

// The backend can take 60 s plus SDK retries; give up a little after that (EC FE-06).
const REQUEST_TIMEOUT_MS = 90_000;

export class ApiError extends Error {
  /** HTTP status, or 0 when the backend could not be reached or the request timed out. */
  readonly status: number;
  readonly error: string;
  readonly failureId: string | null;
  readonly detail: string | null;

  constructor(status: number, error: string, failureId: string | null = null, detail: string | null = null) {
    super(`${status} ${error}`);
    this.name = "ApiError";
    this.status = status;
    this.error = error;
    this.failureId = failureId;
    this.detail = detail;
  }
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

/** Parse any error body without throwing: ours, FastAPI's `{detail}`, or not JSON at all (EC FE-07). */
async function toApiError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // not JSON
  }
  const obj = (body && typeof body === "object" ? body : {}) as Record<string, unknown>;
  const detail = asString(obj.detail) ?? (Array.isArray(obj.detail) ? "invalid request" : null);
  return new ApiError(res.status, asString(obj.error) ?? `http_${res.status}`, asString(obj.failure_id), detail);
}

async function request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
      signal: combined,
    });
  } catch (err) {
    if (signal?.aborted) throw err; // cancelled by the caller: not an error to show
    if (timeout.aborted) throw new ApiError(0, "timeout");
    throw new ApiError(0, "network_error"); // offline, backend down, or blocked by CORS (EC FE-05)
  }
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

export function sendMessage(
  conversationId: string | null,
  message: string,
  documentId: string | null = null,
  signal?: AbortSignal,
) {
  // Optional fields are left out rather than sent as null, so an M1 backend (extra="forbid") still accepts it.
  const body: Record<string, string> = { message };
  if (conversationId) body.conversation_id = conversationId;
  if (documentId) body.document_id = documentId;
  return request<ChatResponse>("/api/chat", { method: "POST", body: JSON.stringify(body) }, signal);
}

export function getDocuments(signal?: AbortSignal) {
  return request<DocumentsOut>("/api/documents", {}, signal);
}

export function getConversation(id: string, signal?: AbortSignal) {
  return request<ConversationOut>(`/api/conversations/${encodeURIComponent(id)}`, {}, signal);
}

export function getHealth() {
  return request<{ status: string; db: string }>("/api/health");
}
