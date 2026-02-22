"use client";

import { useJobStore } from "../core/store/useJobStore";
import JobCard from "./JobCard";

export default function DiscoveryDeck() {
  const jobs = useJobStore((state) => state.jobs);

  return (
    <section className="flex-1 flex flex-col bg-transparent z-10 relative overflow-hidden">
      {/* Header */}
      <div className="px-8 py-6 flex justify-between items-end shrink-0">
        <div>
          <h2 className="text-2xl font-bold text-white tracking-tight">
            Discovery Deck
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            {jobs.length === 0
              ? "Chat with the Navigator to find your next role."
              : `Found ${jobs.length} ${jobs.length === 1 ? "match" : "matches"} based on your criteria.`}
          </p>
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto custom-scroll px-8 pb-8">
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
              <JobCard key={`${job.company}-${job.title}`} job={job} />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
