import { create } from "zustand";
import { Job } from "../types/api";

export interface JobState {
  jobs: Job[];
  setJobs: (jobs: Job[]) => void;
}

export const useJobStore = create<JobState>((set) => ({
  jobs: [],
  setJobs: (jobs) => set({ jobs }),
}));
