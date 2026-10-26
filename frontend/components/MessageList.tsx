"use client";

import { useEffect, useRef } from "react";

import type { ChatMessage } from "@/lib/types";

import { ArrowRightIcon, ProduceIllustration } from "./Icons";
import { MessageBubble } from "./MessageBubble";

export const EXAMPLE_QUESTIONS = [
  "How long can egg salad stay in the fridge?",
  "What do the guidelines say about salt?",
  "How do I defrost meat safely?",
  "How much free sugar should adults have?",
];

type Props = {
  messages: ChatMessage[];
  sending: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCite?: (messageId: string, chunkId: string) => void;
  onExample: (question: string) => void;
};

export function MessageList({ messages, sending, selectedId, onSelect, onCite, onExample }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, sending]);

  return (
    <div className="flex flex-1 flex-col overflow-y-auto px-4 py-6 sm:px-8 sm:py-8">
      {messages.length === 0 && !sending ? (
        <div className="m-auto flex w-full max-w-xl flex-col items-center py-10 text-center">
          <div className="mb-6 flex h-24 w-24 items-center justify-center rounded-3xl border border-outline-variant bg-surface-container-low shadow-card">
            <ProduceIllustration />
          </div>
          <h2 className="mb-3 text-headline-sm text-on-surface">Ask about food, nutrition or food safety</h2>
          <p className="mb-8 max-w-md text-body-sm text-on-surface-variant">
            Answers come only from official guidance documents, with a citation for every claim.
          </p>
          <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
            {EXAMPLE_QUESTIONS.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => onExample(q)}
                className="group flex items-center justify-between rounded-xl border border-outline-variant bg-surface-container-lowest p-3.5 text-left text-label-md text-on-surface shadow-card transition-all hover:bg-surface-container-low hover:shadow-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary-container"
              >
                <span className="pr-2">{q}</span>
                <ArrowRightIcon className="h-[18px] w-[18px] text-tertiary opacity-60 transition-all group-hover:translate-x-0.5 group-hover:opacity-100" />
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div role="log" aria-live="polite" aria-label="Conversation" className="mx-auto w-full max-w-3xl space-y-7">
          {messages.map((m) => (
            <MessageBubble
              key={m.id}
              message={m}
              selected={m.id === selectedId}
              onSelect={m.role === "assistant" && m.scope?.status !== "declined" ? onSelect : undefined}
              onCite={onCite}
            />
          ))}
          {sending && (
            <div
              className="inline-flex items-center gap-3 rounded-2xl rounded-tl-sm bg-surface-container-lowest px-4 py-3 shadow-card"
              aria-label="Assistant is typing"
            >
              <span className="flex items-center gap-1.5">
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="h-2 w-2 animate-bounce rounded-full bg-primary"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </span>
              <span className="text-label-sm text-on-surface-variant">Preparing an answer…</span>
            </div>
          )}
        </div>
      )}
      <div ref={endRef} />
    </div>
  );
}
