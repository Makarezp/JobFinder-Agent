import { act, renderHook } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useJobStore } from "./useJobStore";

describe("useJobStore", () => {
  it("should initialize with an empty jobs array", () => {
    const { result } = renderHook(() => useJobStore());
    expect(result.current.jobs).toEqual([]);
  });

  it("should set jobs correctly", () => {
    const { result } = renderHook(() => useJobStore());

    const mockJobs = [
      {
        title: "Software Engineer",
        company: "Tech Corp",
        location: "Remote",
        salary: "100k - 150k",
        description: "Great job",
        apply_link: "https://example.com",
      },
    ];

    act(() => {
      result.current.setJobs(mockJobs);
    });

    expect(result.current.jobs).toEqual(mockJobs);
  });
});
