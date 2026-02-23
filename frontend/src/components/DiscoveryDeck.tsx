"use client";

import { useJobStore } from "../core/store/useJobStore";
import JobCard from "./JobCard";

export default function DiscoveryDeck() {
  const jobs = useJobStore((state) => state.jobs);
  const isLoading = useJobStore((state) => state.isLoading);
  const error = useJobStore((state) => state.error);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center opacity-60">
        <span className="material-symbols-outlined animate-spin text-4xl">
          progress_activity
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center opacity-60 text-center px-4">
        <p className="text-sm text-red-400">{error}</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto custom-scroll px-8 pb-8 pt-4">
      {jobs.length === 0 ? (
        /* Empty State */
        <div
          data-testid="empty-state"
          className="h-full flex flex-col items-center justify-center opacity-40 text-center px-4"
        >
          <span className="material-symbols-outlined text-6xl mb-4">
            work_outline
          </span>
          <p className="text-sm italic max-w-xs">
            No jobs discovered yet. Ask the Navigator to search for roles.
          </p>
        </div>
      ) : (
        /* Job Grid */
        <div className="grid grid-cols-1 xl:grid-cols-2 2xl:grid-cols-3 gap-6">
          {jobs.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </div>
  );
}
