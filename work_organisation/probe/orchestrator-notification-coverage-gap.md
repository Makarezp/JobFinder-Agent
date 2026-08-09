---
status: open
component: orchestration process (how the orchestrating agent uses `agentctl wait`), not agentctl.py itself
discovered: 2026-08-08
discovered_via: live usage — human asked "why didn't you report back" about two agents whose questions had been sitting unread
severity: high — a human-facing agent can go silent on a real blocking question with no signal that anything is wrong
root_cause: confirmed — see Section 2
---

# Orchestrator "lost" notifications: `agentctl wait` is one-shot and run-scoped, not a standing subscription

## 1. Summary

While orchestrating multiple concurrent agent-tabs runs (`ticket-review`, `ticket-impl`, `ticket-itermbug`, `ticket008-review`), two agents (`impl-006`, `impl-007`, both in run `ticket-impl`) sent `question` events and sat in `awaiting_human` state for ~7-16 minutes with no report reaching the human — discovered only when the human asked directly why there'd been no update. Nothing was actually lost: `bus.jsonl` is an append-only log and both events were sitting in it the whole time, immediately visible via `status`/`read`. The gap was that no `agentctl wait` call was running against the `ticket-impl` run during that window — the only active `wait` was watching a *different* run (`ticket-itermbug`) for a *different* agent's reply.

## 2. Root cause

`agentctl wait --until <predicate> --timeout <t>` (`agentctl.py`, the `wait` subcommand) does exactly one thing: block until the **first** bus event matching the predicate lands (or timeout), then return. It is:

- **One-shot**, not a standing subscription — once it returns (match or timeout), nothing is watching anymore until another `wait` is explicitly started.
- **Scoped to one `--run`** — each run has its own bus, so a single `wait` invocation cannot observe events from a different run at all, regardless of predicate.

The orchestrator (this agent) was, at the time, running a single background `wait` targeting `ticket-itermbug`'s reply. That call had no visibility into `ticket-impl` whatsoever. `impl-006`'s and `impl-007`'s `question` events landed in `ticket-impl`'s bus with nothing subscribed to it, so no notification fired — they were only discovered on the next manual `status`/`list` check, which happened to be prompted by the human asking.

This is a process gap in how the orchestrator uses the tool, not a bug in `agentctl.py`'s event log itself — the log is reliable and complete; the coverage of *who is currently watching it* was not.

## 3. Reproduction / pattern that triggers it

1. Spawn agents across two or more runs.
2. Start a background `wait` for run A only.
3. An agent in run B reaches `awaiting_human` (question/blocked) while that `wait` is still pending.
4. No notification arrives for run B's event until a human asks or the orchestrator happens to check manually. If the `wait` for run A is long-running (e.g. a multi-minute ticket-implementation turn), the gap can be large.

## 4. Practical fix already adopted mid-session

Once identified, the immediate fix was to run **one background `wait` per run being tracked**, in parallel, rather than one overall — e.g. simultaneously watching `ticket008-review`, and `ticket-impl` (for both `impl-006` and `impl-007` separately, since a single `wait` predicate matches one agent at a time). This closes the gap for as long as every active run has its own standing `wait`.

This is not yet a durable fix — it depends on the orchestrator remembering to (a) start a `wait` for every run it cares about, and (b) **immediately restart** a fresh `wait` (chained via `--from-seq`) as soon as one returns, so coverage doesn't lapse the moment an event fires. Nothing in the tooling enforces or reminds about either of those; both are currently manual discipline.

## 5. Suggested structural fix directions (not decided — for human review)

1. **A multi-run/all-agents watch mode.** `agentctl` currently requires a single `--run` per invocation and a single predicate. A mode that could watch every run under a runtime root (or an explicit list of runs) and surface *any* `question`/`blocked` event across all of them in one blocking call would remove the need for the orchestrator to manually fan out one `wait` per run.
2. **A standing poll/daemon pattern instead of one-shot wait.** E.g. a `agentctl watch` subcommand that, once started, keeps re-arming itself after every match (internally chaining `--from-seq`) and streams matches as they occur, rather than requiring the caller to notice a `wait` has returned and manually restart it.
3. **A "silence" alarm.** Independent of 1/2: since a real risk is an agent sitting in `awaiting_human` for an extended period with nothing watching, a cheap complementary safeguard is a periodic sweep (`agentctl status`/`list` across all known runs) on a fixed interval, purely to catch anything a `wait`-based approach missed — a belt-and-suspenders check rather than the primary mechanism.

Option 2 (self-re-arming watch) most directly fixes the mechanism that failed here — a `wait` that silently stops covering anything once it returns. Option 1 additionally removes the requirement to manually fan out per-run. Option 3 is cheap insurance regardless of which of 1/2 is chosen.

## 6. Constraints for whoever picks this up

- No changes have been made to `agentctl.py`. This document is purely descriptive of an orchestration-process gap, observed through live usage, not a code defect in the existing `wait` command as it's currently documented/specified to behave (it does exactly what its one-shot, single-run contract says).
- Any fix should preserve `wait`'s existing one-shot behavior as a still-valid, simpler primitive for scripts/tests that genuinely only want to block once — this should be an additive mode, not a replacement.
