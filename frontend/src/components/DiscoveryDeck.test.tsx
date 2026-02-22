import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import DiscoveryDeck from "./DiscoveryDeck";
import { Job } from "../core/types/api";

// Mock useJobStore so we can control the jobs state in tests
vi.mock("../core/store/useJobStore", () => ({
  useJobStore: vi.fn(),
}));

import { useJobStore } from "../core/store/useJobStore";

const mockJob1: Job = {
  title: "Senior Backend Engineer",
  company: "TechFlow",
  location: "Remote",
  salary: "£85k - £110k",
  description: "Leading the backend migration team.",
  apply_link: "https://example.com/apply/1",
};

const mockJob2: Job = {
  title: "Python Architect",
  company: "DataCorp",
  location: "London (Hybrid)",
  salary: "£95k - £120k",
  description: "High-scale data ingestion systems architecture.",
  apply_link: "https://example.com/apply/2",
};

describe("DiscoveryDeck", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the empty state when there are no jobs", () => {
    vi.mocked(useJobStore).mockReturnValue([]);
    render(<DiscoveryDeck />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText(/No jobs discovered yet/i)).toBeInTheDocument();
  });

  it("renders the correct subtitle in the empty state", () => {
    vi.mocked(useJobStore).mockReturnValue([]);
    render(<DiscoveryDeck />);
    expect(screen.getByText(/Chat with the Navigator/i)).toBeInTheDocument();
  });

  it("renders job cards when jobs are present", () => {
    vi.mocked(useJobStore).mockReturnValue([mockJob1, mockJob2]);
    render(<DiscoveryDeck />);
    expect(screen.getByText("Senior Backend Engineer")).toBeInTheDocument();
    expect(screen.getByText("Python Architect")).toBeInTheDocument();
  });

  it("does not show empty state when jobs are present", () => {
    vi.mocked(useJobStore).mockReturnValue([mockJob1]);
    render(<DiscoveryDeck />);
    expect(screen.queryByTestId("empty-state")).not.toBeInTheDocument();
  });

  it("displays the correct match count in the subtitle", () => {
    vi.mocked(useJobStore).mockReturnValue([mockJob1, mockJob2]);
    render(<DiscoveryDeck />);
    expect(screen.getByText(/Found 2 matches/i)).toBeInTheDocument();
  });

  it("uses singular 'match' for a single job", () => {
    vi.mocked(useJobStore).mockReturnValue([mockJob1]);
    render(<DiscoveryDeck />);
    expect(screen.getByText(/Found 1 match/i)).toBeInTheDocument();
  });
});
