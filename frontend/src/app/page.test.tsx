import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import Home from "./page";

vi.mock("../core/store/useChatStore", () => ({
  useChatStore: vi.fn(() => ({
    fetchHistory: vi.fn(),
    isPending: false,
    messages: [],
  })),
}));

vi.mock("../core/store/useJobStore", () => ({
  useJobStore: vi.fn(() => []),
}));

vi.mock("../core/store/useProfileStore", () => ({
  useProfileStore: vi.fn(() => ({
    profile: null,
    preferences: {},
    decisions: [],
    isPending: false,
    fetchProfile: vi.fn(),
  })),
}));

// Stub child components to isolate page-level tab logic
vi.mock("../components/AdvisoryFeed", () => ({
  default: () => <div data-testid="advisory-feed" />,
}));

vi.mock("../components/CommandCenter", () => ({
  default: () => <div data-testid="command-center" />,
}));

vi.mock("../components/DiscoveryDeck", () => ({
  default: () => <div data-testid="discovery-deck" />,
}));

vi.mock("../components/ProfileView", () => ({
  default: () => <div data-testid="profile-view" />,
}));

import { useProfileStore } from "../core/store/useProfileStore";
import { useJobStore } from "../core/store/useJobStore";

describe("Home page — tab system", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useJobStore).mockReturnValue([]);
    vi.mocked(useProfileStore).mockReturnValue({
      profile: null,
      preferences: {},
      decisions: [],
      isPending: false,
      fetchProfile: vi.fn(),
    });
  });

  it("renders the Discovery tab by default", async () => {
    await act(async () => {
      render(<Home />);
    });
    expect(screen.getByTestId("discovery-deck")).toBeInTheDocument();
    expect(screen.queryByTestId("profile-view")).not.toBeInTheDocument();
  });

  it("switches to ProfileView when the Profile tab is clicked", async () => {
    await act(async () => {
      render(<Home />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /profile/i }));
    });

    expect(screen.getByTestId("profile-view")).toBeInTheDocument();
    expect(screen.queryByTestId("discovery-deck")).not.toBeInTheDocument();
  });

  it("calls fetchProfile when the Profile tab is clicked", async () => {
    const mockFetchProfile = vi.fn();
    vi.mocked(useProfileStore).mockReturnValue({
      profile: null,
      preferences: {},
      decisions: [],
      isPending: false,
      fetchProfile: mockFetchProfile,
    });

    await act(async () => {
      render(<Home />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /profile/i }));
    });

    expect(mockFetchProfile).toHaveBeenCalledOnce();
  });

  it("switches back to DiscoveryDeck when Discovery tab is clicked", async () => {
    await act(async () => {
      render(<Home />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /profile/i }));
    });
    expect(screen.getByTestId("profile-view")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /discovery/i }));
    });
    expect(screen.getByTestId("discovery-deck")).toBeInTheDocument();
    expect(screen.queryByTestId("profile-view")).not.toBeInTheDocument();
  });

  it("shows match count subtitle when Discovery tab is active and jobs exist", async () => {
    vi.mocked(useJobStore).mockReturnValue([
      {
        id: "abc",
        title: "Dev",
        company: "Corp",
        location: "Remote",
        salary: null,
        description: "...",
        apply_link: "https://example.com",
      },
      {
        id: "def",
        title: "Dev 2",
        company: "Corp2",
        location: "London",
        salary: null,
        description: "...",
        apply_link: "https://example.com",
      },
    ]);

    await act(async () => {
      render(<Home />);
    });

    expect(screen.getByText(/Found 2 matches/i)).toBeInTheDocument();
  });

  it("does not show match count subtitle when Profile tab is active", async () => {
    vi.mocked(useJobStore).mockReturnValue([
      {
        id: "abc",
        title: "Dev",
        company: "Corp",
        location: "Remote",
        salary: null,
        description: "...",
        apply_link: "https://example.com",
      },
    ]);

    await act(async () => {
      render(<Home />);
    });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /profile/i }));
    });

    expect(screen.queryByText(/Found 1 match/i)).not.toBeInTheDocument();
  });
});
