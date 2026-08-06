# CVviewer — Agent Workflow

This file defines how the orchestrating agent (you) must run each iteration.
Follow these steps exactly, in order. Do not skip steps or combine them.

---

## The Iteration Workflow

### Step 1 — Write Tickets (Ticket Architect subagent)
Spawn a subagent with:
- **Model: `sonnet`**
- Role: Ticket Architect (`.agent/skills/ticket-architect/SKILL.md`)
- Input: sprint plan (`work_organisation/sprints/<current-sprint>.md`, Current State + iteration goal) + relevant existing source files
- Task: Write granular tickets for the iteration
- Output: Save tickets to `work_organisation/tickets/iteration-N.md`

### Step 2 — Human Checkpoint: Sanity-Check Tickets (Orchestrator)
Present the tickets from Step 1 to the human before spending review effort on them.
Ask: **"Do these tickets look right, or is anything missing/wrong before I send them for defensive review?"**
- If the human requests changes, edit `work_organisation/tickets/iteration-N.md` directly and re-confirm.
- Do not proceed to Step 3 until the human explicitly approves moving on.

### Step 3 — Review Tickets (Defensive Architect subagent)
Spawn a subagent with:
- **Model: `opus`**
- Role: Defensive Architect (`.agent/skills/defensive-architect/SKILL.md`)
- Input: `work_organisation/tickets/iteration-N.md` + sprint plan + relevant source files
- Task: Review every ticket through all defensive lenses
- Output: Save findings to `work_organisation/tickets/iteration-N-review.md` (separate file — do NOT append to tickets)

### Step 4 — Discuss with Human (Orchestrator)
Present a summary of the tickets and the defensive review to the human.
Walk through each flagged issue. For each one, ask: **"Is this worth fixing?"**
Do not proceed until the human has approved or dismissed every issue.

### Step 5 — Update Tickets + Implement (merged or separate)

**If agreed changes are concrete and unambiguous** (e.g. "fix all", clearly specified fixes):
- Skip the separate update step
- Pass original tickets + agreed changes list directly to the implementation subagent
- Human approval from Step 4 discussion counts — no extra approval step needed

**If agreed changes involve design decisions or ambiguity:**
- Edit `work_organisation/tickets/iteration-N.md` directly using the Edit tool (no subagent, no SKILL.md)
- Show updated tickets to human for final approval before proceeding

### Step 6 — Human Final Approval (Orchestrator)
Only required when Step 5 used the separate update path.
**Do not proceed to implementation until the human explicitly says "go".**

### Step 7 — Implement (Agent Sprint Framework subagent)
Spawn a subagent with:
- **Model: `sonnet`**
- Role: Agent Sprint Execution Framework (`.agent/skills/agent-sprint-framework/SKILL.md`)
- Input: `work_organisation/tickets/iteration-N.md` (final approved tickets) + sprint plan + relevant source files
- Task: Before starting, update `## Current State` in the sprint plan to reflect what is about to be built. Then work through the tickets one at a time, following the skill's own three-phase loop per ticket:
  1. `TICKET_DISCOVERY` — analyze the ticket, check it against design principles, present the plan, and **stop for human sign-off before writing code**
  2. `IMPLEMENTATION` — write the code and tests, run `pytest` / `ruff check`, document what changed, and **stop for human sign-off before moving to review**
  3. `REVIEW` — explain the work, have the human manually test it, and **stop for explicit human sign-off before looping back to the next ticket**
- Rules:
  - The skill's per-ticket hard blockers ARE the human-in-the-loop mechanism for this step — do not skip or compress them
  - Stop and report back to orchestrator if stuck (do not guess)
  - Do not touch files outside the ticket scope
  - Do NOT commit — the orchestrator handles that

### Step 8 — Verify & Commit (Orchestrator)
Run through the iteration's Verify criteria from the sprint plan.
If all pass:
- Update `## Current State` in the sprint plan
- Commit with: `feat: iteration N — <short description>`

If any Verify step fails:
- Report back to human before committing

---

## Rules for the Orchestrator

- Never skip the ticket + review cycle, even for simple iterations
- Never let tickets go from Step 1 to Step 3 without the Step 2 human checkpoint
- Never let the implementation subagent start without human approval (Step 6)
- Never batch two iterations into one run
- If the human says "just do it" — remind them of the workflow and ask once more
- Keep the main conversation focused on decisions, not implementation details
- Prefer direct edits over subagents whenever the change is well-defined
