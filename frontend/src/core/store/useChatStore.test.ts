import { describe, it, expect, vi, beforeEach } from "vitest";
import { useChatStore, PENDING_AI_MESSAGE } from "./useChatStore";
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
    useChatStore.setState({
      threads: { discovery: [], profile: [] },
      isPending: { discovery: false, profile: false },
    });
    vi.mocked(useJobStore.getState).mockReturnValue({
      jobs: [],
      isLoading: false,
      error: null,
      fetchDeck: vi.fn().mockResolvedValue(undefined),
      submitFeedback: vi.fn(),
      resetDiscovery: vi.fn(),
    });
  });

  describe("Initialization", () => {
    it("initializes with empty threads and isPending false for both workspaces", () => {
      const state = useChatStore.getState();
      expect(state.threads.discovery).toEqual([]);
      expect(state.threads.profile).toEqual([]);
      expect(state.isPending.discovery).toBe(false);
      expect(state.isPending.profile).toBe(false);
    });
  });

  describe("fetchHistory", () => {
    it("fetches discovery history and updates only the discovery thread", async () => {
      const mockHistory = [{ user_message: "u", ai_message: "a", jobs: [] }];
      vi.mocked(chatApi.fetchHistoryRequest).mockResolvedValueOnce(mockHistory);

      const promise = useChatStore.getState().fetchHistory("discovery");

      expect(useChatStore.getState().isPending.discovery).toBe(true);
      expect(useChatStore.getState().isPending.profile).toBe(false);

      await promise;

      expect(useChatStore.getState().threads.discovery).toEqual(mockHistory);
      expect(useChatStore.getState().threads.profile).toEqual([]);
      expect(useChatStore.getState().isPending.discovery).toBe(false);
    });

    it("fetches profile history and updates only the profile thread", async () => {
      const mockHistory = [{ user_message: "p", ai_message: "b", jobs: [] }];
      vi.mocked(chatApi.fetchHistoryRequest).mockResolvedValueOnce(mockHistory);

      await useChatStore.getState().fetchHistory("profile");

      expect(useChatStore.getState().threads.profile).toEqual(mockHistory);
      expect(useChatStore.getState().threads.discovery).toEqual([]);
    });

    it("handles errors gracefully and clears pending", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      vi.mocked(chatApi.fetchHistoryRequest).mockRejectedValueOnce(
        new Error("Network Error")
      );

      await useChatStore.getState().fetchHistory("discovery");

      expect(useChatStore.getState().threads.discovery).toEqual([]);
      expect(useChatStore.getState().isPending.discovery).toBe(false);
      // A discovery-scoped error must not touch the profile thread
      expect(useChatStore.getState().threads.profile).toEqual([]);

      consoleSpy.mockRestore();
    });
  });

  describe("sendMessage", () => {
    it("performs an optimistic update in the discovery thread and resolves actual response", async () => {
      const actualResponse = {
        user_message: "test",
        ai_message: "real ai reply",
        jobs: [],
      };
      vi.mocked(chatApi.sendMessageRequest).mockResolvedValueOnce(
        actualResponse
      );

      const promise = useChatStore.getState().sendMessage("test", "discovery");

      let state = useChatStore.getState();
      expect(state.isPending.discovery).toBe(true);
      expect(state.isPending.profile).toBe(false);
      expect(state.threads.discovery).toHaveLength(1);
      expect(state.threads.discovery[0].user_message).toBe("test");
      expect(state.threads.discovery[0].ai_message).toBe(PENDING_AI_MESSAGE);

      await promise;

      state = useChatStore.getState();
      expect(state.isPending.discovery).toBe(false);
      expect(state.threads.discovery).toHaveLength(1);
      expect(state.threads.discovery[0].ai_message).toBe("real ai reply");
      expect(state.threads.profile).toHaveLength(0);
    });

    it("sends to profile thread without touching discovery thread", async () => {
      vi.mocked(chatApi.sendMessageRequest).mockResolvedValueOnce({
        user_message: "update name",
        ai_message: "done",
        jobs: [],
      });

      await useChatStore.getState().sendMessage("update name", "profile");

      const state = useChatStore.getState();
      expect(state.threads.profile).toHaveLength(1);
      expect(state.threads.discovery).toHaveLength(0);
    });

    it("calls fetchDeck when response contains jobs", async () => {
      const mockFetchDeck = vi.fn().mockResolvedValue(undefined);
      vi.mocked(useJobStore.getState).mockReturnValue({
        jobs: [],
        isLoading: false,
        error: null,
        fetchDeck: mockFetchDeck,
        submitFeedback: vi.fn(),
        resetDiscovery: vi.fn(),
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

      await useChatStore.getState().sendMessage("find jobs", "discovery");

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
        resetDiscovery: vi.fn(),
      });

      vi.mocked(chatApi.sendMessageRequest).mockResolvedValueOnce({
        user_message: "hello",
        ai_message: "hi",
        jobs: [],
      });

      await useChatStore.getState().sendMessage("hello", "discovery");

      expect(mockFetchDeck).not.toHaveBeenCalled();
    });

    it("injects a system error message into the correct thread on API failure", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      vi.mocked(chatApi.sendMessageRequest).mockRejectedValueOnce(
        new Error("Server down")
      );

      await useChatStore.getState().sendMessage("test", "discovery");

      const state = useChatStore.getState();
      expect(state.isPending.discovery).toBe(false);
      expect(state.threads.discovery).toHaveLength(1);
      expect(state.threads.discovery[0].ai_message).toContain(
        "**System Error**"
      );
      expect(state.threads.profile).toHaveLength(0);

      consoleSpy.mockRestore();
    });
  });

  describe("uploadCV", () => {
    it("targets the profile thread for optimistic update and success", async () => {
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

      let state = useChatStore.getState();
      expect(state.isPending.profile).toBe(true);
      expect(state.isPending.discovery).toBe(false);
      expect(state.threads.profile[0].user_message).toBe(
        "Uploaded CV: mycv.pdf"
      );
      expect(state.threads.profile[0].ai_message).toBe(PENDING_AI_MESSAGE);

      await promise;

      state = useChatStore.getState();
      expect(state.isPending.profile).toBe(false);
      expect(state.threads.profile[0].ai_message).toBe("parsed");
      expect(state.threads.discovery).toHaveLength(0);
    });

    it("injects a system error message into the profile thread on failure", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      vi.mocked(chatApi.uploadCVRequest).mockRejectedValueOnce(
        new Error("Upload failed")
      );

      const file = new File(["content"], "bad.pdf", {
        type: "application/pdf",
      });

      await useChatStore.getState().uploadCV(file);

      const state = useChatStore.getState();
      expect(state.isPending.profile).toBe(false);
      expect(state.threads.profile).toHaveLength(1);
      expect(state.threads.profile[0].ai_message).toContain("**System Error**");

      consoleSpy.mockRestore();
    });
  });
});
