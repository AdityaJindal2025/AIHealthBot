import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { charCount } from "@/components/ChatInput";
import { ErrorBanner } from "@/components/ErrorBanner";
import { MessageBubble } from "@/components/MessageBubble";
import { EMPTY_SOURCES_TEXT, SourcesPanel } from "@/components/SourcesPanel";
import { ApiError } from "@/lib/api";
import type { ChatMessage } from "@/lib/types";

afterEach(cleanup);

const answer: ChatMessage = {
  id: "m1",
  role: "assistant",
  content: "Lentils are high in fibre.",
  claims: [
    { text: "Lentils are high in fibre.", source: null },
    { text: "Lentils contain protein.", source: null },
  ],
  scope: { status: "in_scope", category: null, stage: null },
};

describe("SourcesPanel", () => {
  it("shows the empty state when every source is null", () => {
    render(<SourcesPanel claims={answer.claims} />);
    expect(screen.getByText(EMPTY_SOURCES_TEXT)).toBeTruthy();
  });
});

describe("MessageBubble", () => {
  it("lists claims with an Unverified badge", () => {
    render(<MessageBubble message={answer} />);
    fireEvent.click(screen.getByRole("button", { name: /claims \(2\)/i }));
    expect(screen.getAllByText("Unverified")).toHaveLength(2);
  });

  it("renders a decline without a claims section", () => {
    const declined: ChatMessage = {
      id: "m2",
      role: "assistant",
      content: "I can't help with personal calorie or weight targets.",
      claims: [],
      scope: { status: "declined", category: "weight_target", stage: "input" },
    };
    render(<MessageBubble message={declined} />);
    expect(screen.getByTestId("declined-message")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /claims/i })).toBeNull();
  });

  it("renders HTML as plain text", () => {
    const msg: ChatMessage = { ...answer, claims: [], content: "<script>alert(1)</script>" };
    const { container } = render(<MessageBubble message={msg} />);
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText("<script>alert(1)</script>")).toBeTruthy();
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
});

describe("charCount", () => {
  it("counts an emoji once, like the backend", () => {
    expect(charCount("🥑🥑")).toBe(2);
  });
});
