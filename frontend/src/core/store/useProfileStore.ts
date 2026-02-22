import { create } from "zustand";
import { DecisionLogEntry, Preference, ProfileResponse } from "../types/api";
import { fetchProfileRequest } from "../api/profile";

interface ProfileState {
  profile: ProfileResponse["profile"] | null;
  preferences: Record<string, Preference>;
  decisions: DecisionLogEntry[];
  isPending: boolean;
  fetchProfile: () => Promise<void>;
}

export const useProfileStore = create<ProfileState>((set) => ({
  profile: null,
  preferences: {},
  decisions: [],
  isPending: false,

  fetchProfile: async () => {
    set({ isPending: true });
    try {
      const data = await fetchProfileRequest();
      set({
        profile: data.profile,
        preferences: data.preferences,
        decisions: data.decisions,
      });
    } catch (error) {
      console.error("Failed to fetch profile:", error);
    } finally {
      set({ isPending: false });
    }
  },
}));
