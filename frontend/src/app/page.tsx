"use client";

import { useEffect, useState } from "react";
import { useChatStore } from "../core/store/useChatStore";
import CommandCenter from "../components/CommandCenter";
import AdvisoryFeed from "../components/AdvisoryFeed";
import DiscoveryDeck from "../components/DiscoveryDeck";

export default function Home() {
  const { fetchHistory } = useChatStore();
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

        {/* Advisory Feed Logic (Ticket 1.3) */}
        <AdvisoryFeed />

        {/* Premium Command Center Component */}
        <CommandCenter />
      </aside>

      {/* Right Pane: Discovery Deck */}
      <DiscoveryDeck />
    </main>
  );
}
