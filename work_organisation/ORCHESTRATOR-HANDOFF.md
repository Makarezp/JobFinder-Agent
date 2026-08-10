---
written: 2026-08-10
written_by: prior orchestrator session, right before a deliberate full restart (killed all agent-tabs tmux sessions, computer rebooted)
purpose: single entry point for a fresh orchestrator session with no memory of prior conversations
---

# Orchestrator handoff

Everything described here is fully committed on `main` as of commit `476bd0f`. Nothing in
this project currently depends on any tmux session, worktree, or agent-tabs run surviving —
they were all deliberately closed/removed before this handoff was written. `git worktree list`
should show only the main checkout; if it shows anything else, something spawned after this
doc was written and this doc doesn't know about it.

## What agent-tabs is

`.agent/skills/agent-tabs/agentctl.py` — a framework for orchestrating multiple real Claude
Code (or other CLI) agents in their own tmux windows, communicating via an append-only
`bus.jsonl` per run plus inbox/outbox files. See `.agent/skills/agent-sprint-framework/SKILL.md`
for the 3-phase implementation workflow, and `.agent/skills/ticket-architect/SKILL.md` /
`.agent/skills/defensive-architect/SKILL.md` for the ticket-writing/review cycle used below.

**Standing process used this session, worth continuing:** ticket-architect (sonnet) writes/
revises a ticket -> defensive-architect (opus) reviews it -> ticket-architect **smart-applies**
the review (judges each finding on its merits, doesn't blindly apply everything, pushes back
explicitly on anything that doesn't hold up). Implementation agents are spawned with
`--worktree` (isolated git checkout, detached HEAD) via the sprint framework, and merged into
`main` once done — see "How the TICKET-006/007 merges were done" below if you need to repeat
this pattern.

## Ticket status

- **TICKET-006** (spawn-cleanup bug, C002 finding) — **done.** Implemented, merged to `main`,
  agent closed, marked DONE.
- **TICKET-007** (lost-doorbell / B002 measurement, C014 finding) — **code fix done and
  merged; measurement still not obtained.** The actual fix (`probe/lib/runner.py` waits on
  `turn_end` before grading `_lost_doorbell`) is on `main`. So is a `probe/lib/` baseline
  commit (this harness source was gitignored and never in git history before — see
  `.gitignore`'s prior bare `lib/` line, now fixed) and a correction to the C014 evidence
  README (struck a false claim, reclassified as inconclusive). **What's NOT done:** getting
  one clean `probe.py run B002` measurement to actually validate the fix and make the
  step-6 branch decision (does the fix change the rate or not). This has been blocked
  repeatedly by TICKET-009's bug (see below), not by anything wrong with the fix itself.
  Read `work_organisation/tickets/TICKET-007-handoff.md` for full detail before resuming.
- **TICKET-008** (iTerm shared-window bug — all tabs in a run collapse onto one window) —
  **spec only, no implementation.** Ticket written, reviewed live against tmux 3.7b
  (9 findings, 2 blockers), revised to incorporate every correction, committed to `main`.
  Nobody has implemented it. It is ready to hand to an implementer as-is — read
  `work_organisation/tickets/TICKET-008-itermtab-viewer-shared-window.md` (implementation
  steps are fully spec'd, corrections from the review are inline) and
  `work_organisation/tickets/TICKET-008-review.md` (the review itself, for context on
  *why* each correction exists, useful if a future review asks "why does this look different
  from the original write-up").
- **TICKET-009** (Haiku bootstrap-reply gap — a real Claude/Haiku worker's bootstrap turn
  sometimes ends without ever calling `agentctl reply`, ~25% rate at small sample size,
  observed via live B002 measurement attempts) — **spec only, no implementation.** This
  ticket exists because it was blocking TICKET-007's step 5 — B002/B002-control need many
  consecutive clean bootstrap turns, and at a ~25% per-spawn flake rate a full clean run is
  statistically unlikely by blind retry. Ticket proposes a bounded nudge-and-retry mitigation
  inside `probe/lib/runner.py::_wait_for_bootstrap` only (no `agentctl.py` changes) — read
  `work_organisation/tickets/TICKET-009-probe-bootstrap-reply-gap.md`. Root cause is
  explicitly **not established** (candidate hypotheses only, n=8) — the ticket itself says so
  and forbids overclaiming a fix. **This has not been reviewed by defensive-architect yet** —
  that's the next step if this ticket proceeds, following the same cycle as 006/007/008.

### Recommended next step for TICKET-007/009

1. Get TICKET-009 reviewed (defensive-architect) and smart-applied, same cycle as before.
2. Implement TICKET-009 (spawn an implementer in its own `--worktree`, sprint framework).
3. Merge TICKET-009's fix to `main`.
4. Spawn a fresh implementer (or resume the idea, but there is no old impl-007 agent/worktree
   to resume — it was closed and its worktree removed after merging) to run `probe.py run B002`
   again with the mitigation in place, get a clean measurement, make TICKET-007's step 6
   branch decision, close out TICKET-007.

## Known tooling/framework bugs (all real, all still unfixed, all just documented)

None of these were fixed — per a standing constraint this session, `agentctl.py` itself was
never modified without an explicit human decision to do so. All are written up in
`work_organisation/probe/`:

1. **`send-enter-not-submitted-bug.md`** — `agentctl send`'s Enter keystroke sometimes doesn't
   register as submit, leaving the pointer text typed but unsubmitted with no error, no bus
   signal. Observed 7+ times this session across multiple agents. Workaround used every time:
   `tmux send-keys -t <handle> Enter` manually, then verify via `tmux capture-pane`.
   **Gotcha for a fresh orchestrator:** before assuming stuck text is real, check whether it's
   ANSI-dim (`\x1b[2m...\x1b[0m` in `tmux capture-pane -p -e`) — dim means it's a TUI
   placeholder hint in an empty composer, not real stuck input; only plain (non-dim) text is
   a genuine unsubmitted message.
2. **`tmux-new-window-index-collision-bug.md`** — spawning a second agent into an existing
   run with `--viewer none` can fail outright (`create window failed: index N in use`). Root
   cause not confirmed. Workaround used: spawn into a fresh run instead of a populated one.
3. **`orchestrator-notification-coverage-gap.md`** — `agentctl wait` is one-shot and
   single-run-scoped, not a standing subscription. Practical fix adopted: run one background
   `wait` per run you're tracking, and re-arm it (or just re-check via `agentctl list`) once it
   returns. If you're the fresh orchestrator: don't assume silence means nothing happened —
   check `agentctl list --run <run>` directly if you haven't had a `wait` running continuously.
4. **`iterm-viewer-shared-window-bug.md`** — the bug TICKET-008 exists to fix. Its own §5
   workaround section was corrected this session (the original recommended workaround was
   itself proven unsafe) — read the current version, not an old cached one.
5. **`haiku-bootstrap-reply-gap.md`** — the bug TICKET-009 exists to fix. See above.

## Practical agentctl reminders

- `agentctl list --run <run>` (not `status <name>` — that needs `--run` differently; `list`
  is the reliable one) to check agent state.
- `agentctl read <name> --run <run>` to read its full message history.
- `agentctl send <name> --run <run> "<text>"` to send an instruction — **always verify it
  actually got submitted** (see bug #1 above) via `tmux capture-pane -t <handle> -p` a few
  seconds later; don't just trust the `sent` confirmation.
- Spawning: `agentctl spawn <name> --role <path-to-SKILL.md> --model <sonnet|opus> --run <run>
  --viewer iterm-tab [--worktree]`. Use `--worktree` for anything that will write code, so it
  gets an isolated git checkout; omit it for ticket-writing-only agents (they can write
  directly into the main checkout — confirm with `git status` before/after either way).
- Closing: `agentctl close <name> --run <run>`. This is destructive for `--worktree` agents
  (`git worktree remove --force`) — **always merge/commit what you want to keep before
  closing**, never after.
- Merging a worktree agent's work: since `--worktree` creates a *linked* worktree of the same
  repo (not a separate clone), its commits are already in the same object database — just
  `git merge --no-edit <worktree-HEAD-sha>` from the main checkout, no remote/fetch needed.
  Watch for add/add conflicts on files both branches touched independently (happened twice
  this session, both were "the worktree's copy is stale, main already has the real fix" —
  verify direction with `git diff HEAD:<path> <worktree-sha>:<path>` before resolving, don't
  assume "theirs" is always right).
