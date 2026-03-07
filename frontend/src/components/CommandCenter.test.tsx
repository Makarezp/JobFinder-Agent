import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import CommandCenter from "./CommandCenter";
import { useChatStore } from "../core/store/useChatStore";
import type { ChatState } from "../core/store/useChatStore";

// Mock the zustand store
vi.mock("../core/store/useChatStore", () => ({
  useChatStore: vi.fn(),
  PENDING_AI_MESSAGE: "...",
}));

describe("CommandCenter", () => {
  const mockSendMessage = vi.fn();
  const mockUploadCV = vi.fn();

  /** Helper: makes useChatStore(selector) call the selector with the given state. */
  function mockStoreState(overrides?: Partial<ChatState>) {
    const state: ChatState = {
      threads: { discovery: [], profile: [] },
      isPending: { discovery: false, profile: false },
      sendMessage: mockSendMessage,
      uploadCV: mockUploadCV,
      fetchHistory: vi.fn(),
      ...overrides,
    };
    vi.mocked(useChatStore).mockImplementation(
      (selector?: (s: ChatState) => unknown) =>
        selector ? selector(state) : state
    );
  }

  beforeEach(() => {
    vi.clearAllMocks();
    mockStoreState();
  });

  it("renders the discovery placeholder and no attach button in discovery workspace", () => {
    render(<CommandCenter workspace="discovery" />);
    expect(screen.getByPlaceholderText(/Ask Navigator/i)).toBeInTheDocument();
    expect(screen.queryByTitle(/Attach CV/i)).not.toBeInTheDocument();
  });

  it("renders the profile placeholder and attach button in profile workspace", () => {
    render(<CommandCenter workspace="profile" />);
    expect(
      screen.getByPlaceholderText(/Discuss your background/i)
    ).toBeInTheDocument();
    expect(screen.getByTitle(/Attach CV/i)).toBeInTheDocument();
  });

  it("updates input text on change", () => {
    render(<CommandCenter workspace="discovery" />);
    const input = screen.getByPlaceholderText(
      /Ask Navigator/i
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Hello AI" } });
    expect(input.value).toBe("Hello AI");
  });

  it("calls sendMessage when Enter is pressed", () => {
    render(<CommandCenter workspace="discovery" />);
    const input = screen.getByPlaceholderText(/Ask Navigator/i);
    fireEvent.change(input, { target: { value: "Search Python jobs" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });
    expect(mockSendMessage).toHaveBeenCalledWith(
      "Search Python jobs",
      "discovery"
    );
    expect((input as HTMLInputElement).value).toBe("");
  });

  it("calls sendMessage when Send button is clicked", () => {
    render(<CommandCenter workspace="discovery" />);
    const input = screen.getByPlaceholderText(/Ask Navigator/i);
    fireEvent.change(input, { target: { value: "Search Python jobs" } });

    const sendBtn = screen.getByRole("button", { name: /Send message/i });
    fireEvent.click(sendBtn);
    expect(mockSendMessage).toHaveBeenCalledWith(
      "Search Python jobs",
      "discovery"
    );
  });

  it("disables inputs when isPending is true", () => {
    mockStoreState({
      isPending: { discovery: true, profile: false },
    });

    render(<CommandCenter workspace="discovery" />);
    const input = screen.getByPlaceholderText(/Ask Navigator/i);

    expect(input).toBeDisabled();
    expect(screen.getByText(/Agent is processing/i)).toBeInTheDocument();
  });

  it("triggers file upload on file change (profile workspace)", () => {
    render(<CommandCenter workspace="profile" />);
    const attachButton = screen.getByTitle(/Attach CV/i);
    expect(attachButton).toBeInTheDocument();

    const fileInput = screen.getByTestId("cv-file-input") as HTMLInputElement;

    const file = new File(["cv content"], "cv.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(fileInput, { target: { files: [file] } });

    expect(mockUploadCV).toHaveBeenCalledWith(file);
  });
});
