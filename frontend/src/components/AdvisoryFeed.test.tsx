import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import AdvisoryFeed from "./AdvisoryFeed";
import { useChatStore, ChatState } from "../core/store/useChatStore";

// Mock the zustand store
vi.mock("../core/store/useChatStore", () => ({
  useChatStore: vi.fn(),
}));

// Mock scrollIntoView as it's not implemented in JSDOM
window.HTMLElement.prototype.scrollIntoView = vi.fn();

describe("AdvisoryFeed", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders empty state when no messages", () => {
    vi.mocked(useChatStore).mockReturnValue({
      messages: [],
      isPending: false,
    } as unknown as ChatState);

    render(<AdvisoryFeed />);
    expect(screen.getByText(/No advisory history yet/i)).toBeInTheDocument();
  });

  it("renders messages when they exist", () => {
    vi.mocked(useChatStore).mockReturnValue({
      messages: [{ user_message: "Hi", ai_message: "Hello", jobs: [] }],
      isPending: false,
    } as unknown as ChatState);

    render(<AdvisoryFeed />);
    expect(screen.getByText("Hi")).toBeInTheDocument();
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("shows thinking indicator when isPending is true", () => {
    vi.mocked(useChatStore).mockReturnValue({
      messages: [],
      isPending: true,
    } as unknown as ChatState);

    render(<AdvisoryFeed />);
    expect(screen.getByText(/Thinking.../i)).toBeInTheDocument();
  });

  it("scrolls to bottom on new messages", () => {
    const { rerender } = render(<AdvisoryFeed />);

    vi.mocked(useChatStore).mockReturnValue({
      messages: [{ user_message: "New", ai_message: "Response", jobs: [] }],
      isPending: false,
    } as unknown as ChatState);

    rerender(<AdvisoryFeed />);
    expect(window.HTMLElement.prototype.scrollIntoView).toHaveBeenCalled();
  });
});
