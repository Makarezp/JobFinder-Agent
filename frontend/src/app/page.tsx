"use client";

import { useEffect, useState } from "react";
import { useChatStore } from "../core/store/useChatStore";
import { useJobStore } from "../core/store/useJobStore";
import { useProfileStore } from "../core/store/useProfileStore";
import CommandCenter from "../components/CommandCenter";
import AdvisoryFeed from "../components/AdvisoryFeed";
import DiscoveryDeck from "../components/DiscoveryDeck";
import ProfileView from "../components/ProfileView";

export default function Home() {
  const { fetchHistory } = useChatStore();
  const jobs = useJobStore((state) => state.jobs);
  const { fetchProfile } = useProfileStore();
  const [isMounted, setIsMounted] = useState(false);
  const [activeTab, setActiveTab] = useState<"discovery" | "profile">(
    "discovery"
  );

  function handleTabChange(tab: "discovery" | "profile") {
    if (tab === "profile") {
      fetchProfile();
    }
    setActiveTab(tab);
  }

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
    <main className="flex-1 min-h-0 flex overflow-clip relative">
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

      {/* Right Pane: Tabbed Panel */}
      <section className="flex-1 flex flex-col bg-transparent z-10 relative overflow-hidden">
        {/* Tab Bar */}
        <div className="px-8 pt-6 pb-2 border-b border-glass-border flex gap-6 shrink-0">
          <button
            type="button"
            onClick={() => handleTabChange("discovery")}
            className={`pb-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "discovery"
                ? "border-primary text-white"
                : "border-transparent text-slate-400 hover:text-white"
            }`}
          >
            Discovery
          </button>
          <button
            type="button"
            onClick={() => handleTabChange("profile")}
            className={`pb-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "profile"
                ? "border-primary text-white"
                : "border-transparent text-slate-400 hover:text-white"
            }`}
          >
            Profile
          </button>
        </div>

        {/* Match count subtitle — Discovery tab only */}
        {activeTab === "discovery" && jobs.length > 0 && (
          <p className="px-8 pt-3 pb-1 text-slate-400 text-sm shrink-0">
            {`Found ${jobs.length} ${jobs.length === 1 ? "match" : "matches"} based on your criteria.`}
          </p>
        )}

        {/* Tab Content */}
        {activeTab === "discovery" ? <DiscoveryDeck /> : <ProfileView />}
      </section>
    </main>
  );
}
