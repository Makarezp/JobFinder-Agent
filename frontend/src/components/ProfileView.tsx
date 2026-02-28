"use client";

import { useProfileStore } from "../core/store/useProfileStore";
import { useChatStore } from "../core/store/useChatStore";
import { Preference, DecisionLogEntry } from "../core/types/api";

function IdentityCard({
  profile,
}: {
  profile: NonNullable<ReturnType<typeof useProfileStore.getState>["profile"]>;
}) {
  return (
    <div className="glass-panel rounded-2xl p-6 flex flex-col gap-4">
      <div className="flex items-center gap-4">
        <div className="size-20 rounded-full bg-gradient-to-br from-primary to-purple-600 shrink-0" />
        <div>
          <h3 className="text-xl font-bold text-white">
            {profile.name ?? "Unknown"}
          </h3>
          <p className="text-primary font-medium text-sm">
            {profile.role ?? "Role not set"}
          </p>
        </div>
      </div>

      {profile.cv_summary && (
        <div className="bg-surface-dark/50 border border-glass-border rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="material-symbols-outlined text-sm text-slate-400">
              auto_awesome
            </span>
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              AI Summary
            </span>
          </div>
          <p className="text-sm text-slate-300">{profile.cv_summary}</p>
        </div>
      )}
    </div>
  );
}

function PreferencesCard({
  preferences,
}: {
  preferences: Record<string, Preference>;
}) {
  const sendMessage = useChatStore((state) => state.sendMessage);
  const entries = Object.entries(preferences);
  const positive = entries.filter(([, p]) => p.sentiment === "positive");
  const negative = entries.filter(([, p]) => p.sentiment === "negative");

  return (
    <div className="glass-panel rounded-2xl p-6 flex flex-col gap-4">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
        Search Preferences
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Looking For */}
        <div>
          <div className="flex items-center gap-1.5 mb-3">
            <span className="material-symbols-outlined text-sm text-green-400">
              check_circle
            </span>
            <span className="text-xs font-semibold text-green-400 uppercase tracking-wider">
              Looking For
            </span>
          </div>
          {positive.length === 0 ? (
            <p className="text-xs text-slate-500 italic">None set yet.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {positive.map(([key, pref]) => (
                <li
                  key={key}
                  className="group flex items-center justify-between"
                >
                  <span className="text-sm text-slate-200">{pref.label}</span>
                  <button
                    type="button"
                    onClick={() =>
                      sendMessage(`Remove my preference for "${key}"`)
                    }
                    className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-500 hover:text-red-400"
                    aria-label={`Remove preference ${key}`}
                  >
                    <span className="material-symbols-outlined text-sm">
                      close
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Avoiding */}
        <div>
          <div className="flex items-center gap-1.5 mb-3">
            <span className="material-symbols-outlined text-sm text-red-400">
              cancel
            </span>
            <span className="text-xs font-semibold text-red-400 uppercase tracking-wider">
              Avoiding
            </span>
          </div>
          {negative.length === 0 ? (
            <p className="text-xs text-slate-500 italic">None set yet.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {negative.map(([key, pref]) => (
                <li
                  key={key}
                  className="group flex items-center justify-between"
                >
                  <span className="text-sm text-slate-200">{pref.label}</span>
                  <button
                    type="button"
                    onClick={() =>
                      sendMessage(`Remove my preference for "${key}"`)
                    }
                    className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-500 hover:text-red-400"
                    aria-label={`Remove preference ${key}`}
                  >
                    <span className="material-symbols-outlined text-sm">
                      close
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function DecisionLogCard({ decisions }: { decisions: DecisionLogEntry[] }) {
  return (
    <div className="glass-panel rounded-2xl p-6 flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-sm text-slate-400">
          history
        </span>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Passed Jobs Feedback
        </h3>
      </div>

      {decisions.length === 0 ? (
        <p className="text-sm text-slate-500 italic">
          No feedback yet. Pass or pursue some jobs to see your decision history
          here.
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {decisions.map((entry, i) => (
            <li
              key={`${entry.job_title}-${entry.company}-${i}`}
              className="bg-surface-dark/50 border border-glass-border rounded-xl p-3 flex gap-3"
            >
              <span className="material-symbols-outlined text-slate-400 shrink-0 mt-0.5">
                corporate_fare
              </span>
              <div className="flex flex-col gap-1 min-w-0">
                <p className="text-sm font-semibold text-white truncate">
                  {entry.job_title}{" "}
                  <span className="text-slate-400 font-normal">
                    at {entry.company}
                  </span>
                </p>
                <p className="text-[10px] text-slate-500">
                  {new Date(entry.timestamp).toLocaleDateString()}
                </p>
                {entry.description && (
                  <p className="text-xs text-slate-400 italic">
                    {entry.description}
                  </p>
                )}
                {entry.reason && (
                  <p className="text-sm text-slate-300">
                    &ldquo;
                    <span className="text-indigo-300">{entry.reason}</span>
                    &rdquo;
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ProfileView() {
  const { profile, preferences, decisions, isPending } = useProfileStore();

  if (isPending) {
    return (
      <div
        data-testid="profile-loading"
        className="flex-1 flex items-center justify-center"
      >
        <div className="flex flex-col items-center gap-3 opacity-60">
          <span className="material-symbols-outlined text-4xl animate-spin">
            progress_activity
          </span>
          <p className="text-sm text-slate-400">Loading profile...</p>
        </div>
      </div>
    );
  }

  if (!profile) {
    return (
      <div
        data-testid="profile-empty"
        className="flex-1 flex items-center justify-center px-8"
      >
        <p className="text-center text-slate-400 text-sm max-w-xs">
          I don&apos;t know much about you yet. Upload your CV or tell me about
          yourself in the chat.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto custom-scroll px-8 pb-8 pt-4 flex flex-col gap-6">
      <IdentityCard profile={profile} />
      <PreferencesCard preferences={preferences} />
      <DecisionLogCard decisions={decisions} />
    </div>
  );
}
