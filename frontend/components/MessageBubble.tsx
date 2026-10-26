"use client";

import { useEffect, useId, useState } from "react";

import { citationText, type ChatMessage, type Source } from "@/lib/types";

import {
  ArrowRightIcon,
  BookIcon,
  CheckIcon,
  ChevronIcon,
  CopyIcon,
  FactCheckIcon,
  InfoIcon,
  LeafIcon,
  SearchIcon,
  VerifiedIcon,
} from "./Icons";

const focusRing = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary-container";

type Props = {
  message: ChatMessage;
  selected?: boolean;
  onSelect?: (id: string) => void;
  /** A citation chip was clicked: show that chunk in the sources panel. */
  onCite?: (messageId: string, chunkId: string) => void;
};

/** "[3] WHO, 2020". Clicking it highlights the cited chunk in the sources panel (FAP §12). */
export function CitationChip({ source, onClick }: { source: Source; onClick?: () => void }) {
  const text = citationText(source);
  const className =
    "inline-flex flex-none items-center gap-1.5 rounded-full border border-primary-container/40 bg-surface-container px-2.5 py-1 text-label-sm text-on-primary-fixed-variant";
  if (!onClick) {
    return (
      <span className={className} title={`${source.document_name} — ${source.section}`}>
        <BookIcon className="h-3.5 w-3.5" />
        {text}
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Source ${text}: ${source.document_name}. Show in sources panel`}
      title={`${source.document_name} — ${source.section}`}
      className={`${className} transition-colors hover:bg-surface-container-high ${focusRing}`}
    >
      <BookIcon className="h-3.5 w-3.5" />
      {text}
    </button>
  );
}

/** Distinct cited sources, in the order the claims first cite them. */
function citedSources(message: ChatMessage): Source[] {
  const seen = new Map<string, Source>();
  for (const claim of message.claims) {
    if (claim.source && !seen.has(claim.source.chunk_id)) seen.set(claim.source.chunk_id, claim.source);
  }
  return [...seen.values()];
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(t);
  }, [copied]);

  return (
    <button
      type="button"
      aria-label={copied ? "Copied" : "Copy answer"}
      title={copied ? "Copied" : "Copy answer"}
      onClick={() => {
        navigator.clipboard?.writeText(text).then(
          () => setCopied(true),
          () => {}, // clipboard blocked: nothing useful to show
        );
      }}
      className={`rounded-lg p-2 text-on-surface-variant transition-colors hover:bg-surface-container hover:text-on-surface ${focusRing}`}
    >
      {copied ? <CheckIcon className="h-[18px] w-[18px] text-primary" /> : <CopyIcon className="h-[18px] w-[18px]" />}
    </button>
  );
}

export function MessageBubble({ message, selected = false, onSelect, onCite }: Props) {
  const [open, setOpen] = useState(false);
  const claimsId = useId();

  // Plain text only, never HTML (EC FE-10). Long words wrap (EC FE-11).
  const textClass = "whitespace-pre-wrap [overflow-wrap:anywhere]";

  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div
          className={`max-w-[85%] rounded-2xl rounded-tr-sm bg-primary-container px-5 py-3.5 text-body-md text-on-primary shadow-card sm:max-w-[78%] ${textClass}`}
        >
          {message.content}
        </div>
      </div>
    );
  }

  const declined = message.scope?.status === "declined";

  if (declined) {
    return (
      <div className="flex justify-start" data-testid="declined-message">
        <div
          role="note"
          className="flex w-full max-w-[94%] items-start gap-3.5 rounded-2xl border border-notice-border bg-notice p-5 text-on-notice shadow-card"
        >
          <span className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-notice-icon">
            <InfoIcon className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="pb-1 text-label-lg">
              Nutrition Assistant <span className="text-label-sm opacity-80">· Scope notice</span>
            </p>
            <p className={`text-body-md ${textClass}`}>{message.content}</p>
          </div>
        </div>
      </div>
    );
  }

  // "We don't have guidance on that" looks different from "We won't answer that" (FPS §4.5).
  if (message.grounding?.status === "not_covered") {
    const { searched, filter_document_id: filtered } = message.grounding;
    return (
      <div className="flex justify-start" data-testid="not-covered-message">
        <div
          role="note"
          className="flex w-full max-w-[94%] items-start gap-3.5 rounded-2xl border border-uncovered-border bg-uncovered p-5 text-on-uncovered shadow-card"
        >
          <span className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-uncovered-icon">
            <SearchIcon className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="pb-1 text-label-lg">
              Nutrition Assistant <span className="text-label-sm opacity-80">· Not covered</span>
            </p>
            <p className={`text-body-md ${textClass}`}>{message.content}</p>
            {searched.length > 0 && (
              <div className="mt-3">
                <p className="text-label-sm font-bold tracking-wider uppercase opacity-80">
                  {filtered ? "Searched (as you asked)" : `Searched ${searched.length} documents`}
                </p>
                <ul className="mt-1.5 space-y-1 text-body-sm">
                  {searched.map((d) => (
                    <li key={d.document_id} className="[overflow-wrap:anywhere]">
                      <span className="italic">{d.document_name}</span> — {d.publisher}
                      {d.year != null ? `, ${d.year}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {onSelect && message.sources.length > 0 && (
              <button
                type="button"
                aria-pressed={selected}
                onClick={() => onSelect(message.id)}
                className={`mt-3 rounded-lg px-1.5 py-1 text-label-md underline underline-offset-4 ${focusRing}`}
              >
                {selected ? "Showing what was retrieved" : "View what was retrieved"}
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const count = message.claims.length;
  const cited = citedSources(message);
  const cite = (source: Source) => (onCite ? () => onCite(message.id, source.chunk_id) : undefined);

  return (
    <div className="flex flex-col items-start gap-3">
      <div
        className={`w-full max-w-[94%] rounded-2xl rounded-tl-sm border bg-surface-container-lowest p-5 shadow-card transition-shadow sm:p-6 ${
          selected ? "border-primary-container ring-1 ring-primary-container" : "border-transparent"
        }`}
      >
        <div className="flex items-center gap-2.5 pb-4">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-container text-primary">
            <LeafIcon className="h-5 w-5" />
          </span>
          <p className="text-label-lg text-on-surface">Nutrition Assistant</p>
        </div>

        <p className={`text-body-md text-on-surface ${textClass}`}>{message.content}</p>

        {cited.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2" aria-label="Cited sources">
            {cited.map((source) => (
              <CitationChip key={source.chunk_id} source={source} onClick={cite(source)} />
            ))}
          </div>
        )}

        <div className="mt-5 flex items-start justify-between gap-3 border-t border-surface-container pt-4">
          <div className="flex flex-wrap items-center gap-2">
            {count > 0 && ( // no empty "Claims (0)" section (EC FE-09)
              <button
                type="button"
                aria-expanded={open}
                aria-controls={claimsId}
                onClick={() => setOpen((v) => !v)}
                className={`flex items-center gap-1.5 rounded-lg bg-surface-container-low px-2 py-1 text-label-md text-primary transition-colors hover:bg-surface-container hover:text-on-primary-fixed-variant ${focusRing}`}
              >
                <VerifiedIcon className="h-[18px] w-[18px]" />
                Extracted claims ({count})
                <ChevronIcon up={open} />
              </button>
            )}
            {onSelect && (
              <button
                type="button"
                aria-pressed={selected}
                onClick={() => onSelect(message.id)}
                className={`flex items-center gap-1 rounded-lg px-1.5 py-1 text-label-md text-on-surface-variant underline underline-offset-4 hover:text-on-surface ${focusRing}`}
              >
                {selected ? "Showing sources" : "View sources"}
                {!selected && <ArrowRightIcon className="h-4 w-4" />}
              </button>
            )}
          </div>
          <CopyButton text={message.content} />
        </div>
      </div>

      {count > 0 && open && (
        <div id={claimsId} className="w-full max-w-[94%] space-y-3.5 rounded-xl bg-surface-container-low p-5 shadow-card">
          <div className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1.5 text-label-sm font-bold tracking-wider text-on-surface-variant uppercase">
              <FactCheckIcon className="h-4 w-4 text-tertiary" />
              Claims in this answer
            </span>
            <span className="text-label-sm text-on-surface-variant">
              {count} {count === 1 ? "statement" : "statements"}
            </span>
          </div>
          <ul className="space-y-3">
            {message.claims.map((claim, i) => (
              <li
                key={i}
                className="flex flex-col justify-between gap-3 rounded-lg bg-surface-container-lowest p-3.5 shadow-card md:flex-row md:items-center"
              >
                <span className={`text-body-sm text-on-surface ${textClass}`}>{claim.text}</span>
                {claim.source ? (
                  <span className="self-start md:self-auto">
                    <CitationChip source={claim.source} onClick={cite(claim.source)} />
                  </span>
                ) : (
                  // Only on the Milestone 1 path: an answer without retrieval has no citations.
                  <span className="inline-flex flex-none items-center gap-1.5 self-start rounded-full bg-surface-container px-2.5 py-1 text-label-sm text-on-surface-variant md:self-auto">
                    <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-secondary" />
                    <span>Unverified</span>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
