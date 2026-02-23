import { act, renderHook } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useJobStore } from "./useJobStore";
import * as profileApi from "../api/profile";
import { useProfileStore } from "./useProfileStore";
import { Job } from "../types/api";

vi.mock("../api/profile", () => ({
  fetchProfileRequest: vi.fn(),
  submitFeedbackRequest: vi.fn(),
}));

vi.mock("./useProfileStore", () => ({
  useProfileStore: {
    getState: vi.fn(() => ({
      fetchProfile: vi.fn(),
    })),
  },
}));

const mockJob1: Job = {
  id: "aabbcc112233",
  title: "Software Engineer",
  company: "Tech Corp",
  location: "Remote",
  salary: "100k - 150k",
  description: "Great job",
  apply_link: "https://example.com/1",
};

const mockJob2: Job = {
  id: "ddeeff445566",
  title: "Python Architect",
  company: "DataCorp",
  location: "London",
  salary: "120k",
  description: "Big data systems",
  apply_link: "https://example.com/2",
};

describe("useJobStore", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    useJobStore.setState({ jobs: [] });
    // Restore the mock after reset
    vi.mocked(useProfileStore.getState).mockReturnValue({
      fetchProfile: vi.fn(),
      profile: null,
      preferences: {},
      decisions: [],
      isPending: false,
    });
  });

  describe("initialization", () => {
    it("should initialize with an empty jobs array", () => {
      const { result } = renderHook(() => useJobStore());
      expect(result.current.jobs).toEqual([]);
    });
  });

  describe("setJobs", () => {
    it("should set jobs correctly", () => {
      const { result } = renderHook(() => useJobStore());

      act(() => {
        result.current.setJobs([mockJob1]);
      });

      expect(result.current.jobs).toEqual([mockJob1]);
    });
  });

  describe("submitFeedback", () => {
    it("optimistically removes the job from state before the API call resolves", async () => {
      useJobStore.setState({ jobs: [mockJob1, mockJob2] });
      vi.mocked(profileApi.submitFeedbackRequest).mockResolvedValueOnce(
        undefined
      );

      const promise = useJobStore
        .getState()
        .submitFeedback(mockJob1, "pass", "Too senior");

      // Optimistic removal is synchronous — assert immediately
      expect(useJobStore.getState().jobs).toHaveLength(1);
      expect(useJobStore.getState().jobs[0].id).toBe(mockJob2.id);

      await promise;
    });

    it("calls submitFeedbackRequest with the correct payload", async () => {
      useJobStore.setState({ jobs: [mockJob1] });
      vi.mocked(profileApi.submitFeedbackRequest).mockResolvedValueOnce(
        undefined
      );

      await useJobStore
        .getState()
        .submitFeedback(mockJob1, "pass", "Too senior");

      expect(profileApi.submitFeedbackRequest).toHaveBeenCalledWith({
        job_title: mockJob1.title,
        company: mockJob1.company,
        action: "pass",
        description: mockJob1.description,
        reason: "Too senior",
      });
    });

    it("refreshes the profile store after successful feedback", async () => {
      useJobStore.setState({ jobs: [mockJob1] });
      vi.mocked(profileApi.submitFeedbackRequest).mockResolvedValueOnce(
        undefined
      );
      const mockFetchProfile = vi.fn().mockResolvedValueOnce(undefined);
      vi.mocked(useProfileStore.getState).mockReturnValue({
        fetchProfile: mockFetchProfile,
        profile: null,
        preferences: {},
        decisions: [],
        isPending: false,
      });

      await useJobStore.getState().submitFeedback(mockJob1, "pass", null);

      expect(mockFetchProfile).toHaveBeenCalledOnce();
    });

    it("logs error but does not roll back optimistic removal on failure", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      useJobStore.setState({ jobs: [mockJob1, mockJob2] });
      vi.mocked(profileApi.submitFeedbackRequest).mockRejectedValueOnce(
        new Error("Network error")
      );

      await useJobStore.getState().submitFeedback(mockJob1, "pass", null);

      // Card stays removed even after failure
      expect(useJobStore.getState().jobs).toHaveLength(1);
      expect(consoleSpy).toHaveBeenCalledOnce();

      consoleSpy.mockRestore();
    });
  });
});
