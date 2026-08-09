---
status: open
component: agent-tabs / agentctl.py / ItermTabViewer
discovered: 2026-08-08
discovered_via: live usage (two real worktree-isolated agents spawned with --viewer iterm-tab in run "ticket-impl"), not the probe/claims pipeline
severity: high — silently misdirects human input to the wrong agent
---

# ItermTabViewer: all tabs on a run collapse onto the most-recently-selected window

## 1. Summary

`agentctl spawn --viewer iterm-tab` opens a new iTerm tab per agent so a human can watch and type to it directly. Spawning a **second** agent in the same run silently retargets **every previously opened tab in that run** to show the new agent's window too. From the human's point of view, all open tabs for a run appear to show "the same agent" — because, after the second spawn, they genuinely do.

This is not a rendering glitch. It is a real shared-state bug: any text a human types into what they believe is Agent A's tab can land in Agent B's composer instead.

## 2. Root cause

`ItermTabViewer.reveal()` (`agentctl.py:675-706`) opens a new iTerm tab and writes this shell command into it:

```
TMUX= tmux attach -t '<run>' \; select-window -t '<handle>'
```

`tmux attach -t <run>` attaches the new client to the **session** for the run (e.g. `ticket-impl`). `select-window` then changes that session's **current window**.

The bug: a tmux session's "current window" is a single pointer shared by every client attached to that session — it is not per-client. When agent 2 is spawned and its `reveal()` call runs `select-window -t @1284`, it changes the *session's* current window, which immediately changes what **every other already-attached client of that session displays**, including the tab that was opened for agent 1.

Confirmed directly via `tmux list-clients -F "#{client_tty} session=#{client_session} window=#{window_id} #{window_name}"` after spawning `impl-006` (window `@1283`) then `impl-007` (window `@1284`) in run `ticket-impl`:

```
/dev/ttys015 session=ticket-impl window=@1284 impl-007
/dev/ttys022 session=ticket-impl window=@1284 impl-007
```

Both attached clients — the tab opened for `impl-006` and the tab opened for `impl-007` — ended up pointed at `@1284` (impl-007's window). The `impl-006` tab's own reveal had run first and correctly selected `@1283` at the time, but the second spawn's `select-window` call overwrote that for both clients simultaneously.

The same collapse was independently observed on an unrelated run (`ticket-review`, agents `review-006`/`review-007`) opened earlier in the same session — both of its tabs were also found pointed at the same window (`@1278`).

This will keep recurring: every additional agent spawned into an already-open run with `--viewer iterm-tab` re-hijacks all previously opened tabs for that run onto the newest window.

## 3. Why this is worse than a cosmetic bug

The worker protocol (`WORKER.md`) treats direct human typing into an agent's tab as a first-class instruction channel, equivalent to a message routed through the inbox. If a human, looking at a tab they believe belongs to Agent A, types an approval/answer and presses enter, it is delivered to whichever agent tmux's shared current-window pointer actually happens to be showing — which may silently be Agent B.

Observed in the same session: after this collapse occurred, `impl-007`'s composer was found holding unsent draft text — `Yes to both — copy the evidence dirs and use 30 trials.` — typed by the human into a tab they had opened believing it was a different agent's window, while both open tabs for the run were in fact pointed at `impl-007`. Had that been submitted, it would have been indistinguishable from a real, deliberate answer to `impl-007` — with no signal to the human that the tab they thought they were addressing (`impl-006`) never received anything.

## 4. Reproduction

1. `agentctl spawn agent-a --viewer iterm-tab --run demo-run ...` — opens tab A, correctly showing agent-a.
2. `agentctl spawn agent-b --viewer iterm-tab --run demo-run ...` — opens tab B, showing agent-b.
3. Switch back to tab A. It now also shows agent-b, not agent-a.
4. Confirm via `tmux list-clients -F "#{client_tty} window=#{window_id}"` — both clients report the same `window=`.

## 5. Workaround (no code change)

Attach manually from a plain terminal instead of relying on `--viewer iterm-tab`'s auto-opened tabs:

```
tmux attach -t <run>:<window-index-or-name>
```

Each such invocation creates its own client cleanly targeted at that window and is not retargeted by subsequent spawns in the same run — the bug is specifically in `reveal()`'s use of `attach` + `select-window` against a session that already has other clients on it, not in tmux's addressing itself. (`--viewer none` plus manual `tmux attach` for each agent, as done earlier in this session, sidesteps the bug entirely.)

## 6. Suggested fix direction (not yet decided — for human review)

`reveal()` should give each new tab its own independent "current window" view rather than attaching directly to the shared run session. tmux supports this via a **grouped session**: `tmux new-session -t <run> -s <per-agent-session-name>` creates a new session that shares the run's windows and panes but has its own independent current-window pointer, so `select-window` inside it would no longer affect other clients. This would require changing the command `reveal()` writes from a plain `attach` to a grouped `new-session -t`, and would need a decision on session-name collisions/cleanup (grouped sessions accumulate in `tmux list-sessions` and are not cleaned up by `close`/`close-run` today).

This has not been triaged through `probe/claims.jsonl` or `probe/lib/oracle.py` — it was found via direct live usage, not the probe campaign, and carries no claim ID or automated verdict. No changes have been made to `agentctl.py` or any other system-under-test file; this document is purely descriptive, per the probe-operator boundary of not modifying the tool under test without a human decision.
