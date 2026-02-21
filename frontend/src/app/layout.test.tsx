import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import RootLayout from "./layout";

// Mock next/font if used, or other next features
vi.mock("next/font/google", () => ({
  Inter: () => ({ className: "inter-font" }),
}));

// Mock metadata because it can't be rendered in a component test easily
vi.mock("next", () => ({
  Metadata: {},
}));

describe("RootLayout", () => {
  it("renders the layout with header and navigation", () => {
    // We need to provide the children
    render(
      <RootLayout>
        <div data-testid="children">Content</div>
      </RootLayout>
    );

    // Check for premium header elements
    expect(screen.getByText("CVviewer")).toBeInTheDocument();
    expect(screen.getByText("Searching...")).toBeInTheDocument();
    expect(screen.getByText("notifications")).toBeInTheDocument(); // Material icon text

    // Check for children
    expect(screen.getByTestId("children")).toBeInTheDocument();
  });
});
