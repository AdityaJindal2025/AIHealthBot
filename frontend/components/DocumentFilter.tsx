"use client";

import { useId } from "react";

import type { DocumentOut } from "@/lib/types";

type Props = {
  documents: DocumentOut[];
  value: string | null;
  onChange: (documentId: string | null) => void;
  disabled?: boolean;
};

const MAX_OPTION_CHARS = 60;

function optionLabel(d: DocumentOut): string {
  const title = d.title.length > MAX_OPTION_CHARS ? `${d.title.slice(0, MAX_OPTION_CHARS - 1).trimEnd()}…` : d.title;
  return `${title} (${d.publisher_short})`;
}

/** "Search in: All documents ▾": restricts retrieval to one registry document (FAP §7.2, §12). */
export function DocumentFilter({ documents, value, onChange, disabled = false }: Props) {
  const id = useId();
  // Hidden when the list could not be loaded (or the backend runs without retrieval).
  if (documents.length === 0) return null;

  return (
    <div className="mx-auto flex w-full max-w-3xl items-center gap-2 px-4 pt-3 sm:px-8">
      <label htmlFor={id} className="flex-none text-label-md text-on-surface-variant">
        Search in:
      </label>
      <select
        id={id}
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value || null)}
        className="min-w-0 max-w-full flex-1 truncate rounded-lg border border-outline-variant bg-surface-container-lowest px-2.5 py-1.5 text-label-md text-on-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary-container disabled:opacity-60 sm:flex-none"
      >
        <option value="">All documents</option>
        {documents.map((d) => (
          <option key={d.document_id} value={d.document_id} title={d.title}>
            {optionLabel(d)}
          </option>
        ))}
      </select>
    </div>
  );
}
