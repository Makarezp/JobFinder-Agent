import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import AdvisoryFeed from "./AdvisoryFeed";
import { useChatStore } from "../core/store/useChatStore";
import type { ChatState } from "../core/store/useChatStore";

// Mock the zustand store
vi.mock("../core/store/useChatStore", () => ({
  useChatStore: vi.fn(),
  PENDING_AI_MESSAGE: "...",
}));

// Mock scrollIntoView as it's not implemented in JSDOM
window.HTMLElement.prototype.scrollIntoView = vi.fn();

/** Helper: makes useChatStore(selector) call the selector with the given state. */
function mockStoreState(partial: Partial<ChatState>) {
  const state: ChatState = {
    threads: { discovery: [], profile: [] },
    isPending: { discovery: false, profile: false },
    fetchHistory: vi.fn(),
    sendMessage: vi.fn(),
    uploadCV: vi.fn(),
    ...partial,
  };
  vi.mocked(useChatStore).mockImplementation(
    (selector?: (s: ChatState) => unknown) =>
      selector ? selector(state) : state
  );
}

describe("AdvisoryFeed", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStoreState({});
  });

  it("renders empty state when no messages", () => {
    mockStoreState({
      threads: { discovery: [], profile: [] },
      isPending: { discovery: false, profile: false },
    });

    render(<AdvisoryFeed workspace="discovery" />);
    expect(screen.getByText(/No advisory history yet/i)).toBeInTheDocument();
  });

  it("renders messages when they exist", () => {
    mockStoreState({
      threads: {
        discovery: [{ user_message: "Hi", ai_message: "Hello", jobs: [] }],
        profile: [],
      },
    });

    render(<AdvisoryFeed workspace="discovery" />);
    expect(screen.getByText("Hi")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("shows thinking indicator when isPending is true", () => {
    mockStoreState({
      isPending: { discovery: true, profile: false },
    });

    render(<AdvisoryFeed workspace="discovery" />);
    expect(screen.getByText(/Thinking.../i)).toBeInTheDocument();
  });

  it("scrolls to bottom on new messages", () => {
    // Clear the spy so we can assert exactly how many times it fires in this test
    vi.mocked(window.HTMLElement.prototype.scrollIntoView).mockClear();

    const { rerender } = render(<AdvisoryFeed workspace="discovery" />);

    mockStoreState({
      threads: {
        discovery: [{ user_message: "New", ai_message: "Response", jobs: [] }],
        profile: [],
      },
    });

    rerender(<AdvisoryFeed workspace="discovery" />);
    // Called once on initial render (mount effect) and once after rerender
    expect(window.HTMLElement.prototype.scrollIntoView).toHaveBeenCalledTimes(
      2
    );
  });
});
