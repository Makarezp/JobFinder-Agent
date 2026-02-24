"use client";

import { Job } from "../core/types/api";

interface JobProfileProps {
  job: Job;
  onPass: (job: Job, reason: string | null) => void;
}

// Stub — replaced in Ticket 5.5
export default function JobProfile({ job }: JobProfileProps) {
  return (
    <div
      data-testid="job-profile-stub"
      className="glass-panel glow-card rounded-2xl h-full flex items-center justify-center"
    >
      <p className="text-white text-xl font-bold">{job.title}</p>
    </div>
  );
}
