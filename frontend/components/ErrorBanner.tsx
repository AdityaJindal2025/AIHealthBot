import type { ApiError } from "@/lib/api";

export function errorText(error: ApiError): string {
  if (error.status === 502) {
    return `The assistant returned an invalid response (ref: ${error.failureId ?? "not recorded"})`;
  }
  if (error.status === 429) return "Too many requests, please wait a moment.";
  if (error.status === 0) {
    return error.error === "timeout"
      ? "The assistant took too long to respond."
      : "Can't reach the assistant. Check your connection and try again.";
  }
  if (error.error === "conversation_turn_limit") {
    return error.detail ?? "This conversation is full. Start a new chat to continue.";
  }
  if (error.error === "index_not_ready") return "The assistant is starting up, please try again in a minute.";
  if (error.error === "unknown_document") {
    return "That document is no longer available, so the filter was reset to all documents. Please try again.";
  }
  if (error.status === 503) return "The service is temporarily unavailable.";
  return `Something went wrong (${error.error}).`;
}

type Props = {
  error: ApiError;
  onRetry: () => void;
  onNewChat: () => void;
  onDismiss: () => void;
};

export function ErrorBanner({ error, onRetry, onNewChat, onDismiss }: Props) {
  const turnLimit = error.error === "conversation_turn_limit";
  const btn =
    "rounded-lg px-3 py-1.5 text-label-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary-container";

  return (
    <div
      role="alert"
      className="mx-4 mb-3 rounded-xl border border-error/30 bg-error-container px-4 py-3 text-body-sm text-on-error-container shadow-card sm:mx-8"
    >
      <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-3">
        <p className="flex-1 [overflow-wrap:anywhere]">{errorText(error)}</p>
        {turnLimit ? (
          <button type="button" onClick={onNewChat} className={`${btn} bg-error text-white hover:bg-on-error-container`}>
            New chat
          </button>
        ) : (
          <button type="button" onClick={onRetry} className={`${btn} bg-error text-white hover:bg-on-error-container`}>
            Retry
          </button>
        )}
        <button type="button" onClick={onDismiss} className={`${btn} hover:bg-white/60`}>
          Dismiss
        </button>
      </div>
    </div>
  );
}
