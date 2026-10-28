"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getConversation, getThemes, sendMessage } from "./api";
import type { ChatMessage, MessageOut, ThemeOut } from "./types";

const STORAGE_KEY = "nutrition-assistant.conversation-id";
// The "Select theme" filter is remembered per conversation.
const FILTER_KEY_PREFIX = "nutrition-assistant.theme-filter.";

function readStoredId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // storage blocked: chat still works, history just isn't restored (EC FE-02)
  }
}

function writeStoredId(id: string | null) {
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}

function readStoredFilter(conversationId: string): string | null {
  try {
    return window.localStorage.getItem(FILTER_KEY_PREFIX + conversationId);
  } catch {
    return null;
  }
}

function writeStoredFilter(conversationId: string, themeId: string | null) {
  try {
    if (themeId) window.localStorage.setItem(FILTER_KEY_PREFIX + conversationId, themeId);
    else window.localStorage.removeItem(FILTER_KEY_PREFIX + conversationId);
  } catch {
    // ignore: the filter still applies for this page view
  }
}

function fromServer(m: MessageOut): ChatMessage {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    claims: m.claims ?? [],
    scope: m.scope,
    grounding: m.grounding ?? null,
    sources: m.sources ?? [],
  };
}

/** The chunk the user asked to see, from a citation chip. */
export type FocusedSource = { messageId: string; chunkId: string };

export type ChatErrorState = { error: ApiError; message: string };

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [error, setError] = useState<ChatErrorState | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focused, setFocused] = useState<FocusedSource | null>(null);
  const [themes, setThemes] = useState<ThemeOut[]>([]);
  const [themeId, setThemeIdState] = useState<string | null>(null);

  // Each "New chat" starts a new epoch; a response from an older epoch is dropped (EC FE-03).
  const epoch = useRef(0);
  const inFlight = useRef<AbortController | null>(null);
  const conversationRef = useRef<string | null>(null);
  const themeRef = useRef<string | null>(null);

  // The theme list is loaded once. If it fails (or an M1 backend has no endpoint) the filter is hidden.
  useEffect(() => {
    const controller = new AbortController();
    getThemes(controller.signal).then(
      (res) => setThemes(res.themes),
      () => {},
    );
    return () => controller.abort();
  }, []);

  const setThemeId = useCallback((id: string | null) => {
    themeRef.current = id;
    setThemeIdState(id);
    if (conversationRef.current) writeStoredFilter(conversationRef.current, id);
  }, []);

  // A stored filter for a theme that no longer exists is dropped.
  useEffect(() => {
    if (themes.length && themeRef.current && !themes.some((t) => t.theme_id === themeRef.current)) {
      setThemeId(null);
    }
  }, [themes, setThemeId]);

  useEffect(() => {
    const controller = new AbortController();

    async function restore() {
      const stored = readStoredId();
      if (stored) {
        try {
          const conv = await getConversation(stored, controller.signal);
          conversationRef.current = conv.id;
          setConversationId(conv.id);
          setMessages(conv.messages.map(fromServer));
          const filter = readStoredFilter(conv.id);
          themeRef.current = filter;
          setThemeIdState(filter);
        } catch (err) {
          // Unknown ID (DB reset, other environment): start fresh, no error loop (EC FE-01).
          if (err instanceof ApiError && err.status === 404) writeStoredId(null);
        }
      }
      if (!controller.signal.aborted) setLoadingHistory(false);
    }

    void restore();
    return () => controller.abort();
  }, []);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || inFlight.current) return;

      const myEpoch = epoch.current;
      const controller = new AbortController();
      inFlight.current = controller;
      setError(null);
      setSending(true);
      const tempId = `local-${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        { id: tempId, role: "user", content: message, claims: [], scope: null, grounding: null, sources: [] },
      ]);

      try {
        const res = await sendMessage(conversationRef.current, message, themeRef.current, controller.signal);
        if (epoch.current !== myEpoch) return;
        conversationRef.current = res.conversation_id;
        setConversationId(res.conversation_id);
        writeStoredId(res.conversation_id);
        writeStoredFilter(res.conversation_id, themeRef.current);
        setMessages((prev) => [
          ...prev,
          {
            id: res.message_id,
            role: "assistant",
            content: res.answer,
            claims: res.claims,
            scope: res.scope,
            grounding: res.grounding ?? null,
            sources: res.sources ?? [],
          },
        ]);
        setSelectedId(res.message_id);
        setFocused(null);
      } catch (err) {
        if (epoch.current !== myEpoch || controller.signal.aborted) return;
        const apiError = err instanceof ApiError ? err : new ApiError(0, "network_error");
        // A 429 or 422 means the server did not keep the message; drop it from the list.
        if (apiError.status === 429 || apiError.status === 422 || apiError.status === 0) {
          setMessages((prev) => prev.filter((m) => m.id !== tempId));
        }
        // The chosen theme was removed: fall back to all themes.
        if (apiError.error === "unknown_theme") setThemeId(null);
        setError({ error: apiError, message });
      } finally {
        if (epoch.current === myEpoch) {
          inFlight.current = null;
          setSending(false);
        }
      }
    },
    [setThemeId],
  );

  const retry = useCallback(() => {
    if (!error) return;
    const { message } = error;
    // Remove the unanswered copy from the UI. The server keeps both copies of the user
    // message after a 502; that is accepted and documented for M1 (EC FE-04).
    setMessages((prev) => {
      const last = prev[prev.length - 1];
      return last && last.role === "user" && last.content === message ? prev.slice(0, -1) : prev;
    });
    void send(message);
  }, [error, send]);

  const newChat = useCallback(() => {
    epoch.current += 1;
    inFlight.current?.abort();
    inFlight.current = null;
    conversationRef.current = null;
    writeStoredId(null);
    setConversationId(null);
    setMessages([]);
    setSelectedId(null);
    setFocused(null);
    themeRef.current = null;
    setThemeIdState(null);
    setError(null);
    setSending(false);
  }, []);

  /** A citation chip was clicked: select its message and the chunk it cites. */
  const focusSource = useCallback((messageId: string, chunkId: string) => {
    setSelectedId(messageId);
    setFocused({ messageId, chunkId });
  }, []);

  const select = useCallback((id: string) => {
    setSelectedId(id);
    setFocused(null);
  }, []);

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant") ?? null;
  const selected = messages.find((m) => m.id === selectedId && m.role === "assistant") ?? lastAssistant;

  return {
    messages,
    conversationId,
    sending,
    loadingHistory,
    error,
    selected,
    select,
    focusedChunkId: focused && selected && focused.messageId === selected.id ? focused.chunkId : null,
    focusSource,
    themes,
    themeId,
    setThemeId,
    send,
    retry,
    newChat,
    dismissError: () => setError(null),
  };
}
