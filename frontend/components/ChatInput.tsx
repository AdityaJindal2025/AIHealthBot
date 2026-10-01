"use client";

import { useLayoutEffect, useRef, useState } from "react";

import { SendIcon } from "./Icons";

export const MAX_CHARS = 2000;

/** Counts code points, like the backend's `len()`, so an emoji counts once (EC IN-05). */
export function charCount(text: string) {
  return [...text].length;
}

type Props = {
  disabled: boolean;
  onSend: (text: string) => void;
};

export function ChatInput({ disabled, onSend }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const count = charCount(text);
  const tooLong = count > MAX_CHARS;
  const canSend = !disabled && text.trim().length > 0 && !tooLong;

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  function submit() {
    if (!canSend) return;
    onSend(text);
    setText("");
  }

  return (
    <form
      className="bg-surface-container-lowest px-4 py-4 shadow-[0_-4px_16px_-8px_rgba(28,42,34,0.08)] sm:px-5"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div
        className={`mx-auto max-w-3xl rounded-2xl bg-surface-container-low p-3.5 shadow-card focus-within:ring-2 ${
          tooLong ? "ring-2 ring-error" : "focus-within:ring-secondary-container"
        }`}
      >
        <label htmlFor="chat-input" className="sr-only">
          Ask a question about food or nutrition
        </label>
        <textarea
          id="chat-input"
          ref={ref}
          rows={2}
          value={text}
          disabled={disabled}
          placeholder="Ask about food, nutrition or food safety…"
          aria-describedby="char-count"
          aria-invalid={tooLong}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            // Enter sends, Shift+Enter adds a line; never send mid IME composition (EC FE-14).
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
          className="block w-full resize-none bg-transparent text-body-md text-on-surface placeholder:text-outline focus:outline-none disabled:opacity-60"
        />
        <div className="flex items-center justify-between gap-3 pt-2">
          <div className="flex items-center gap-3 text-label-sm text-on-surface-variant">
            <span id="char-count" className={`font-mono ${tooLong ? "font-semibold text-error" : ""}`}>
              {tooLong ? `Too long: ${count} / ${MAX_CHARS}` : `${count} / ${MAX_CHARS}`}
            </span>
            <span className="hidden sm:inline">· Shift + Enter for new line</span>
          </div>
          <button
            type="submit"
            disabled={!canSend}
            className="flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-label-lg text-on-primary shadow-card transition-colors hover:bg-primary-container focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary-container disabled:cursor-not-allowed disabled:bg-surface-container-highest disabled:text-on-surface-variant"
          >
            Send
            <SendIcon className="h-[18px] w-[18px]" />
          </button>
        </div>
      </div>
    </form>
  );
}
