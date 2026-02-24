import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import DiscoveryDeck from "./DiscoveryDeck";
import { Job } from "../core/types/api";

vi.mock("../core/store/useJobStore", () => ({
  useJobStore: vi.fn(),
}));

vi.mock("./JobProfile", () => ({
  default: ({
    job,
    onPass,
  }: {
    job: Job;
    onPass: (job: Job, reason: string | null) => void;
  }) => (
    <div data-testid="job-profile" data-job-id={job.id}>
      <span>{job.title}</span>
      <button onClick={() => onPass(job, null)}>pass</button>
    </div>
  ),
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

const mockJob3: Job = {
  id: "gghhii778899",
  title: "ML Engineer",
  company: "AILabs",
  location: "London",
  salary: null,
  description: "Train and deploy models.",
  full_description: null,
  apply_link: "https://example.com/apply/3",
};

const mockSubmitFeedback = vi.fn();

function mockStoreWith(
  jobs: Job[],
  isLoading = false,
  error: string | null = null
) {
  vi.mocked(useJobStore).mockImplementation(
    (selector: (s: JobState) => unknown) => {
      const state: JobState = {
        jobs,
        isLoading,
        error,
        fetchDeck: vi.fn(),
        submitFeedback: mockSubmitFeedback,
      };
      return selector(state);
    }
  );
  // Also wire getState for the handlePass submitFeedback call
  vi.mocked(useJobStore).getState = vi.fn(() => ({
    jobs,
    isLoading,
    error,
    fetchDeck: vi.fn(),
    submitFeedback: mockSubmitFeedback,
  }));
}

describe("DiscoveryDeck", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the empty state when there are no jobs and not loading", () => {
    mockStoreWith([]);
    render(<DiscoveryDeck />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText(/all caught up/i)).toBeInTheDocument();
  });

  it("does not show empty state when jobs are present", () => {
    mockStoreWith([mockJob1]);
    render(<DiscoveryDeck />);
    expect(screen.queryByTestId("empty-state")).not.toBeInTheDocument();
  });

  it("shows only the current job card (not all jobs at once)", () => {
    mockStoreWith([mockJob1, mockJob2]);
    render(<DiscoveryDeck />);
    // Only the first job is rendered as the current card
    expect(screen.getByTestId("job-profile")).toHaveAttribute(
      "data-job-id",
      mockJob1.id
    );
    expect(screen.queryByText(mockJob2.title)).not.toBeInTheDocument();
  });

  it("visibleJobs filters out passed job ids — 3 jobs minus 1 passed leaves 2 visible", () => {
    mockStoreWith([mockJob1, mockJob2, mockJob3]);
    render(<DiscoveryDeck />);

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /pass/i }));
    });

    // After passing job1, job2 should now be the current card
    expect(screen.getByTestId("job-profile")).toHaveAttribute(
      "data-job-id",
      mockJob2.id
    );
  });

  it("handlePass adds the job id to passedIds and calls submitFeedback", () => {
    mockStoreWith([mockJob1, mockJob2]);
    render(<DiscoveryDeck />);

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /pass/i }));
    });

    expect(mockSubmitFeedback).toHaveBeenCalledWith(mockJob1, "pass", null);
    // job1 is gone, job2 is now visible
    expect(screen.getByTestId("job-profile")).toHaveAttribute(
      "data-job-id",
      mockJob2.id
    );
  });

  it("currentIndex is 0 (not -1) after passing the last remaining job", () => {
    mockStoreWith([mockJob1]);
    render(<DiscoveryDeck />);

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /pass/i }));
    });

    // After passing the last job, empty state should appear (not a crash / undefined render)
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });
});
