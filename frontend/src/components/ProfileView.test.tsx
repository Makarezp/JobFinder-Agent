import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ProfileView from "./ProfileView";

vi.mock("../core/store/useProfileStore", () => ({
  useProfileStore: vi.fn(),
}));

vi.mock("../core/store/useChatStore", () => ({
  useChatStore: vi.fn(() => vi.fn()),
}));

import { useProfileStore } from "../core/store/useProfileStore";

const mockProfile = {
  id: 1,
  name: "Jane Doe",
  role: "Senior Python Engineer",
  cv_summary: "10 years in backend systems.",
  cv_uploaded: true,
};

const mockPreferences = {
  remote: {
    key: "remote",
    label: "Remote only",
    sentiment: "positive" as const,
  },
  no_agencies: {
    key: "no_agencies",
    label: "No agencies",
    sentiment: "negative" as const,
  },
};

const mockDecisions = [
  {
    job_title: "Fullstack Dev",
    company: "FintechCorp",
    action: "pass" as const,
    reason: "Legacy technology stack",
    timestamp: "2026-02-22T10:00:00+00:00",
  },
];

describe("ProfileView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("loading state", () => {
    it("renders a loading indicator when isPending is true", () => {
      vi.mocked(useProfileStore).mockReturnValue({
        profile: null,
        preferences: {},
        decisions: [],
        isPending: true,
        fetchProfile: vi.fn(),
      });

      render(<ProfileView />);
      expect(screen.getByTestId("profile-loading")).toBeInTheDocument();
    });
  });

  describe("empty state", () => {
    it("renders the empty state message when profile is null and not loading", () => {
      vi.mocked(useProfileStore).mockReturnValue({
        profile: null,
        preferences: {},
        decisions: [],
        isPending: false,
        fetchProfile: vi.fn(),
      });

      render(<ProfileView />);
      expect(screen.getByTestId("profile-empty")).toBeInTheDocument();
      expect(
        screen.getByText(/I don't know much about you yet/i)
      ).toBeInTheDocument();
    });
  });

  describe("populated state", () => {
    beforeEach(() => {
      vi.mocked(useProfileStore).mockReturnValue({
        profile: mockProfile,
        preferences: mockPreferences,
        decisions: mockDecisions,
        isPending: false,
        fetchProfile: vi.fn(),
      });
    });

    it("renders the user name and role", () => {
      render(<ProfileView />);
      expect(screen.getByText("Jane Doe")).toBeInTheDocument();
      expect(screen.getByText("Senior Python Engineer")).toBeInTheDocument();
    });

    it("renders the AI summary", () => {
      render(<ProfileView />);
      expect(
        screen.getByText("10 years in backend systems.")
      ).toBeInTheDocument();
    });

    it("renders a positive preference under Looking For", () => {
      render(<ProfileView />);
      expect(screen.getByText(/Looking For/i)).toBeInTheDocument();
      expect(screen.getByText("Remote only")).toBeInTheDocument();
    });

    it("renders a negative preference under Avoiding", () => {
      render(<ProfileView />);
      expect(screen.getByText(/Avoiding/i)).toBeInTheDocument();
    });

    it("renders a decision log entry with job title and reason", () => {
      render(<ProfileView />);
      expect(screen.getByText("Fullstack Dev")).toBeInTheDocument();
      expect(screen.getByText("Legacy technology stack")).toBeInTheDocument();
    });

    it("renders no-feedback message when decisions array is empty", () => {
      vi.mocked(useProfileStore).mockReturnValue({
        profile: mockProfile,
        preferences: {},
        decisions: [],
        isPending: false,
        fetchProfile: vi.fn(),
      });

      render(<ProfileView />);
      expect(screen.getByText(/No feedback yet/i)).toBeInTheDocument();
    });
  });
});
