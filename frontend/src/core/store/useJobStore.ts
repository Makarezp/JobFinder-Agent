import { create } from "zustand";
import { Job } from "../types/api";
import { fetchDeckRequest, submitFeedbackRequest } from "../api/profile";
import { useProfileStore } from "./useProfileStore";

export interface JobState {
  jobs: Job[];
  isLoading: boolean;
  error: string | null;
  fetchDeck: () => Promise<void>;
  submitFeedback: (
    job: Job,
    action: "pass" | "pursue",
    reason: string | null
  ) => Promise<void>;
}

export const useJobStore = create<JobState>((set) => ({
  jobs: [],
  isLoading: false,
  error: null,

  fetchDeck: async () => {
    set({ isLoading: true, error: null });
    try {
      const jobs = await fetchDeckRequest();
      set({ jobs });
    } catch (error) {
      console.error("Failed to fetch deck:", error);
      set({ error: "Failed to load jobs. Please try again." });
    } finally {
      set({ isLoading: false });
    }
  },

  submitFeedback: async (job, action, reason) => {
    // Optimistic removal — irreversible by design
    set((state) => ({ jobs: state.jobs.filter((j) => j.id !== job.id) }));

    try {
      await submitFeedbackRequest({
        job_title: job.title,
        company: job.company,
        action,
        reason,
        job_id: job.id,
      });
      await useProfileStore.getState().fetchProfile();
    } catch (error) {
      console.error("Failed to submit feedback:", error);
    }
  },
}));
