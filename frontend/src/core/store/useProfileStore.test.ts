import { describe, it, expect, vi, beforeEach } from "vitest";
import { useProfileStore } from "./useProfileStore";
import * as profileApi from "../api/profile";
import { ProfileResponse } from "../types/api";

vi.mock("../api/profile", () => ({
  fetchProfileRequest: vi.fn(),
  submitFeedbackRequest: vi.fn(),
}));

const mockProfileResponse: ProfileResponse = {
  profile: {
    id: 1,
    name: "Jane Doe",
    role: "Senior Python Engineer",
    cv_summary: "10 years in backend systems.",
    cv_uploaded: true,
  },
  preferences: {
    remote: {
      key: "remote",
      label: "Remote only",
      sentiment: "positive",
    },
    no_agencies: {
      key: "no_agencies",
      label: "No agencies",
      sentiment: "negative",
    },
  },
  decisions: [
    {
      job_title: "Fullstack Dev",
      company: "FintechCorp",
      action: "pass",
      reason: "Legacy technology stack",
      timestamp: "2026-02-22T10:00:00+00:00",
    },
    {
      job_title: "Senior Python",
      company: "AgencyX",
      action: "pass",
      reason: "Agency model",
      timestamp: "2026-02-21T09:00:00+00:00",
    },
  ],
};

describe("useProfileStore", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    useProfileStore.setState({
      profile: null,
      preferences: {},
      decisions: [],
      isPending: false,
    });
  });

  describe("initialization", () => {
    it("starts with null profile and empty collections", () => {
      const state = useProfileStore.getState();
      expect(state.profile).toBeNull();
      expect(state.preferences).toEqual({});
      expect(state.decisions).toEqual([]);
      expect(state.isPending).toBe(false);
    });
  });

  describe("fetchProfile — loading state", () => {
    it("sets isPending to true while fetching", async () => {
      vi.mocked(profileApi.fetchProfileRequest).mockResolvedValueOnce(
        mockProfileResponse
      );

      const promise = useProfileStore.getState().fetchProfile();
      expect(useProfileStore.getState().isPending).toBe(true);

      await promise;
      expect(useProfileStore.getState().isPending).toBe(false);
    });
  });

  describe("fetchProfile — populated state", () => {
    it("populates profile, preferences, and decisions from response", async () => {
      vi.mocked(profileApi.fetchProfileRequest).mockResolvedValueOnce(
        mockProfileResponse
      );

      await useProfileStore.getState().fetchProfile();

      const state = useProfileStore.getState();
      expect(state.profile).toEqual(mockProfileResponse.profile);
      expect(state.preferences).toEqual(mockProfileResponse.preferences);
      expect(state.decisions).toEqual(mockProfileResponse.decisions);
      expect(state.isPending).toBe(false);
    });
  });

  describe("fetchProfile — error state", () => {
    it("logs error and resets isPending without mutating existing state", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      vi.mocked(profileApi.fetchProfileRequest).mockRejectedValueOnce(
        new Error("Network error")
      );

      // Seed existing state so we can verify it's not mutated on error
      useProfileStore.setState({ profile: mockProfileResponse.profile });

      await useProfileStore.getState().fetchProfile();

      const state = useProfileStore.getState();
      expect(state.isPending).toBe(false);
      expect(state.profile).toEqual(mockProfileResponse.profile); // unchanged
      expect(consoleSpy).toHaveBeenCalledOnce();

      consoleSpy.mockRestore();
    });
  });
});
