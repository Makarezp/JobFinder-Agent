import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import JobCard from "./JobCard";
import { Job } from "../core/types/api";

const mockJob: Job = {
  id: "abc123def456",
  title: "Senior Backend Engineer",
  company: "TechFlow",
  location: "Remote",
  salary: "£85k - £110k",
  description:
    "Leading the backend migration team. This role offers a direct path to Staff Engineer.",
  apply_link: "https://example.com/apply",
};

describe("JobCard", () => {
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

  it("renders the description with line-clamp-2 class for truncation", () => {
    render(<JobCard job={mockJob} />);
    const description = screen.getByText(mockJob.description);
    expect(description).toHaveClass("line-clamp-2");
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
});
