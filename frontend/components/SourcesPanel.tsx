"use client";

import { useEffect, useRef } from "react";

import { labelNumber, type ChatMessage, type RetrievedSource } from "@/lib/types";

import { BookIcon, SearchIcon } from "./Icons";

// Milestone 1 path (no retrieval): answers have no sources.
export const EMPTY_SOURCES_TEXT =
  "No sources yet. Answers are currently generated from the model's memory and are not verified.";
export const NO_MESSAGE_TEXT = "Ask a question to see the guidance behind each answer.";
export const DECLINED_SOURCES_TEXT = "No sources: this question is outside what the assistant answers.";
export const NOT_COVERED_SOURCES_TEXT = "Nothing relevant was found in the documents that were searched.";

const focusRing = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary-container";

export function sourceElementId(chunkId: string): string {
  return `source-${chunkId.replace(/[^A-Za-z0-9_-]/g, "-")}`;
}

type Props = {
  /** The selected assistant message, or null before the first answer. */
  message: ChatMessage | null;
  /** A chunk to highlight and scroll to, from a citation chip. */
  focusChunkId?: string | null;
};

/** Shows the retrieved chunks behind the selected answer: cited first, the rest collapsed (FAP §12). */
export function SourcesPanel({ message, focusChunkId = null }: Props) {
  const sources = message?.sources ?? [];
  const cited = sources.filter((s) => s.cited);
  const uncited = sources.filter((s) => !s.cited);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!focusChunkId) return;
    const el = listRef.current?.querySelector<HTMLElement>(`#${sourceElementId(focusChunkId)}`);
    el?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
    el?.focus({ preventScroll: true });
  }, [focusChunkId, message?.id]);

  let empty: { title: string; text: string } | null = null;
  if (!message) empty = { title: "No answer yet", text: NO_MESSAGE_TEXT };
  else if (message.scope?.status === "declined") empty = { title: "Outside scope", text: DECLINED_SOURCES_TEXT };
  else if (sources.length === 0 && message.grounding?.status === "not_covered")
    empty = { title: "Not covered", text: NOT_COVERED_SOURCES_TEXT };
  else if (sources.length === 0) empty = { title: "Awaiting verification", text: EMPTY_SOURCES_TEXT };

  return (
    <section aria-labelledby="sources-heading" className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <BookIcon className="h-5 w-5 text-primary" />
          <h2 id="sources-heading" className="text-label-md font-bold tracking-widest text-on-surface-variant uppercase">
            Sources
          </h2>
        </div>
        <span className="rounded-full bg-surface-container px-2.5 py-1 text-label-sm text-on-surface-variant">
          {cited.length} cited
        </span>
      </div>

      {empty ? (
        <div className="flex flex-col items-center rounded-2xl bg-surface-container-low p-7 text-center shadow-inner">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-container-highest text-tertiary">
            <SearchIcon className="h-7 w-7" />
          </div>
          <h3 className="mb-2 text-headline-sm text-on-surface">{empty.title}</h3>
          <p className="max-w-xs text-body-sm text-on-surface-variant">{empty.text}</p>
        </div>
      ) : (
        <div ref={listRef} className="flex flex-col gap-5">
          {cited.length > 0 && (
            <div>
              <h3 className="mb-3 text-label-sm font-bold tracking-wider text-on-surface-variant uppercase">
                Cited in this answer
              </h3>
              <ul className="space-y-3" data-testid="cited-sources">
                {cited.map((s) => (
                  <SourceCard
                    key={s.chunk_id}
                    source={s}
                    claims={message!.claims.filter((c) => c.source?.chunk_id === s.chunk_id).map((c) => c.text)}
                    focused={s.chunk_id === focusChunkId}
                  />
                ))}
              </ul>
            </div>
          )}
          {uncited.length > 0 && (
            <details
              className="group rounded-xl bg-surface-container-low p-3"
              data-testid="also-retrieved"
              // Open when the panel has nothing cited (a not-covered answer), or a chip points inside it.
              open={cited.length === 0 || uncited.some((s) => s.chunk_id === focusChunkId)}
            >
              <summary
                className={`cursor-pointer rounded-lg px-1 py-1 text-label-md text-on-surface-variant ${focusRing}`}
              >
                Also retrieved ({uncited.length})
              </summary>
              <ul className="mt-3 space-y-3">
                {uncited.map((s) => (
                  <SourceCard key={s.chunk_id} source={s} claims={[]} focused={s.chunk_id === focusChunkId} />
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </section>
  );
}

function SourceCard({ source, claims, focused }: { source: RetrievedSource; claims: string[]; focused: boolean }) {
  const n = labelNumber(source.label);
  const year = source.year != null ? `, ${source.year}` : "";
  return (
    <li
      id={sourceElementId(source.chunk_id)}
      tabIndex={-1}
      data-focused={focused || undefined}
      className={`rounded-xl border bg-surface-container-lowest p-4 text-body-sm text-on-surface shadow-card outline-none ${
        focused ? "border-primary-container ring-2 ring-primary-container" : "border-outline-variant"
      }`}
    >
      <div className="flex items-start gap-2.5">
        <span className="flex-none rounded-md bg-surface-container px-1.5 py-0.5 text-label-sm font-bold text-primary">
          {n != null ? `[${n}]` : source.label}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-label-lg text-on-surface [overflow-wrap:anywhere]">{source.document_name}</p>
          <p className="text-label-sm text-on-surface-variant [overflow-wrap:anywhere]">
            {source.publisher}
            {year} · {source.section}
            {source.page != null ? ` · p. ${source.page}` : ""}
          </p>
        </div>
      </div>
      {/* Plain text, never HTML (EC FE-10). Long chunks scroll inside the card. */}
      <p className="mt-3 max-h-48 overflow-y-auto whitespace-pre-wrap rounded-lg bg-surface-container-low p-3 text-body-sm text-on-surface-variant [overflow-wrap:anywhere]">
        {source.text}
      </p>
      {claims.length > 0 && (
        <div className="mt-3">
          <p className="text-label-sm font-bold tracking-wider text-on-surface-variant uppercase">Supports</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {claims.map((text, i) => (
              <li key={i} className="[overflow-wrap:anywhere]">
                {text}
              </li>
            ))}
          </ul>
        </div>
      )}
      {source.url && (
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className={`mt-3 inline-block rounded text-label-md text-primary underline underline-offset-4 hover:text-on-primary-fixed-variant ${focusRing}`}
        >
          Open document ↗<span className="sr-only"> (opens in a new tab)</span>
        </a>
      )}
    </li>
  );
}
