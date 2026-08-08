# Work Organisation

This file is the canonical routing and status register for planned work. Detailed sprint and ticket files carry their evidence and acceptance criteria; this register decides what is current.

## Lifecycle

- **Planned** — approved scope, not started.
- **Implemented — verification pending** — code exists, but required acceptance evidence is incomplete.
- **Done** — all stated acceptance criteria are evidenced.
- **Archived** — no longer drives execution. Historical context only.

Only active work belongs in `sprints/` or `tickets/`. Move completed or superseded material to `history/`; do not execute it merely because it is discoverable there.

## Active work

| Work item | Status | Authority | Next action |
|---|---|---|---|
| Sprint V3: Agent-Tabs Hardening & Probe Loop | Active | `sprints/sprint_v3_agent_tabs_hardening.md` | Follow its dependency graph and execution notes. |
| T0: Composer readiness regression | Implemented — live verification pending | `tickets/agent-tabs-composer-readiness-regression.md` | Run the opt-in live-worker and manual acceptance checks, then mark done only if they pass. |
| T1–T7: Probe loop | Planned — Revision 4 | `tickets/agent-tabs-probe-loop.md` | T3 and T5a are independent; the T1 → T2 → T4 → T6 → T7 chain follows the V3 dependency graph. |

## Evidence and proposals

| Location | Purpose | Execution rule |
|---|---|---|
| `probe/` | Machine-generated spike evidence and probe artifacts | Evidence only; promote a finding into an active ticket deliberately. |
| `spec/` | Product/design proposals not scheduled as active sprint work | Do not implement without promotion into an active ticket. |
| `bugs/` | Investigations and defect records | Triage into an active ticket before implementation. |

## Archived work

| Artifact | Reason archived | Location |
|---|---|---|
| Sprint V2: Search Ledger | Declared landed by Sprint V3; retained for product-history context. | `history/sprints/sprint_v2_search_ledger.md` |
| Agent-Tabs Iteration 1 and its review | Shipped prerequisite for the probe loop. | `history/tickets/agent-tabs-iteration-1.md`, `history/tickets/agent-tabs-iteration-1-review.md` |
| Agent-Tabs Codex support | Implemented prerequisite for the probe loop. | `history/tickets/agent-tabs-codex-support.md` |
| Agent-Tabs initial-task bootstrap | Marked done. | `history/tickets/agent-tabs-initial-task-bootstrap.md` |

## Maintenance rule

When a work item changes state, update this register and its detailed ticket in the same change. When it becomes Done or is superseded, move it to `history/` and repair references from active planning files.
