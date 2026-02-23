import { create } from "zustand";
import { Job } from "../types/api";
import { submitFeedbackRequest } from "../api/profile";
import { useProfileStore } from "./useProfileStore";

export interface JobState {
  jobs: Job[];
  setJobs: (jobs: Job[]) => void;
  submitFeedback: (
    job: Job,
    action: "pass" | "pursue",
    reason: string | null
  ) => Promise<void>;
}

export const useJobStore = create<JobState>((set) => ({
  jobs: [],
  setJobs: (jobs) => set({ jobs }),

  submitFeedback: async (job, action, reason) => {
    // Optimistic removal — irreversible by design
    set((state) => ({ jobs: state.jobs.filter((j) => j.id !== job.id) }));

    try {
      await submitFeedbackRequest({
        job_title: job.title,
        company: job.company,
        action,
        description: job.description ?? null,
        reason,
      });
      await useProfileStore.getState().fetchProfile();
    } catch (error) {
      console.error("Failed to submit feedback:", error);
    }
  },
}));
