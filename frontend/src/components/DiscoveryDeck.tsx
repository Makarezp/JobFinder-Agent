"use client";

import { useJobStore } from "../core/store/useJobStore";
import JobCard from "./JobCard";

export default function DiscoveryDeck() {
  const jobs = useJobStore((state) => state.jobs);

  return (
    <section className="flex-1 flex flex-col bg-transparent z-10 relative overflow-hidden">
      {/* Content Area */}
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
    </section>
  );
}
