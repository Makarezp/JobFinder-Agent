import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  fetchHistoryRequest,
  sendMessageRequest,
  uploadCVRequest,
} from "./chat";

// Mock the global fetch function
global.fetch = vi.fn();

describe("chat API clients", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  describe("fetchHistoryRequest", () => {
    it("fetches discovery history with workspace query param", async () => {
      const mockHistory = [
        { user_message: "hi", ai_message: "hello", jobs: [] },
      ];
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockHistory,
      } as Response);

      const result = await fetchHistoryRequest("discovery");

      expect(fetch).toHaveBeenCalledWith("/api/history?workspace=discovery");
      expect(result).toEqual(mockHistory);
    });

    it("fetches profile history with workspace query param", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as Response);

      await fetchHistoryRequest("profile");

      expect(fetch).toHaveBeenCalledWith("/api/history?workspace=profile");
    });

    it("defaults to discovery workspace", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as Response);

      await fetchHistoryRequest();

      expect(fetch).toHaveBeenCalledWith("/api/history?workspace=discovery");
    });

    it("throws an error on failure", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 500,
      } as Response);

      await expect(fetchHistoryRequest()).rejects.toThrow(
        "HTTP error! status: 500"
      );
    });
  });

  describe("sendMessageRequest", () => {
    it("successfully sends a message with workspace in body", async () => {
      const mockResponse = {
        user_message: "test",
        ai_message: "reply",
        jobs: [],
      };
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const result = await sendMessageRequest("test", "discovery");

      expect(fetch).toHaveBeenCalledWith("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "test", workspace: "discovery" }),
      });
      expect(result).toEqual(mockResponse);
    });

    it("sends with profile workspace", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ user_message: "x", ai_message: "y", jobs: [] }),
      } as Response);

      await sendMessageRequest("update name", "profile");

      expect(fetch).toHaveBeenCalledWith("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: "update name", workspace: "profile" }),
      });
    });

    it("defaults to discovery workspace", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => ({ user_message: "x", ai_message: "y", jobs: [] }),
      } as Response);

      await sendMessageRequest("hello");

      const body = JSON.parse(
        vi.mocked(fetch).mock.calls[0][1]?.body as string
      );
      expect(body.workspace).toBe("discovery");
    });

    it("throws an error on failure", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 400,
      } as Response);

      await expect(sendMessageRequest("fail")).rejects.toThrow(
        "HTTP error! status: 400"
      );
    });
  });

  describe("uploadCVRequest", () => {
    it("successfully uploads a CV", async () => {
      const mockResponse = {
        user_message: "pdf",
        ai_message: "parsed",
        jobs: [],
      };
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      } as Response);

      const mockFile = new File(["test"], "test.pdf", {
        type: "application/pdf",
      });
      const result = await uploadCVRequest(mockFile);

      expect(fetch).toHaveBeenCalledWith("/api/upload-cv", {
        method: "POST",
        body: expect.any(FormData),
      });

      // Verify the FormData contains the file
      const fetchCallArgs = vi.mocked(fetch).mock.calls[0];
      const formData = fetchCallArgs[1]?.body as FormData;
      expect(formData.get("file")).toBe(mockFile);

      expect(result).toEqual(mockResponse);
    });

    it("throws an error on failure", async () => {
      vi.mocked(fetch).mockResolvedValueOnce({
        ok: false,
        status: 413,
      } as Response);

      const mockFile = new File(["too big"], "huge.pdf");
      await expect(uploadCVRequest(mockFile)).rejects.toThrow(
        "HTTP error! status: 413"
      );
    });
  });
});
