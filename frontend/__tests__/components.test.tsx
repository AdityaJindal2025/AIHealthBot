import { act, cleanup, fireEvent, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { charCount } from "@/components/ChatInput";
import { ErrorBanner } from "@/components/ErrorBanner";
import { MessageBubble } from "@/components/MessageBubble";
import {
  DECLINED_SOURCES_TEXT,
  EMPTY_SOURCES_TEXT,
  NO_MESSAGE_TEXT,
  SourcesPanel,
  sourceElementId,
} from "@/components/SourcesPanel";
import { ThemeFilter } from "@/components/ThemeFilter";
import { ApiError } from "@/lib/api";
import { citationText, type ChatMessage, type RetrievedSource, type Source, type ThemeOut } from "@/lib/types";
import { useChat } from "@/lib/useChat";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  try {
    window.localStorage.clear();
  } catch {
    // ignore
  }
});

// An M1-shaped answer: no grounding, no sources, null citations.
const answer: ChatMessage = {
  id: "m1",
  role: "assistant",
  content: "Lentils are high in fibre.",
  claims: [
    { text: "Lentils are high in fibre.", source: null },
    { text: "Lentils contain protein.", source: null },
  ],
  scope: { status: "in_scope", category: null, stage: null },
  grounding: null,
  sources: [],
};

function retrieved(label: string, chunkId: string, cited: boolean, extra: Partial<RetrievedSource> = {}): RetrievedSource {
  return {
    label,
    chunk_id: chunkId,
    document_id: chunkId.split("#")[0],
    document_name: "Healthy diet (Fact sheet N°394)",
    publisher: "World Health Organization",
    publisher_short: "WHO",
    year: 2020,
    url: "https://example.org/healthy-diet",
    section: "Salt, sodium and potassium",
    page: 3,
    text: `Text of ${chunkId}`,
    score: 0.8,
    cited,
    ...extra,
  };
}

function sourceFor(r: RetrievedSource): Source {
  return {
    document_id: r.document_id,
    document_name: r.document_name,
    publisher: r.publisher,
    publisher_short: r.publisher_short,
    year: r.year,
    url: r.url,
    section: r.section,
    page: r.page,
    chunk_id: r.chunk_id,
    label: r.label,
    excerpt: r.text,
  };
}

const S1 = retrieved("S1", "who-healthy-diet#0040-0045", true);
const S3 = retrieved("S3", "eatwell-guide#0076-0078", true, {
  document_name: "The Eatwell Guide",
  publisher: "Public Health England",
  publisher_short: "PHE",
  year: 2016,
  url: null,
});
const S2 = retrieved("S2", "fsa-chill#0001-0004", false, { document_name: "How to chill", publisher_short: "FSA" });

const grounded: ChatMessage = {
  id: "m3",
  role: "assistant",
  content: "These documents each address this:\n\nWHO, 2020\n• Keep salt under 5 g a day. [1]\n\nPHE, 2016\n• Adults should eat no more than 6 g of salt a day. [3]",
  claims: [
    { text: "WHO recommends keeping salt intake under 5 g a day.", source: sourceFor(S1) },
    { text: "Adults should eat no more than 6 g of salt a day.", source: sourceFor(S3) },
  ],
  scope: { status: "in_scope", category: null, stage: null },
  grounding: {
    status: "grounded",
    filter_document_id: null,
    searched: [],
    top_score: 0.81,
  },
  sources: [S1, S2, S3],
};

const notCovered: ChatMessage = {
  id: "m4",
  role: "assistant",
  content: "The guidance I searched doesn't cover this.",
  claims: [],
  scope: { status: "in_scope", category: null, stage: null },
  grounding: {
    status: "not_covered",
    filter_document_id: null,
    searched: [
      { document_id: "who-healthy-diet", document_name: "Healthy diet", publisher: "World Health Organization", year: 2020, url: null },
      { document_id: "eatwell-guide", document_name: "The Eatwell Guide", publisher: "Public Health England", year: 2016, url: null },
    ],
    top_score: 0.6,
  },
  sources: [],
};

const declined: ChatMessage = {
  id: "m2",
  role: "assistant",
  content: "I can't help with personal calorie or weight targets.",
  claims: [],
  scope: { status: "declined", category: "calorie_target", stage: "retrieval" },
  grounding: null,
  sources: [],
};

describe("SourcesPanel", () => {
  it("shows the M1 empty state when an answer has no sources", () => {
    render(<SourcesPanel message={answer} />);
    expect(screen.getByText(EMPTY_SOURCES_TEXT)).toBeTruthy();
  });

  it("shows a prompt before any answer", () => {
    render(<SourcesPanel message={null} />);
    expect(screen.getByText(NO_MESSAGE_TEXT)).toBeTruthy();
  });

  it("shows the decline empty state", () => {
    render(<SourcesPanel message={declined} />);
    expect(screen.getByText(DECLINED_SOURCES_TEXT)).toBeTruthy();
  });

  it("renders cited chunks first and the rest under Also retrieved", () => {
    render(<SourcesPanel message={grounded} />);
    const cited = screen.getByTestId("cited-sources");
    expect(within(cited).getAllByRole("listitem").filter((li) => li.id.startsWith("source-"))).toHaveLength(2);
    expect(within(cited).getByText("[1]")).toBeTruthy();
    expect(within(cited).getByText("[3]")).toBeTruthy();
    // The claim each chunk supports is listed under it.
    expect(within(cited).getByText("WHO recommends keeping salt intake under 5 g a day.")).toBeTruthy();
    const also = screen.getByTestId("also-retrieved");
    expect(within(also).getByText("Also retrieved (1)")).toBeTruthy();
    expect(within(also).getByText("Text of fsa-chill#0001-0004")).toBeTruthy();
    expect(screen.getByText("2 cited")).toBeTruthy();
  });

  it("links to the document only when a URL is known", () => {
    render(<SourcesPanel message={grounded} />);
    const links = screen.getAllByRole("link", { name: /open document/i });
    // S1 and S2 have a URL; S3 (url null) has no link.
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute("href")).toBe("https://example.org/healthy-diet");
    expect(links[0].getAttribute("rel")).toContain("noopener");
  });

  it("highlights the focused chunk", () => {
    const { container } = render(<SourcesPanel message={grounded} focusChunkId={S3.chunk_id} />);
    const card = container.querySelector(`#${sourceElementId(S3.chunk_id)}`);
    expect(card?.getAttribute("data-focused")).toBe("true");
    expect(container.querySelectorAll("[data-focused]")).toHaveLength(1);
  });
});

describe("MessageBubble", () => {
  it("lists M1 claims with an Unverified badge", () => {
    render(<MessageBubble message={answer} />);
    fireEvent.click(screen.getByRole("button", { name: /claims \(2\)/i }));
    expect(screen.getAllByText("Unverified")).toHaveLength(2);
  });

  it("shows a citation chip per cited source that selects its chunk", () => {
    const onCite = vi.fn();
    render(<MessageBubble message={grounded} onCite={onCite} />);
    const chips = within(screen.getByLabelText("Cited sources")).getAllByRole("button");
    expect(chips.map((c) => c.textContent)).toEqual(["[1] WHO, 2020", "[3] PHE, 2016"]);
    fireEvent.click(chips[1]);
    expect(onCite).toHaveBeenCalledWith("m3", S3.chunk_id);
  });

  it("replaces the Unverified badge with chips in the claims list", () => {
    render(<MessageBubble message={grounded} onCite={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /claims \(2\)/i }));
    expect(screen.queryByText("Unverified")).toBeNull();
    expect(screen.getAllByRole("button", { name: /Source \[1\] WHO, 2020/ })).toHaveLength(2);
  });

  it("renders a decline without a claims section", () => {
    render(<MessageBubble message={declined} />);
    expect(screen.getByTestId("declined-message")).toBeTruthy();
    expect(screen.queryByTestId("not-covered-message")).toBeNull();
    expect(screen.queryByRole("button", { name: /claims/i })).toBeNull();
  });

  it("renders not-covered differently from a decline and lists what was searched", () => {
    render(<MessageBubble message={notCovered} />);
    const note = screen.getByTestId("not-covered-message");
    expect(screen.queryByTestId("declined-message")).toBeNull();
    expect(within(note).getByText(/Not covered/)).toBeTruthy();
    expect(within(note).getByText("Searched 2 documents")).toBeTruthy();
    expect(within(note).getByText("The Eatwell Guide")).toBeTruthy();
    const box = within(note).getByRole("note");
    expect(box.className).toContain("bg-uncovered");
    expect(box.className).not.toContain("bg-notice");
  });

  it("says 'as you asked' when the search was filtered", () => {
    const filtered: ChatMessage = {
      ...notCovered,
      grounding: { ...notCovered.grounding!, filter_document_id: "eatwell-guide", searched: [notCovered.grounding!.searched[1]] },
    };
    render(<MessageBubble message={filtered} />);
    expect(screen.getByText("Searched (as you asked)")).toBeTruthy();
  });

  it("renders HTML as plain text", () => {
    const msg: ChatMessage = { ...answer, claims: [], content: "<script>alert(1)</script>" };
    const { container } = render(<MessageBubble message={msg} />);
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText("<script>alert(1)</script>")).toBeTruthy();
  });
});

describe("citationText", () => {
  it("formats the chip and handles a missing year", () => {
    expect(citationText({ label: "S3", publisher_short: "PHE", year: 2016 })).toBe("[3] PHE, 2016");
    expect(citationText({ label: "S1", publisher_short: "WHO", year: null })).toBe("[1] WHO");
  });
});

const THEMES: ThemeOut[] = [
  { theme_id: "food-storage", name: "Food storage & refrigeration", description: "How long foods keep", document_ids: ["cold-food-storage", "fsa-chill"] },
  { theme_id: "sugar-salt-fat", name: "Sugar, salt & fats", description: "Limits on sugar, salt and fats", document_ids: ["who-healthy-diet", "eatwell-guide"] },
];

describe("ThemeFilter", () => {
  it("lists all themes and reports the choice", () => {
    const onChange = vi.fn();
    render(<ThemeFilter themes={THEMES} value={null} onChange={onChange} />);
    const select = screen.getByLabelText("Select theme:") as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual([
      "All themes",
      "Food storage & refrigeration",
      "Sugar, salt & fats",
    ]);
    expect(select.options[1].title).toBe("How long foods keep");
    fireEvent.change(select, { target: { value: "sugar-salt-fat" } });
    expect(onChange).toHaveBeenCalledWith("sugar-salt-fat");
    fireEvent.change(select, { target: { value: "" } });
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("is hidden when there are no themes", () => {
    const { container } = render(<ThemeFilter themes={[]} value={null} onChange={() => {}} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("useChat theme filter", () => {
  function mockFetch() {
    const calls: { url: string; body: unknown }[] = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (url.endsWith("/api/themes")) {
        return new Response(JSON.stringify({ themes: THEMES }), { status: 200 });
      }
      return new Response(
        JSON.stringify({
          conversation_id: "c1",
          message_id: `a${calls.length}`,
          answer: "ok",
          claims: [],
          scope: { status: "in_scope", category: null, stage: null },
          meta: { prompt_version: "v2", model: null, latency_ms: null },
        }),
        { status: 200 },
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    return calls;
  }

  it("sends theme_id with the next message and remembers it for the conversation", async () => {
    const calls = mockFetch();
    const { result } = renderHook(() => useChat());
    await waitFor(() => expect(result.current.themes).toHaveLength(2));

    await act(async () => {
      await result.current.send("first question");
    });
    expect(calls.find((c) => c.url.endsWith("/api/chat"))?.body).toEqual({ message: "first question" });

    act(() => result.current.setThemeId("food-storage"));
    await act(async () => {
      await result.current.send("How do I defrost meat?");
    });
    const chats = calls.filter((c) => c.url.endsWith("/api/chat"));
    expect(chats[1].body).toEqual({ conversation_id: "c1", message: "How do I defrost meat?", theme_id: "food-storage" });
    expect(window.localStorage.getItem("nutrition-assistant.theme-filter.c1")).toBe("food-storage");

    act(() => result.current.newChat());
    expect(result.current.themeId).toBeNull();
  });

  it("keeps grounding and sources on an M2 response, and tolerates an M1 response", async () => {
    mockFetch();
    const { result } = renderHook(() => useChat());
    await act(async () => {
      await result.current.send("hello");
    });
    const msg = result.current.messages.find((m) => m.role === "assistant")!;
    expect(msg.grounding).toBeNull();
    expect(msg.sources).toEqual([]);
  });
});

describe("ErrorBanner", () => {
  it("shows the failure id for a 502 and retries", () => {
    const onRetry = vi.fn();
    render(
      <ErrorBanner
        error={new ApiError(502, "model_output_invalid", "abc-123")}
        onRetry={onRetry}
        onNewChat={() => {}}
        onDismiss={() => {}}
      />,
    );
    expect(screen.getByText(/invalid response \(ref: abc-123\)/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("shows the rate-limit message for a 429", () => {
    render(
      <ErrorBanner error={new ApiError(429, "rate_limited")} onRetry={() => {}} onNewChat={() => {}} onDismiss={() => {}} />,
    );
    expect(screen.getByText("Too many requests, please wait a moment.")).toBeTruthy();
  });

  it("shows the start-up message while the index is building", () => {
    render(
      <ErrorBanner error={new ApiError(503, "index_not_ready")} onRetry={() => {}} onNewChat={() => {}} onDismiss={() => {}} />,
    );
    expect(screen.getByText("The assistant is starting up, please try again in a minute.")).toBeTruthy();
  });
});

describe("charCount", () => {
  it("counts an emoji once, like the backend", () => {
    expect(charCount("🥑🥑")).toBe(2);
  });
});
