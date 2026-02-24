"use client";

import { useState } from "react";
import { useJobStore } from "../core/store/useJobStore";
import { Job } from "../core/types/api";
import JobProfile from "./JobProfile";

export default function DiscoveryDeck() {
  const jobs = useJobStore((state) => state.jobs);
  const isLoading = useJobStore((state) => state.isLoading);
  const error = useJobStore((state) => state.error);

  const [currentIndex, setCurrentIndex] = useState(0);
  const [passedIds, setPassedIds] = useState<Set<string>>(new Set());

  const visibleJobs = jobs.filter((j) => !passedIds.has(j.id));
  const currentJob = visibleJobs[currentIndex] ?? null;

  function goNext() {
    setCurrentIndex((i) => Math.min(i + 1, visibleJobs.length - 1));
  }

  function goPrev() {
    setCurrentIndex((i) => Math.max(i - 1, 0));
  }

  function handlePass(job: Job, reason: string | null) {
    setPassedIds((prev) => new Set(prev).add(job.id));
    setCurrentIndex((i) => Math.max(0, Math.min(i, visibleJobs.length - 2)));
    useJobStore.getState().submitFeedback(job, "pass", reason);
  }

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

  const atStart = currentIndex === 0;
  const atEnd = currentIndex >= visibleJobs.length - 1;

  return (
    <section className="flex-1 flex items-center justify-center overflow-hidden">
      {/* Left nav gutter — flex sibling, always adjacent to the card */}
      <div
        className={`shrink-0 w-20 h-full flex items-center justify-center nav-gutter group select-none ${atStart ? "pointer-events-none opacity-30" : "cursor-pointer"}`}
        onClick={goPrev}
      >
        <div className="h-32 w-12 rounded-full glass-panel flex items-center justify-center border border-white/10 group-hover:border-primary/40 transition-all duration-300">
          <span className="material-symbols-outlined text-4xl text-slate-400 group-hover:text-white transition-colors">
            chevron_left
          </span>
        </div>
      </div>

      {/* Main profile card */}
      <div className="flex-1 max-w-4xl h-full max-h-[85vh]">
        {currentJob ? (
          <JobProfile job={currentJob} onPass={handlePass} />
        ) : (
          <div
            data-testid="empty-state"
            className="h-full flex flex-col items-center justify-center opacity-40 text-center px-4"
          >
            <span className="material-symbols-outlined text-6xl mb-4">
              smart_toy
            </span>
            <p className="text-sm italic max-w-xs">
              You&apos;re all caught up. Ask the navigator to find more.
            </p>
          </div>
        )}
      </div>

      {/* Right nav gutter — flex sibling, always adjacent to the card */}
      <div
        className={`shrink-0 w-20 h-full flex items-center justify-center nav-gutter right group select-none ${atEnd ? "pointer-events-none opacity-30" : "cursor-pointer"}`}
        onClick={goNext}
      >
        <div className="h-32 w-12 rounded-full glass-panel flex items-center justify-center border border-white/10 group-hover:border-primary/40 transition-all duration-300">
          <span className="material-symbols-outlined text-4xl text-slate-400 group-hover:text-white transition-colors">
            chevron_right
          </span>
        </div>
      </div>
    </section>
  );
}
