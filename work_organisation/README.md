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
| T6: Journal and coverage digest | Implemented — human review pending | `tickets/agent-tabs-probe-loop.md` | Review the generated digest and exploration gate. |
| T7: Oracle triage and spec emission | Planned — Revision 4 | `tickets/agent-tabs-probe-loop.md` | Follow T6 human review. |

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
| T0: Composer readiness regression | Human-signed-off fix for the composer gate and unattached captures. | `history/tickets/agent-tabs-composer-readiness-regression.md` |
| T3: Claim registry | Human-signed-off claim-coverage surface. | `history/tickets/agent-tabs-probe-claim-registry.md` |
| T5a: Bus-only orchestrator checks | Human-signed-off ground-truth checks and fluency counters. | `history/tickets/agent-tabs-probe-bus-only-checks.md` |
| T1: Probe substrate | Human-signed-off isolated lifecycle and ground-truth readers. | `history/tickets/agent-tabs-probe-substrate.md` |
| T2: Deterministic puppet fault states | Human-signed-off deterministic terminal fault injector. | `history/tickets/agent-tabs-probe-puppet.md` |
| T4: Conformance briefs | Human-signed-off reduced-scope real-worker conformance smoke. | `history/tickets/agent-tabs-probe-conformance-briefs.md` |
| T5b: Cmdlog checks | Human-signed-off Route A instrumentation and cmdlog conformance checks. | `history/tickets/agent-tabs-probe-cmdlog-checks.md` |

## Maintenance rule

When a work item changes state, update this register and its detailed ticket in the same change. When it becomes Done or is superseded, move it to `history/` and repair references from active planning files.
