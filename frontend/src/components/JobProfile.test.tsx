import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import JobProfile from "./JobProfile";
import { Job } from "../core/types/api";

const mockJob: Job = {
  id: "job-001",
  title: "Senior ML Engineer",
  company: "Acme AI",
  location: "London, UK",
  salary: "£90k - £120k",
  description: "Build and deploy ML pipelines at scale.",
  full_description: "Full scraped description with lots of detail.",
  apply_link: "https://example.com/apply/1",
};

describe("JobProfile", () => {
  it("renders title, company, and location", () => {
    render(<JobProfile job={mockJob} onPass={vi.fn()} />);
    expect(screen.getByText("Senior ML Engineer")).toBeInTheDocument();
    expect(screen.getByText(/Acme AI/)).toBeInTheDocument();
    expect(screen.getByText(/London, UK/)).toBeInTheDocument();
  });

  it("renders salary when job.salary is not null", () => {
    render(<JobProfile job={mockJob} onPass={vi.fn()} />);
    expect(screen.getByText("£90k - £120k")).toBeInTheDocument();
  });

  it("does not render salary when job.salary is null", () => {
    render(<JobProfile job={{ ...mockJob, salary: null }} onPass={vi.fn()} />);
    expect(screen.queryByText(/£/)).not.toBeInTheDocument();
  });

  it("renders full description section when job.full_description is not null", () => {
    render(<JobProfile job={mockJob} onPass={vi.fn()} />);
    expect(screen.getByText("Full Description")).toBeInTheDocument();
    expect(
      screen.getByText("Full scraped description with lots of detail.")
    ).toBeInTheDocument();
  });

  it("does not render full description section when job.full_description is null", () => {
    render(
      <JobProfile
        job={{ ...mockJob, full_description: null }}
        onPass={vi.fn()}
      />
    );
    expect(screen.queryByText("Full Description")).not.toBeInTheDocument();
  });

  it("clicking Pass shows the reason input", () => {
    render(<JobProfile job={mockJob} onPass={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /pass/i }));
    expect(
      screen.getByPlaceholderText(/why\? \(optional\)/i)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /skip/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /submit/i })).toBeInTheDocument();
  });

  it("clicking Skip calls onPass(job, null)", () => {
    const onPass = vi.fn();
    render(<JobProfile job={mockJob} onPass={onPass} />);
    fireEvent.click(screen.getByRole("button", { name: /pass/i }));
    fireEvent.click(screen.getByRole("button", { name: /skip/i }));
    expect(onPass).toHaveBeenCalledWith(mockJob, null);
  });

  it("clicking Submit with a reason calls onPass(job, reason)", () => {
    const onPass = vi.fn();
    render(<JobProfile job={mockJob} onPass={onPass} />);
    fireEvent.click(screen.getByRole("button", { name: /pass/i }));
    fireEvent.change(screen.getByPlaceholderText(/why\? \(optional\)/i), {
      target: { value: "Not remote" },
    });
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));
    expect(onPass).toHaveBeenCalledWith(mockJob, "Not remote");
  });

  it("Pursue link has correct href and target", () => {
    render(<JobProfile job={mockJob} onPass={vi.fn()} />);
    const link = screen.getByRole("link", { name: /pursue/i });
    expect(link).toHaveAttribute("href", "https://example.com/apply/1");
    expect(link).toHaveAttribute("target", "_blank");
  });
});
