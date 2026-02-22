"use client";

import ReactMarkdown from "react-markdown";
import { ChatResponse } from "../core/types/api";

interface ChatMessageProps {
  message: ChatResponse;
  role: "user" | "ai";
}

export default function ChatMessage({ message, role }: ChatMessageProps) {
  const isAi = role === "ai";
  const isError = isAi && message.ai_message.startsWith("**System Error**");

  return (
    <div className={`flex items-start gap-3 ${isAi ? "" : "justify-end"}`}>
      {isAi && (
        <div className="shrink-0 size-8 rounded-full bg-gradient-to-br from-primary to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-primary/20">
          <span className="material-symbols-outlined text-sm">smart_toy</span>
        </div>
      )}

      <div
        className={`flex flex-col gap-1 ${isAi ? "max-w-[85%]" : "items-end max-w-[85%]"}`}
      >
        <span
          className={`text-xs font-medium text-slate-400 ${isAi ? "ml-1" : "mr-1"}`}
        >
          {isAi ? "Navigator AI" : "You"}
        </span>

        <div
          className={`p-3.5 rounded-2xl text-sm leading-relaxed ${
            isAi
              ? isError
                ? "rounded-tl-none bg-red-500/10 border border-red-500/30 text-rose-200"
                : "rounded-tl-none bg-glass-dark border border-glass-border text-slate-200"
              : "rounded-tr-none bg-primary text-white shadow-lg shadow-primary/10"
          }`}
        >
          {isAi ? (
            <div
              className={`prose prose-invert max-w-none text-sm ${isError ? "prose-rose" : "prose-slate"}`}
            >
              <ReactMarkdown>{message.ai_message}</ReactMarkdown>
            </div>
          ) : (
            <p>{message.user_message}</p>
          )}
        </div>

        {isAi && message.jobs && message.jobs.length > 0 && (
          <div className="mt-2 text-[10px] inline-flex items-center gap-1.5 bg-primary/10 text-primary font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border border-primary/20">
            <span className="material-symbols-outlined text-[12px]">
              auto_awesome
            </span>
            Found {message.jobs.length} jobs in Deck
          </div>
        )}
      </div>

      {!isAi && (
        <div className="shrink-0 size-8 rounded-full bg-slate-800 border border-glass-border flex items-center justify-center text-slate-400">
          <span className="material-symbols-outlined text-sm">person</span>
        </div>
      )}
    </div>
  );
}
