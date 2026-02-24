import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import JobCard from "./JobCard";
import { Job } from "../core/types/api";

vi.mock("../core/store/useJobStore", () => ({
  useJobStore: {
    getState: vi.fn(() => ({ submitFeedback: vi.fn() })),
  },
}));

import { useJobStore } from "../core/store/useJobStore";

const mockJob: Job = {
  id: "abc123def456",
  title: "Senior Backend Engineer",
  company: "TechFlow",
  location: "Remote",
  salary: "£85k - £110k",
  description:
    "Leading the backend migration team. This role offers a direct path to Staff Engineer.",
  full_description: null,
  apply_link: "https://example.com/apply",
};

describe("JobCard", () => {
  beforeEach(() => {
    vi.mocked(useJobStore.getState).mockReturnValue({
      submitFeedback: vi.fn(),
      jobs: [],
      isLoading: false,
      error: null,
      fetchDeck: vi.fn(),
    });
  });

  it("renders the job title", () => {
    render(<JobCard job={mockJob} />);
    expect(screen.getByText("Senior Backend Engineer")).toBeInTheDocument();
  });

  it("renders the company name", () => {
    render(<JobCard job={mockJob} />);
    expect(screen.getByText("TechFlow")).toBeInTheDocument();
  });

  it("renders the location pill", () => {
    render(<JobCard job={mockJob} />);
    const locationPill = screen.getByTestId("location-pill");
    expect(locationPill).toBeInTheDocument();
    expect(locationPill).toHaveTextContent("Remote");
  });

  it("renders the salary pill when salary is provided", () => {
    render(<JobCard job={mockJob} />);
    const salaryPill = screen.getByTestId("salary-pill");
    expect(salaryPill).toBeInTheDocument();
    expect(salaryPill).toHaveTextContent("£85k - £110k");
  });

  it("does not render the salary pill when salary is null", () => {
    const jobWithoutSalary: Job = { ...mockJob, salary: null };
    render(<JobCard job={jobWithoutSalary} />);
    expect(screen.queryByTestId("salary-pill")).not.toBeInTheDocument();
  });

  it("renders the description with line-clamp-4 class for truncation", () => {
    render(<JobCard job={mockJob} />);
    const description = screen.getByText(mockJob.description);
    expect(description).toHaveClass("line-clamp-4");
  });

  it("renders the Pursue button as a link to apply_link", () => {
    render(<JobCard job={mockJob} />);
    const pursueLink = screen.getByRole("link", { name: /pursue/i });
    expect(pursueLink).toHaveAttribute("href", "https://example.com/apply");
    expect(pursueLink).toHaveAttribute("target", "_blank");
    expect(pursueLink).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders the Pass button", () => {
    render(<JobCard job={mockJob} />);
    expect(screen.getByRole("button", { name: /pass/i })).toBeInTheDocument();
  });

  it("shows the reason input after clicking Pass", () => {
    render(<JobCard job={mockJob} />);
    fireEvent.click(screen.getByRole("button", { name: /pass/i }));
    expect(
      screen.getByPlaceholderText(/why\? \(optional\)/i)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /skip/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit/i })).toBeInTheDocument();
  });

  it("calls submitFeedback with null reason when Skip is clicked", () => {
    const mockSubmitFeedback = vi.fn();
    vi.mocked(useJobStore.getState).mockReturnValue({
      submitFeedback: mockSubmitFeedback,
      jobs: [],
      isLoading: false,
      error: null,
      fetchDeck: vi.fn(),
    });

    render(<JobCard job={mockJob} />);
    fireEvent.click(screen.getByRole("button", { name: /pass/i }));
    fireEvent.click(screen.getByRole("button", { name: /skip/i }));

    expect(mockSubmitFeedback).toHaveBeenCalledWith(mockJob, "pass", null);
  });

  it("calls submitFeedback with typed reason when Submit is clicked", () => {
    const mockSubmitFeedback = vi.fn();
    vi.mocked(useJobStore.getState).mockReturnValue({
      submitFeedback: mockSubmitFeedback,
      jobs: [],
      isLoading: false,
      error: null,
      fetchDeck: vi.fn(),
    });

    render(<JobCard job={mockJob} />);
    fireEvent.click(screen.getByRole("button", { name: /pass/i }));
    fireEvent.change(screen.getByPlaceholderText(/why\? \(optional\)/i), {
      target: { value: "Too much legacy code" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));

    expect(mockSubmitFeedback).toHaveBeenCalledWith(
      mockJob,
      "pass",
      "Too much legacy code"
    );
  });
});
