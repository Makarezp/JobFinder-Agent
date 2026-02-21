import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import CommandCenter from "./CommandCenter";
import { useChatStore, ChatState } from "../core/store/useChatStore";

// Mock the zustand store
vi.mock("../core/store/useChatStore", () => ({
  useChatStore: vi.fn(),
}));

describe("CommandCenter", () => {
  const mockSendMessage = vi.fn();
  const mockUploadCV = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useChatStore).mockReturnValue({
      isPending: false,
      sendMessage: mockSendMessage,
      uploadCV: mockUploadCV,
      fetchHistory: vi.fn(),
      messages: [],
    } as ChatState);
  });

  it("renders the input and buttons", () => {
    render(<CommandCenter />);
    expect(screen.getByPlaceholderText(/Ask Navigator/i)).toBeInTheDocument();
    expect(screen.getByTitle(/Attach CV/i)).toBeInTheDocument();
  });

  it("updates input text on change", () => {
    render(<CommandCenter />);
    const input = screen.getByPlaceholderText(
      /Ask Navigator/i
    ) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Hello AI" } });
    expect(input.value).toBe("Hello AI");
  });

  it("calls sendMessage when Enter is pressed", () => {
    render(<CommandCenter />);
    const input = screen.getByPlaceholderText(/Ask Navigator/i);
    fireEvent.change(input, { target: { value: "Search Python jobs" } });
    fireEvent.keyDown(input, { key: "Enter", code: "Enter" });
    expect(mockSendMessage).toHaveBeenCalledWith("Search Python jobs");
    expect((input as HTMLInputElement).value).toBe("");
  });

  it("calls sendMessage when Send button is clicked", () => {
    render(<CommandCenter />);
    const input = screen.getByPlaceholderText(/Ask Navigator/i);
    fireEvent.change(input, { target: { value: "Search Python jobs" } });

    const sendBtn = screen.getByRole("button", { name: /Send message/i });

    if (sendBtn) {
      fireEvent.click(sendBtn);
      expect(mockSendMessage).toHaveBeenCalledWith("Search Python jobs");
    }
  });

  it("disables inputs when isPending is true", () => {
    vi.mocked(useChatStore).mockReturnValue({
      isPending: true,
      sendMessage: mockSendMessage,
      uploadCV: mockUploadCV,
      fetchHistory: vi.fn(),
      messages: [],
    } as ChatState);

    render(<CommandCenter />);
    const input = screen.getByPlaceholderText(/Ask Navigator/i);
    const attachButton = screen.getByTitle(/Attach CV/i);

    expect(input).toBeDisabled();
    expect(attachButton).toBeDisabled();
    expect(screen.getByText(/Agent is processing/i)).toBeInTheDocument();
  });

  it("triggers file upload on file change", () => {
    render(<CommandCenter />);
    // Actually, finding by type="file" is better
    const input = document.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;

    const file = new File(["cv content"], "cv.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(input, { target: { files: [file] } });

    expect(mockUploadCV).toHaveBeenCalledWith(file);
  });
});
