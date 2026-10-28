"use client";

import { useId } from "react";

import type { ThemeOut } from "@/lib/types";

type Props = {
  themes: ThemeOut[];
  value: string | null;
  onChange: (themeId: string | null) => void;
  disabled?: boolean;
};

/** "Select theme: All themes ▾": restricts retrieval to one theme's documents (`corpus/themes.json`). */
export function ThemeFilter({ themes, value, onChange, disabled = false }: Props) {
  const id = useId();
  // Hidden when the list could not be loaded (or the backend runs without retrieval).
  if (themes.length === 0) return null;

  return (
    <div className="mx-auto flex w-full max-w-3xl items-center gap-2 px-4 pt-3 sm:px-8">
      <label htmlFor={id} className="flex-none text-label-md text-on-surface-variant">
        Select theme:
      </label>
      <select
        id={id}
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value || null)}
        className="min-w-0 max-w-full flex-1 truncate rounded-lg border border-outline-variant bg-surface-container-lowest px-2.5 py-1.5 text-label-md text-on-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary-container disabled:opacity-60 sm:flex-none"
      >
        <option value="">All themes</option>
        {themes.map((t) => (
          <option key={t.theme_id} value={t.theme_id} title={t.description}>
            {t.name}
          </option>
        ))}
      </select>
    </div>
  );
}
