"use client";

import { useState } from "react";
import { Job } from "../core/types/api";

interface JobProfileProps {
  job: Job;
  onPass: (job: Job, reason: string | null) => void;
}

export default function JobProfile({ job, onPass }: JobProfileProps) {
  const [showReasonInput, setShowReasonInput] = useState(false);
  const [reason, setReason] = useState("");

  function handlePassClick() {
    setShowReasonInput(true);
  }

  function handleSkip() {
    onPass(job, null);
    setShowReasonInput(false);
    setReason("");
  }

  function handleSubmit() {
    onPass(job, reason.trim() || null);
    setShowReasonInput(false);
    setReason("");
  }

  return (
    <div className="relative glass-panel glow-card rounded-2xl flex flex-col overflow-hidden h-full">
      {/* Sticky Header */}
      <div className="shrink-0 p-8 pb-4 border-b border-glass-border bg-surface-dark/50 backdrop-blur">
        <div className="flex gap-5 items-start">
          {/* Logo placeholder */}
          <div className="size-20 rounded-2xl bg-slate-800 flex items-center justify-center shrink-0">
            <span className="material-symbols-outlined text-4xl text-slate-400">
              work
            </span>
          </div>
          {/* Title block */}
          <div>
            <h3 className="text-3xl font-bold text-white">{job.title}</h3>
            <p className="text-lg text-slate-300 mt-1">
              {job.company} · {job.location}
            </p>
            {job.salary !== null && (
              <span className="inline-flex items-center gap-1 mt-2 text-sm text-slate-400">
                <span className="material-symbols-outlined text-base">
                  payments
                </span>
                {job.salary}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Scrollable Body */}
      <div className="flex-1 overflow-y-auto custom-scroll p-8 pb-24 space-y-6 scroll-mask">
        {/* Short description */}
        <div>
          <h4 className="text-lg font-semibold text-white mb-2">Overview</h4>
          <p className="text-slate-300 leading-relaxed">{job.description}</p>
        </div>

        {/* Full description — only when present */}
        {job.full_description && (
          <div className="pt-4 border-t border-glass-border">
            <h4 className="text-lg font-semibold text-white mb-2">
              Full Description
            </h4>
            <div className="text-slate-300 leading-relaxed whitespace-pre-wrap">
              {job.full_description}
            </div>
          </div>
        )}
      </div>

      {/* Reason input — shown above action bar when Pass is clicked */}
      {showReasonInput && (
        <div className="px-6 pb-2 flex gap-2 items-center">
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

      {/* Floating Action Bar */}
      <div className="absolute bottom-8 left-1/2 -translate-x-1/2 w-[calc(100%-4rem)] max-w-lg z-40">
        <div className="floating-action-bar rounded-2xl p-2 flex gap-3">
          <button
            type="button"
            onClick={handlePassClick}
            className="flex-1 py-2.5 rounded-xl border border-slate-600 text-slate-300 font-medium text-sm hover:border-slate-400 hover:text-white hover:bg-white/5 transition-all flex items-center justify-center gap-2"
          >
            <span className="material-symbols-outlined text-base">close</span>
            Pass
          </button>
          <a
            href={job.apply_link}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 py-2.5 rounded-xl bg-primary text-white font-bold text-sm shadow-lg shadow-primary/25 hover:bg-primary-hover hover:shadow-primary/40 transition-all flex items-center justify-center gap-2"
          >
            Pursue
            <span className="material-symbols-outlined text-base">
              arrow_forward
            </span>
          </a>
        </div>
      </div>
    </div>
  );
}
