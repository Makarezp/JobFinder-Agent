"use client";

import { useState } from "react";
import { Job } from "../core/types/api";
import { useJobStore } from "../core/store/useJobStore";

interface JobCardProps {
  job: Job;
}

export default function JobCard({ job }: JobCardProps) {
  const [showReasonInput, setShowReasonInput] = useState(false);
  const [reason, setReason] = useState("");

  function handlePassClick() {
    setShowReasonInput(true);
  }

  function handleSkip() {
    useJobStore.getState().submitFeedback(job, "pass", null);
    setShowReasonInput(false);
  }

  function handleSubmit() {
    useJobStore.getState().submitFeedback(job, "pass", reason.trim() || null);
    setShowReasonInput(false);
  }

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
        <p className="text-sm text-slate-400 line-clamp-4">{job.description}</p>
      </div>

      {/* Action Buttons */}
      <div className="flex gap-3 mt-auto pt-1">
        <button
          type="button"
          onClick={handlePassClick}
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

      {/* Inline Reason Input */}
      {showReasonInput && (
        <div className="flex gap-2 items-center pt-1">
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why? (optional)"
            className="flex-1 bg-surface-dark/50 border border-glass-border rounded-lg px-3 py-1.5 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-primary/50"
          />
          <button
            type="button"
            onClick={handleSkip}
            className="text-xs text-slate-400 hover:text-white px-2 py-1.5 rounded-lg hover:bg-white/5 transition-all"
          >
            Skip
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            className="text-xs text-primary hover:text-white px-2 py-1.5 rounded-lg hover:bg-primary/20 transition-all font-medium"
          >
            Submit
          </button>
        </div>
      )}
    </div>
  );
}
