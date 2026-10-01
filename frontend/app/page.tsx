"use client";

import { useEffect, useState } from "react";

import { ChatInput } from "@/components/ChatInput";
import { ErrorBanner } from "@/components/ErrorBanner";
import { BookIcon, CloseIcon, LogoMark, PlusIcon } from "@/components/Icons";
import { MessageList } from "@/components/MessageList";
import { SourcesPanel } from "@/components/SourcesPanel";
import { useChat } from "@/lib/useChat";

const focusRing = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-secondary-container";

export default function Home() {
  const chat = useChat();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const selectedClaims = chat.selected?.claims ?? [];

  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawerOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  return (
    <div className="flex h-dvh flex-col bg-surface">
      <header className="border-b border-outline-variant bg-surface-container-lowest">
        <div className="flex h-16 items-center justify-between gap-2 px-4 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <LogoMark />
            <h1 className="flex min-w-0 items-center gap-2">
              <span className="truncate text-label-lg text-on-surface sm:text-headline-sm">Nutrition Assistant</span>
              <span className="hidden rounded-full border border-outline-variant bg-surface-container-low px-2 py-0.5 text-label-sm text-on-surface-variant sm:inline">
                · prototype
              </span>
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className={`flex items-center gap-1.5 whitespace-nowrap rounded-xl border border-outline-variant bg-surface-container-lowest px-3 py-2 text-label-md text-on-surface hover:border-primary-container hover:bg-surface-container-low lg:hidden ${focusRing}`}
            >
              <BookIcon className="h-4 w-4 text-primary" />
              Sources
            </button>
            <button
              type="button"
              onClick={chat.newChat}
              className={`flex items-center gap-1 whitespace-nowrap rounded-xl bg-inverse-surface px-3 sm:px-4 py-2 text-label-md text-on-primary shadow-card transition-colors hover:bg-tertiary ${focusRing}`}
            >
              <PlusIcon className="h-4 w-4" />
              New chat
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid min-h-0 w-full max-w-[1440px] flex-1 lg:grid-cols-[65fr_35fr]">
        <section aria-label="Chat" className="flex min-h-0 flex-col">
          {chat.loadingHistory ? (
            <div className="flex flex-1 items-center justify-center text-body-sm text-on-surface-variant">
              Loading conversation…
            </div>
          ) : (
            <MessageList
              messages={chat.messages}
              sending={chat.sending}
              selectedId={chat.selected?.id ?? null}
              onSelect={chat.select}
              onExample={chat.send}
            />
          )}
          {chat.error && (
            <ErrorBanner
              error={chat.error.error}
              onRetry={chat.retry}
              onNewChat={chat.newChat}
              onDismiss={chat.dismissError}
            />
          )}
          <ChatInput disabled={chat.sending || chat.loadingHistory} onSend={chat.send} />
        </section>

        <aside className="hidden overflow-y-auto border-l border-outline-variant bg-surface-container-lowest p-8 lg:block">
          <SourcesPanel claims={selectedClaims} />
        </aside>
      </main>

      <footer className="border-t border-outline-variant bg-surface-container-low px-4 py-2 text-center text-label-sm text-on-surface-variant">
        General information only, not medical advice.
      </footer>

      {drawerOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Sources">
          <button
            type="button"
            aria-label="Close sources"
            className="absolute inset-0 bg-inverse-surface/40"
            onClick={() => setDrawerOpen(false)}
          />
          <div className="absolute inset-x-0 bottom-0 max-h-[75dvh] overflow-y-auto rounded-t-3xl bg-surface-container-lowest p-6 shadow-overlay">
            <SourcesPanel claims={selectedClaims} />
            <button
              type="button"
              autoFocus
              onClick={() => setDrawerOpen(false)}
              className={`mt-6 flex w-full items-center justify-center gap-1.5 rounded-xl border border-outline-variant py-2.5 text-label-md text-on-surface hover:bg-surface-container-low ${focusRing}`}
            >
              <CloseIcon className="h-4 w-4" />
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
