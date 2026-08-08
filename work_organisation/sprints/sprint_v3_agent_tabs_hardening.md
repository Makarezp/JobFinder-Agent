# Sprint V3: Agent-Tabs Hardening & Probe Loop

**Branch:** `probe-spike` (cut from `main` at `1bb37a7`)
**Track:** Tooling / meta — deliberately separate from the archived product sprint `history/sprints/sprint_v2_search_ledger.md`, which has already landed.

## Why this sprint exists

`agentctl` has ~2.7k lines of tests against a 2.4k-line tool, and they are good. They also test only one half of every claim the protocol makes: that `agentctl` *sends* a doorbell is proven; that a worker reading `WORKER.md` *re-reads its inbox* is not, and cannot be, because the receiving end is a language model reading prose.

`SKILL.md` and `WORKER.md` are the product. This sprint builds the instrument that measures them — and, as its first act, that instrument found a live high-severity bug in `send`.

## Status at sprint open

A live spike (`probe-spike` run, Opus, 2026-08-08) answered both open questions and produced four defects. **The findings below are verified against the source and are binding — do not re-litigate them.**

## Owner Decisions (Binding)

1. **`turn_start` fires on human pane input.** Verified in both cases, including the one that matters: `question → turn_end → [human types] → turn_start`. Mechanism: `HOOK_EVENTS` maps Claude Code's `UserPromptSubmit → TURN_START` (`agentctl.py:938-943`), so it is not an agent-tabs concept and any prompt submission fires it. **T5a's `ignored_awaiting_human` check is not inverted and can be built.**

2. **Route A works. Route B is dead.** A `PreToolUse` hook on `Bash`, in a probe-owned `--cwd`, captured the full command first try under a path containing both a space and an `@`. **No change to `agentctl.py` is required for orchestrator observability**, and the `AGENT_TABS_CMDLOG` fallback ticket is not needed. The hook inherits the three-key window env from `:1440`, so `AGENT_TABS_AGENT` and `AGENT_TABS_RUN` come free — attribution needs no `session_id` correlation.

3. **Workspace trust must be pre-seeded.** Claude Code now shows a workspace-trust dialog for any `cwd` the user has not trusted. It blocks before `SessionStart`, so `spawn` times out at 60s and the C002 except-arm kills the window. One spike window died exactly this way. **Any harness that spawns into a fresh `--cwd` must pre-seed trust or every trial dies at spawn.**

4. **`_deliver`'s event ordering is load-bearing and is an accident.** `_deliver` (`:1232-1240`) types the keystroke *first* and appends `message_sent` *second*, so `message_sent → turn_start` is a race between two processes. Measured n=7, **0 inversions**, gaps 81–94 ms (mean 88 ms). The margin is the worker hook's Python cold start, nothing more. T5a must tolerate near-coincident pairs (~250 ms window) rather than assume the ordering holds.

5. **The loop stops at the spec. No auto-fix.** Unchanged from the probe ticket: a patch applied by agents running *on* agent-tabs can corrupt the substrate that would have detected the bad patch.

6. **Machine-authored findings are quarantined** in `work_organisation/probe/`, never merged into `work_organisation/tickets/` without a human promoting them.

## Dependency Graph

```
T0  composer-readiness regression  ── BLOCKING, ships first
     │   (D1 breaks `send` today; also blocks T2's gate criteria)
     ▼
T3  claim registry ─────────────┐   (independent, ~1hr hand-work)
T5a bus-only checks ────────────┤   (independent, no model calls)
                                ▼
T1  probe substrate ──► T2 puppet ──► T4 conformance briefs ──► T6 journal ──► T7 oracle
                                ▲
T5b cmdlog checks ──────────────┘   (unblocked — Route A confirmed)
```

## Tickets

| # | Ticket | File | State |
|---|---|---|---|
| T0 | Composer readiness regression (D1 + D2) | `history/tickets/agent-tabs-composer-readiness-regression.md` | **DONE** (2026-08-08) |
| T1–T7 | Probe loop, seven tickets | `tickets/agent-tabs-probe-loop.md` (Revision 4) | T1, T2, T3, T4, T5a, and T5b **DONE**; T6 implemented — human review pending; T7 planned |

### T0 — Composer readiness regression *(Done; archived ticket)*

Two coupled defects in `agentctl`'s only rendering-dependent code path.

**D1 — HIGH, live today.** `_input_row_looks_busy` (`:1563-1584`) returns `bool(stripped[len(COMPOSER_MARKER):].strip())`. Claude Code **2.1.226** renders *placeholders* in the composer row; its docstring says "Verified against Claude Code v2.1.223". So an idle agent looks like it has pending human text → `Readiness(False, "human_typing")` → **every `send` exits 3 and never rings the doorbell.** Nineteen unheard messages accumulated in one spike subject's inbox. `spawn` is unaffected — `_bootstrap` calls `_deliver` directly, bypassing the gates.

**D2 — HIGH for any harness.** `backend.capture()` returns stale or blank output for panes in an *unattached* tmux session; they repaint only on resize. A real spawn failure produced a `Last screen:` diagnostic of 40 blank lines.

**They interact, which is why they are one ticket.** A blank capture finds no `❯` marker, so `_input_row_looks_busy` fails open and `send` succeeds. So:

| Pane | Capture | `send` |
|---|---|---|
| attached (human watching) | placeholder renders | **blocked**, exits 3 |
| detached | blank | works, for the wrong reason |

`send` behaves differently depending on whether a human is watching the window.

**Why the suite missed it:** `tests/test_send.py:76-90` asserts against hand-written `EMPTY_COMPOSER` / `TYPED_COMPOSER` string constants frozen at v2.1.223. The fix is not new fixtures — it is a liveness check against the installed binary. A frozen string cannot detect that the thing it models has changed.

### T1–T7 — Probe loop

Detail lives in `tickets/agent-tabs-probe-loop.md`. **Revision 4 already folds in:**

- Workspace-trust pre-seeding for Route A (decision 3 — absent from the ticket entirely).
- The ~250 ms tolerance rule, and `_deliver`'s ordering stated as a load-bearing invariant (decision 4).
- **Positive controls on every screen assertion.** D2 means `assert_screen_lacks` (T1) and T2's *"assert_screen_lacks confirms the payload was never typed"* would **pass vacuously on a blank capture** — a green assertion proving nothing, which is the exact failure class this sprint exists to eliminate.
- `--permission-mode` in `create_sut`: the default blocks a fresh worker on dialogs for reading its own inbox and running `agentctl reply` — the protocol's own reporting channel.
- Route B removed from T5 Step 0; Route A is confirmed, not conditional.

## Smallest useful slice

**T0, T1, T2, T3, T4, T5a, and T5b are complete. T6 is implemented and awaiting human review.**

T3 and T5a answer the question that decides whether the remaining tickets are worth building: *does an orchestrator reading `SKILL.md` actually obey it?*

## Execution notes

- **Model split.** Spikes and the T7 oracle → Opus (outcome unknown, judgment required). T1/T3/T4/T5/T6 implementation → Sonnet; the acceptance criteria are written adversarially (positive controls, near-miss fixtures) so a wrong spec surfaces as a red test rather than silent acceptance.
- **Validation.** `AGENTCTL_PYTHON="$PWD/.venv/bin/python" .agent/skills/agent-tabs/test.sh`. A bare `./test.sh` **silently skips** ruff, mypy and pytest — it reports missing tools as a yellow skip, not a failure. Baseline at `1bb37a7`: **187 passed, 2 skipped, ruff clean, mypy clean over 11 source files.**
- **Verify before acting.** Three review rounds and one spike each found confident, specific, wrong claims in these tickets — and in round 2, every new defect was in text the round-1 *fix* introduced. Check each line number against source before implementing it.

## Review Checklist

- [ ] T0 ships before T2 — its gate criteria cannot be tested while the gate is broken.
- [ ] D1's regression guard tests against a live spawned worker, not a string constant.
- [ ] Every screen assertion carries a positive control proving the capture was non-empty.
- [ ] Route A pre-seeds workspace trust for its probe `cwd`.
- [ ] T5a tolerates `turn_start` within ~250 ms of a `message_sent`.
- [ ] `create_sut` sets an explicit `--permission-mode` and its own runtime root, never the default tree.
- [ ] Probe assertions read `bus.jsonl` / mailboxes / `tmux` directly — never `agentctl list` / `status`.
- [ ] Every run tears down; `tmux list-sessions` returns to its pre-run count.
- [ ] Machine-authored specs land in `work_organisation/probe/`, not `tickets/`.
- [ ] No auto-fix: the loop stops at the spec.
