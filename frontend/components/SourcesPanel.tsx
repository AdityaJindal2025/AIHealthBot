import type { Claim } from "@/lib/types";

import { BookIcon, SearchIcon } from "./Icons";

export const EMPTY_SOURCES_TEXT =
  "No sources yet. Answers are currently generated from the model's memory and are not verified.";

/** Renders the claims that have a source. Always empty in M1; M2 needs no change here (AP §10). */
export function SourcesPanel({ claims }: { claims: Claim[] }) {
  const sourced = claims.filter((c) => c.source !== null);
  const n = sourced.length;

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
          {n} {n === 1 ? "citation" : "citations"}
        </span>
      </div>

      {n === 0 ? (
        <div className="flex flex-col items-center rounded-2xl bg-surface-container-low p-7 text-center shadow-inner">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-surface-container-highest text-tertiary">
            <SearchIcon className="h-7 w-7" />
          </div>
          <h3 className="mb-2 text-headline-sm text-on-surface">Awaiting verification</h3>
          <p className="max-w-xs text-body-sm text-on-surface-variant">{EMPTY_SOURCES_TEXT}</p>
        </div>
      ) : (
        <ul className="space-y-3">
          {sourced.map((c, i) => (
            <li
              key={i}
              className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4 text-body-sm text-on-surface shadow-card"
            >
              {c.text}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
