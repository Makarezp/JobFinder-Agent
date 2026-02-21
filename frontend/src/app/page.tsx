"use client";

import { useEffect, useState, useRef } from "react";
import { useChatStore } from "../core/store/useChatStore";

export default function Home() {
  const { messages, isPending, fetchHistory, sendMessage, uploadCV } =
    useChatStore();
  const [inputText, setInputText] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isMounted, setIsMounted] = useState(false);

  // Hydrate history on mount and avoid SSR hydration mismatch
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsMounted(true);
    fetchHistory();
  }, [fetchHistory]);

  if (!isMounted) {
    return (
      <main className="flex-1 flex items-center justify-center">
        <h1 className="text-xl text-slate-400">Loading Assistant...</h1>
      </main>
    );
  }

  const handleSend = () => {
    if (!inputText.trim() || isPending) return;
    sendMessage(inputText);
    setInputText("");
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || isPending) return;
    uploadCV(file);
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <main className="flex-1 flex overflow-hidden relative">
      {/* Background Ambient Glow */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-primary/20 blur-[120px] rounded-full pointer-events-none z-0" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[30%] h-[30%] bg-purple-600/10 blur-[100px] rounded-full pointer-events-none z-0" />

      {/* Left Pane: Advisory Feed Wrapper */}
      <aside className="w-full md:w-[380px] lg:w-[420px] flex flex-col border-r border-glass-border bg-surface-dark/40 backdrop-blur-sm z-10 relative">
        <div className="px-6 py-4 border-b border-glass-border flex justify-between items-center">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
            Advisory Feed
          </h2>
          <button className="text-xs text-primary hover:text-white transition-colors font-medium flex items-center gap-1">
            <span className="material-symbols-outlined text-sm">history</span>{" "}
            History
          </button>
        </div>

        {/* Temporary Sprint 0 Code (Will be replaced in Ticket 1.2/1.3) */}
        <div className="flex-1 overflow-y-auto p-6 text-sm text-slate-200">
          {messages.length === 0 ? (
            <p className="text-slate-500 italic">No messages yet.</p>
          ) : (
            <div className="flex flex-col gap-4">
              {messages.map((msg, idx) => (
                <div key={idx} className="bg-glass-dark p-3 rounded-xl">
                  <div>
                    <strong className="text-primary">User:</strong>{" "}
                    {msg.user_message}
                  </div>
                  <div className="mt-2 text-slate-300">
                    <strong>AI:</strong> {msg.ai_message}
                  </div>
                  {msg.jobs && msg.jobs.length > 0 && (
                    <div className="mt-2 text-xs italic text-slate-400">
                      Found {msg.jobs.length} jobs.
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
          {isPending && (
            <p className="mt-4 text-primary animate-pulse">
              Agent is typing...
            </p>
          )}
        </div>

        <div className="p-4 border-t border-glass-border bg-surface-dark/95 backdrop-blur-xl">
          <div className="flex flex-col gap-2">
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              disabled={isPending}
              placeholder="Ask Navigator..."
              className="px-3 py-2 bg-background-dark/50 border border-glass-border rounded text-white"
            />
            <div className="flex gap-2">
              <button
                onClick={handleSend}
                disabled={isPending || !inputText.trim()}
                className="flex-1 bg-primary text-white py-2 rounded hover:bg-primary-hover disabled:opacity-50"
              >
                Send
              </button>
              <input
                type="file"
                accept="application/pdf"
                onChange={handleFileChange}
                disabled={isPending}
                ref={fileInputRef}
                className="text-xs w-48"
              />
            </div>
          </div>
        </div>
      </aside>

      {/* Right Pane: Discovery Deck Wrapper */}
      <section className="flex-1 flex flex-col bg-transparent z-10 relative">
        <div className="px-8 py-6 flex flex-col">
          <h2 className="text-2xl font-bold text-white tracking-tight">
            Discovery Deck
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            Jobs will appear here shortly...
          </p>
        </div>
      </section>
    </main>
  );
}
