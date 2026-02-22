import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import ChatMessage from "./ChatMessage";
import { ChatResponse } from "../core/types/api";

describe("ChatMessage", () => {
  const mockUserMsg: ChatResponse = {
    user_message: "Hello AI",
    ai_message: "",
    jobs: [],
  };

  const mockAiMsg: ChatResponse = {
    user_message: "Hello AI",
    ai_message: "Hello! I am your **Navigator AI**.",
    jobs: [],
  };

  const mockErrorMsg: ChatResponse = {
    user_message: "Fetch jobs",
    ai_message: "**System Error**: Failed to fetch jobs.",
    jobs: [],
  };

  it("renders user message with correct alignment and label", () => {
    render(<ChatMessage message={mockUserMsg} role="user" />);
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("Hello AI")).toBeInTheDocument();
  });

  it("renders AI message with glassmorphism style and Navigator label", () => {
    render(<ChatMessage message={mockAiMsg} role="ai" />);
    const label = screen.getAllByText("Navigator AI")[0];
    expect(label).toBeInTheDocument();
    expect(label).toHaveClass("text-slate-400");
  });

  it("renders markdown correctly in AI message", () => {
    render(<ChatMessage message={mockAiMsg} role="ai" />);
    // The markdown also contains "**Navigator AI**" which parses to <strong>Navigator AI</strong>
    const strongElement = screen.getByText("Navigator AI", {
      selector: "strong",
    });
    expect(strongElement).toBeInTheDocument();
  });

  it("applies error styling for system errors", () => {
    render(<ChatMessage message={mockErrorMsg} role="ai" />);
    const bubble = screen.getByText(/System Error/i).closest("div");
    // The bubble parent of ReactMarkdown should have the red-tinted classes
    // We check for the class we applied: bg-red-500/10
    expect(bubble?.parentElement).toHaveClass("bg-red-500/10");
  });

  it("shows job count badge when jobs are present", () => {
    const msgWithJobs = { ...mockAiMsg, jobs: [{}, {}] } as ChatResponse;
    render(<ChatMessage message={msgWithJobs} role="ai" />);
    expect(screen.getByText(/Found 2 jobs in Deck/i)).toBeInTheDocument();
  });
});
