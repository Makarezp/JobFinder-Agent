"use client";

import { Job } from "../core/types/api";

interface JobCardProps {
  job: Job;
}

export default function JobCard({ job }: JobCardProps) {
  return (
    <div className="glass-panel rounded-2xl p-6 flex flex-col gap-4 group hover:bg-surface-dark/80 transition-all duration-300">
      {/* Header: Logo placeholder + Title + Company */}
      <div className="flex justify-between items-start mt-2">
        <div className="flex gap-4">
          <div className="size-14 rounded-xl bg-slate-800 flex items-center justify-center p-2 shadow-sm shrink-0">
            <span className="material-symbols-outlined text-slate-400 text-3xl">
              work
            </span>
          </div>
          <div>
            <h3 className="text-lg font-bold text-white group-hover:text-primary transition-colors">
              {job.title}
            </h3>
            <p className="text-slate-400 text-sm font-medium">{job.company}</p>
          </div>
        </div>
      </div>

      {/* Pill Badges: Location and Salary */}
      <div className="flex flex-wrap gap-2">
        <span
          data-testid="location-pill"
          className="px-2.5 py-1 rounded-md bg-surface-dark border border-glass-border text-xs text-slate-300 flex items-center gap-1"
        >
          <span className="material-symbols-outlined text-[12px] text-slate-400">
            location_on
          </span>
          {job.location}
        </span>

        {job.salary !== null && (
          <span
            data-testid="salary-pill"
            className="px-2.5 py-1 rounded-md bg-surface-dark border border-glass-border text-xs text-slate-300 flex items-center gap-1"
          >
            <span className="material-symbols-outlined text-[12px] text-slate-400">
              payments
            </span>
            {job.salary}
          </span>
        )}
      </div>

      {/* Description */}
      <div className="py-3 border-t border-glass-border">
        <p className="text-sm text-slate-400 line-clamp-2">{job.description}</p>
      </div>

      {/* Action Buttons */}
      <div className="flex gap-3 mt-auto pt-1">
        <button
          type="button"
          className="flex-1 py-2.5 rounded-lg border border-slate-600 text-slate-300 font-medium text-sm hover:border-slate-400 hover:text-white hover:bg-white/5 transition-all"
        >
          Pass
        </button>
        <a
          href={job.apply_link}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 py-2.5 rounded-lg bg-primary text-white font-bold text-sm shadow-lg shadow-primary/25 hover:bg-primary-hover hover:shadow-primary/40 transition-all flex items-center justify-center gap-2"
        >
          Pursue{" "}
          <span className="material-symbols-outlined text-sm">
            arrow_forward
          </span>
        </a>
      </div>
    </div>
  );
}
