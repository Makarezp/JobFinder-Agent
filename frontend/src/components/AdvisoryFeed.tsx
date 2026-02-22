"use client";

import { useEffect, useRef } from "react";
import { useChatStore } from "../core/store/useChatStore";
import ChatMessage from "./ChatMessage";

export default function AdvisoryFeed() {
  const { messages, isPending } = useChatStore();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isPending]);

  return (
    <div className="flex-1 overflow-y-auto custom-scroll p-6 flex flex-col gap-6">
      <div className="flex justify-center">
        <span className="text-[10px] font-medium text-slate-500 bg-surface-dark px-3 py-1 rounded-full border border-glass-border">
          Today
        </span>
      </div>

      {messages.length === 0 && !isPending && (
        <div className="flex-1 flex flex-col items-center justify-center opacity-40 text-center px-4">
          <span className="material-symbols-outlined text-4xl mb-2">forum</span>
          <p className="text-sm italic">
            No advisory history yet. Upload your CV or ask a question to begin.
          </p>
        </div>
      )}

      {messages.map((msg, idx) => (
        <div key={`msg-group-${idx}`} className="flex flex-col gap-6">
          {msg.user_message && (
            <ChatMessage message={{ ...msg, ai_message: "" }} role="user" />
          )}
          {msg.ai_message && msg.ai_message !== "..." && (
            <ChatMessage message={msg} role="ai" />
          )}
        </div>
      ))}

      {isPending && (
        <div className="flex items-start gap-3 opacity-70 animate-pulse">
          <div className="shrink-0 size-8 rounded-full bg-gradient-to-br from-slate-700 to-slate-800 flex items-center justify-center text-slate-400 border border-slate-600">
            <span className="material-symbols-outlined text-sm animate-spin">
              progress_activity
            </span>
          </div>
          <div className="flex items-center h-8">
            <span className="text-xs text-slate-500 italic">Thinking...</span>
          </div>
        </div>
      )}

      <div ref={scrollRef} />
    </div>
  );
}
