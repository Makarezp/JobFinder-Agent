import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import DiscoveryDeck from "./DiscoveryDeck";
import { Job } from "../core/types/api";

// Mock useJobStore so we can control the jobs state in tests
vi.mock("../core/store/useJobStore", () => ({
  useJobStore: vi.fn(),
}));

import { useJobStore, JobState } from "../core/store/useJobStore";

const mockJob1: Job = {
  id: "aabbcc112233",
  title: "Senior Backend Engineer",
  company: "TechFlow",
  location: "Remote",
  salary: "£85k - £110k",
  description: "Leading the backend migration team.",
  full_description: null,
  apply_link: "https://example.com/apply/1",
};

const mockJob2: Job = {
  id: "ddeeff445566",
  title: "Python Architect",
  company: "DataCorp",
  location: "London (Hybrid)",
  salary: "£95k - £120k",
  description: "High-scale data ingestion systems architecture.",
  full_description: null,
  apply_link: "https://example.com/apply/2",
};

function mockStoreWith(
  jobs: Job[],
  isLoading = false,
  error: string | null = null
) {
  vi.mocked(useJobStore).mockImplementation(
    (selector: (s: JobState) => unknown) => {
      const state = {
        jobs,
        isLoading,
        error,
        fetchDeck: vi.fn(),
        submitFeedback: vi.fn(),
      };
      return selector(state);
    }
  );
}

describe("DiscoveryDeck", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the empty state when there are no jobs", () => {
    mockStoreWith([]);
    render(<DiscoveryDeck />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText(/No jobs discovered yet/i)).toBeInTheDocument();
  });

  it("renders job cards when jobs are present", () => {
    mockStoreWith([mockJob1, mockJob2]);
    render(<DiscoveryDeck />);
    expect(screen.getByText("Senior Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText("Python Architect")).toBeInTheDocument();
  });

  it("does not show empty state when jobs are present", () => {
    mockStoreWith([mockJob1]);
    render(<DiscoveryDeck />);
    expect(screen.queryByTestId("empty-state")).not.toBeInTheDocument();
  });
});
