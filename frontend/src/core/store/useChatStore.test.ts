import { describe, it, expect, vi, beforeEach } from "vitest";
import { useChatStore } from "./useChatStore";
import * as chatApi from "../api/chat";
import { useJobStore } from "./useJobStore";

// Mock the API layer
vi.mock("../api/chat", () => ({
  fetchHistoryRequest: vi.fn(),
  sendMessageRequest: vi.fn(),
  uploadCVRequest: vi.fn(),
}));

vi.mock("./useJobStore", () => ({
  useJobStore: {
    getState: vi.fn(() => ({
      fetchDeck: vi.fn().mockResolvedValue(undefined),
    })),
  },
}));

describe("useChatStore", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    useChatStore.setState({ messages: [], isPending: false });
    vi.mocked(useJobStore.getState).mockReturnValue({
      jobs: [],
      isLoading: false,
      error: null,
      fetchDeck: vi.fn().mockResolvedValue(undefined),
      submitFeedback: vi.fn(),
    });
  });

  describe("Initialization", () => {
    it("initializes with empty messages and isPending false", () => {
      const state = useChatStore.getState();
      expect(state.messages).toEqual([]);
      expect(state.isPending).toBe(false);
    });
  });

  describe("fetchHistory", () => {
    it("fetches history and updates state", async () => {
      const mockHistory = [{ user_message: "u", ai_message: "a", jobs: [] }];
      vi.mocked(chatApi.fetchHistoryRequest).mockResolvedValueOnce(mockHistory);

      const promise = useChatStore.getState().fetchHistory();

      // Should immediately be pending
      expect(useChatStore.getState().isPending).toBe(true);

      await promise;

      // Should have results and not be pending
      expect(useChatStore.getState().messages).toEqual(mockHistory);
      expect(useChatStore.getState().isPending).toBe(false);
    });

    it("handles errors gracefully", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      vi.mocked(chatApi.fetchHistoryRequest).mockRejectedValueOnce(
        new Error("Network Error")
      );

      await useChatStore.getState().fetchHistory();

      expect(useChatStore.getState().messages).toEqual([]); // unchanged
      expect(useChatStore.getState().isPending).toBe(false);

      consoleSpy.mockRestore();
    });
  });

  describe("sendMessage", () => {
    it("performs an optimistic update and resolves actual response", async () => {
      const actualResponse = {
        user_message: "test",
        ai_message: "real ai reply",
        jobs: [],
      };
      vi.mocked(chatApi.sendMessageRequest).mockResolvedValueOnce(
        actualResponse
      );

      const promise = useChatStore.getState().sendMessage("test");

      // Verify optimistic update (loading indicator)
      let state = useChatStore.getState();
      expect(state.isPending).toBe(true);
      expect(state.messages).toHaveLength(1);
      expect(state.messages[0].user_message).toBe("test");
      expect(state.messages[0].ai_message).toBe("...");

      await promise;

      // Verify actual update
      state = useChatStore.getState();
      expect(state.isPending).toBe(false);
      expect(state.messages).toHaveLength(1);
      expect(state.messages[0].ai_message).toBe("real ai reply");
    });

    it("calls fetchDeck (not setJobs) when response contains jobs", async () => {
      const mockFetchDeck = vi.fn().mockResolvedValue(undefined);
      vi.mocked(useJobStore.getState).mockReturnValue({
        jobs: [],
        isLoading: false,
        error: null,
        fetchDeck: mockFetchDeck,
        submitFeedback: vi.fn(),
      });

      const actualResponse = {
        user_message: "find jobs",
        ai_message: "here are jobs",
        jobs: [
          {
            id: "abc123",
            title: "Dev",
            company: "Corp",
            location: "Remote",
            salary: null,
            description: "desc",
            full_description: null,
            apply_link: "https://x.com",
          },
        ],
      };
      vi.mocked(chatApi.sendMessageRequest).mockResolvedValueOnce(
        actualResponse
      );

      await useChatStore.getState().sendMessage("find jobs");

      expect(mockFetchDeck).toHaveBeenCalledOnce();
    });

    it("does not call fetchDeck when response has no jobs", async () => {
      const mockFetchDeck = vi.fn().mockResolvedValue(undefined);
      vi.mocked(useJobStore.getState).mockReturnValue({
        jobs: [],
        isLoading: false,
        error: null,
        fetchDeck: mockFetchDeck,
        submitFeedback: vi.fn(),
      });

      vi.mocked(chatApi.sendMessageRequest).mockResolvedValueOnce({
        user_message: "hello",
        ai_message: "hi",
        jobs: [],
      });

      await useChatStore.getState().sendMessage("hello");

      expect(mockFetchDeck).not.toHaveBeenCalled();
    });

    it("handles API errors by injecting a system error message", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      vi.mocked(chatApi.sendMessageRequest).mockRejectedValueOnce(
        new Error("Server down")
      );

      await useChatStore.getState().sendMessage("test");

      const state = useChatStore.getState();
      expect(state.isPending).toBe(false);
      expect(state.messages).toHaveLength(1);
      expect(state.messages[0].ai_message).toContain("**System Error**");

      consoleSpy.mockRestore();
    });
  });

  describe("uploadCV", () => {
    it("reports optimistic upload status and handles success", async () => {
      const actualResponse = {
        user_message: "Uploaded CV: mycv.pdf",
        ai_message: "parsed",
        jobs: [],
      };
      vi.mocked(chatApi.uploadCVRequest).mockResolvedValueOnce(actualResponse);

      const file = new File(["dummy content"], "mycv.pdf", {
        type: "application/pdf",
      });
      const promise = useChatStore.getState().uploadCV(file);

      // Verify optimistic state
      let state = useChatStore.getState();
      expect(state.isPending).toBe(true);
      expect(state.messages[0].user_message).toBe("Uploaded CV: mycv.pdf");
      expect(state.messages[0].ai_message).toBe("Processing CV...");

      await promise;

      state = useChatStore.getState();
      expect(state.isPending).toBe(false);
      expect(state.messages[0].ai_message).toBe("parsed");
    });
  });
});
