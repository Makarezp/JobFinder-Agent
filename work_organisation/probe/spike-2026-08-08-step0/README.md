# Spike report — Probe Loop Step 0 investigations

**Date:** 2026-08-08
**Commit under test:** `1bb37a7`
**Ticket:** `work_organisation/tickets/agent-tabs-probe-loop.md` (Revision 3)
**Scope executed:** the two investigation spikes only. T1, T2, T3, T4, T6, T7 not implemented.
**Environment:** Claude Code **v2.1.226**, tmux 3.7b, macOS.

Both spikes have definitive answers. Neither required a change to the subject
under test, and none was made — `git status` over `.agent/skills/agent-tabs/`
was clean at teardown.

> **The Claude Code version is load-bearing.** Finding D1 below is a defect
> against v2.1.226 specifically, and `agentctl`'s own docstring records that the
> affected heuristic was verified against v2.1.223. Re-check D1 before acting on
> it if your version differs.

---

## Spike 1 — does `turn_start` fire on human pane input?

### Answer: YES, in both cases. The ticket's claim is correct and T5a is unblocked.

Method: one throwaway `--model haiku` worker under an isolated runtime root,
driven with `tmux send-keys` (byte-identical to a human typing), asserted
directly against `bus.jsonl`. No `agentctl list` or `status` was used as
evidence (W3).

| Case | Stimulus | Result |
|---|---|---|
| (a) plain text, idle pane | `send-keys 'Say the word PINEAPPLE...' Enter` | `turn_start` seq 6, +0.25 s |
| (b) after a `question` report | `question`@9 → `turn_end`@10 → `send-keys 'blue' Enter` | `turn_start` seq 11 |

Raw evidence: `evidence/probe-s1-bus.jsonl`.

```
{"type":"question",  "seq":9, "ts":"2026-08-08T09:28:30.189Z"}
{"type":"turn_end",  "seq":10,"ts":"2026-08-08T09:28:32.326Z"}   <- awaiting_human
{"type":"turn_start","seq":11,"ts":"2026-08-08T09:28:44.780Z"}   <- the human answered
```

### Why it could hardly have been otherwise

`turn_start` is not an agent-tabs concept. `HOOK_EVENTS` (`agentctl.py:938-943`)
maps it to Claude Code's **`UserPromptSubmit`**, which fires on *any* prompt
submission and cannot distinguish a human keystroke from a doorbell keystroke.
`derive_state`'s docstring (`:505-507`) already depends on this behaviour:

> A report (reply/question/blocked) only counts while it is newer than the most
> recent `turn_start`, so answering a question in the pane clears
> `awaiting_human` on the agent's next turn rather than latching forever.

**Consequence for the ticket:** T5a's `ignored_awaiting_human` check is *not*
inverted and can be written as specified. The ticket branch that would have
required redesigning it does not apply.

---

## Ordering probe — a fragility the ticket does not name

This was not in the original assignment; it was added because the same property
that makes Spike 1 succeed also makes `agentctl send` emit a `turn_start`.

`_deliver` (`agentctl.py:1232-1240`) types the keystroke **first** and appends
`message_sent` **second**:

```python
backend.send(handle, doorbell_text(inbox_path), enter)  # submits the prompt
...
append_event(paths, agent, EventType.MESSAGE_SENT, {...})  # only now
```

So `message_sent → turn_start` ordering is a **race between two processes**, not
a construction guarantee.

**Measured: 7 pairs across 2 runs, 0 inversions.** The five real doorbell
deliveries: **92, 87, 88, 81, 94 ms** (mean 88 ms). Reproduce with
`evidence/ordering_probe.sh`.

The orchestrator wins only because the worker's hook must cold-start a Python
interpreter before it can append `turn_start`. That ~88 ms is the entire margin.

**Why it matters.** T5a's discriminator is ordering alone. If it ever inverts, a
genuine orchestrator barge-in renders as `question → turn_start → message_sent`
— byte-identical to the near-miss fixture the ticket declares *correct*
behaviour. That is a false **negative**: the check silently clears the exact
violation it exists to catch.

**Recommendation.** T5a should treat a `turn_start` landing within ~250 ms
*after* a `message_sent` as caused by it, rather than as evidence a human
answered; and `_deliver`'s ordering should be stated in the ticket as a
load-bearing invariant so a future refactor cannot quietly reverse it.

**Calibration:** 7 pairs is a small sample and is equally consistent with the
ordering being genuinely reliable. This is reported as a fragility, **not** a
bug. The 88 ms figure is not evidence of a defect.

---

## Spike 2 — how can the orchestrator's `agentctl` calls be observed?

### Answer: ROUTE A WORKS. Route B is not needed and no `agentctl.py` ticket is required.

A `PreToolUse` hook on `Bash`, in a probe-controlled working directory reached
via `spawn --cwd`, exploiting the additive settings layering at `SKILL.md:232-238`.

Captured on the first attempt, under a cwd containing **both a space and an `@`**
(`/tmp/probe cwd@spike`) — the exact shape that failed *silently* as review
finding B1 in Iteration 1:

```json
{"ts":"2026-08-08T09:51:37.528900Z","hook_event":"PreToolUse","tool":"Bash",
 "command":"echo PROBE_MARKER_12345","cwd":"/private/tmp/probe cwd@spike",
 "session_id":"18c5be24-342a-4829-ba69-56d3eef3d2b2",
 "agent_env":"s3","run_env":"probe-s3"}
```

Confirmed, as the ticket required:

- the hook **fires**;
- it captures the **full command string**;
- it does **not perturb** the subject (the worker's turn completed normally);
- `--isolated-settings` was deliberately **not** passed (it maps to
  `--setting-sources ""` at `:1359-1360` and would disable the mechanism);
- every element of the hook command was `shlex.quote`d.

**Bonus not anticipated by the ticket:** the hook inherits the three-key window
environment from `:1440`, so `AGENT_TABS_AGENT` and `AGENT_TABS_RUN` are
available to it directly. Attribution of a command to an agent needs no
`session_id` correlation.

Generator: `evidence/make_route_a.py`. Captured settings:
`evidence/routeA-settings.json`. Capture: `evidence/routeA-commands.jsonl`.

### Blocker Route A must handle — not in the ticket

Claude Code now shows a **workspace-trust dialog** for any working directory the
user has not previously trusted:

> Quick safety check: Is this a project you created or one you trust?

It blocks **before** `SessionStart` fires, so `spawn` times out at 60 s and the
`except` arm at `:1488-1493` kills the window — C002 working exactly as
documented. The first attempt died precisely this way
(`evidence/probe-s2-bus.jsonl`):

```json
{"type":"error","data":{"stage":"spawn",
 "error":"agent 's2' never reported SessionStart within 60s.\nLast screen:\n\n\n..."}}
```

The version's own release notes, visible on the worker's screen, confirm it is
new: *"Added a workspace trust prompt"*.

**T5's harness must pre-seed trust for its probe cwd, or every trial dies at
spawn.**

---

## Defects found

### D1 — HIGH. Live in `agentctl` today. `send` silently refuses healthy agents.

`_input_row_looks_busy` (`agentctl.py:1563-1584`) misreads Claude Code
v2.1.226's composer **placeholder** as pending human input. An idle composer
renders `❯\xa0check your inbox`; the function returns `True` →
`Readiness(False, "human_typing")` → every `send` exits **3** and **never rings
the doorbell**.

Observed live: ten consecutive messages (`0006`–`0015`) accumulated in the inbox
of a perfectly healthy, idle agent, none of them announced.

Proof it is a placeholder and not real text:

- typing `ZZZ` **replaced** it — the row became `❯\xa0ZZZ`;
- 40 `BSpace` keystrokes did **not** remove it;
- forcing a repaint did not remove it.

Three-line reproduction — no tmux, no spawn, no model call:

```python
import sys

sys.path.insert(0, ".agent/skills/agent-tabs")
import agentctl as m

m._input_row_looks_busy("❯\xa0check your inbox")  # -> True   IDLE agent
m._input_row_looks_busy("❯\xa0half a sentence")  # -> True   human really typing
m._input_row_looks_busy("❯\xa0")  # -> False
```

The first two are indistinguishable to the gate. The function's own docstring
states it was *"Verified against Claude Code v2.1.223"* and warns that failing
closed *"would deadlock every workflow the moment the TUI changed"* — which is
exactly what has now happened.

**Blocks:** T2's dirty-composer acceptance criteria, and the C004 gate generally.

### D2 — HIGH for the harness. Screen captures are stale or blank.

`backend.capture()` returns a stale or empty screen for panes in an **unattached**
tmux session; they repaint only on resize. Evidenced in a real failure: s2's
`Last screen:` diagnostic is 40 blank lines, so the operator gets no diagnostic
at all.

**Consequence:** `assert_screen_lacks` (T1) and T2's criterion *"`assert_screen_lacks`
confirms the payload was never typed into the pane"* would **pass vacuously** on
a blank capture — a green assertion proving nothing. T5's `screen_parsing` check
reads the same unreliable surface.

### D3 — MEDIUM. The default permission mode blocks the protocol's own channel.

`DEFAULT_PERMISSION_MODE = "acceptEdits"` (`:928`) causes a fresh worker to block
on approval dialogs for **reading its own inbox** and for running
**`agentctl reply`**. With T1's `create_sut` minting runtime roots under
`tempfile.mkdtemp()`, every probe trial will hang on a dialog until timeout.

### D4 — LOW. Ticket text is wrong.

T1 step 2 states `events()` *"parses `<runtime>/bus.jsonl`"*. The real path is
**`<runtime>/<run>/bus.jsonl`** — `RunPaths.build()` sets `root = runtime_root/run`
and `.bus = root/"bus.jsonl"` (`:168-186`). A `ground.py` written to the ticket's
text reads a nonexistent file.

---

## Ticket edits these findings require

| Where | Change |
|---|---|
| T1 step 2 | `<runtime>/bus.jsonl` → `<runtime>/<run>/bus.jsonl` (D4) |
| T1 `create_sut` | Must set a permission mode that does not dialog-block (D3) |
| T1 / T2 criteria | `assert_screen_lacks` is vacuous on stale captures; force a repaint or drop it as evidence (D2) |
| T2 dirty-composer | Criteria currently unbuildable — the gate they assert against misfires on idle agents (D1) |
| T5 Step 0 | Record **Route A works**; add workspace-trust pre-seeding as a hard prerequisite |
| T5a | Add the ~250 ms ordering tolerance; state `_deliver`'s type-then-log ordering as load-bearing |

**These edits have been identified but NOT applied.** Applying them is a human
decision: this ticket has already spent two revisions on confident changes that
were themselves wrong.

---

## W11 verification pass

Every specific checked against source at `1bb37a7`. All resolved correctly:

| Claim | Verdict |
|---|---|
| `which agentctl` → not found | Confirmed, exit 1 |
| hook absolute vector `:1141-1145` | Exact |
| worker absolute path `:1221` | Exact |
| `--isolated-settings` → `--setting-sources ""` `:1359-1360` | Exact |
| `main()` dispatch `:2383-2385` | Exact |
| `SKILL.md:232-238` additive settings layering | Exact |
| `spawn --cwd` `:1960` | Exists |
| T2 Step 0(c) predicted argv | Confirmed verbatim: `claude --settings <path> --permission-mode acceptEdits --model haiku` |

**Incidental confirmation for T1 step 2.** Importing `agentctl` via
`importlib.util.spec_from_file_location` **crashes** — `AttributeError` inside
`dataclasses`, because the module is not registered in `sys.modules` before
`exec_module`. `tests/conftest.py`'s docstring claims the `sys.path` idiom is
*"simpler and more robust than reconstructing the module from a spec"*. That is
now empirically confirmed, and T1's instruction to use the conftest idiom is
correct as written.

---

## Isolation and teardown

Everything spawned used its own runtime root (`/tmp/probe-spike-run`), never the
default `~/.local/state/agent-tabs/<repo>-<hash>/`. All spawns used
`--viewer none`.

Teardown verified:

- `close-run --force` on `probe-s1`, `probe-s2`, `probe-s3`, each followed by an
  unconditional `tmux kill-session` regardless of exit status;
- `tmux list-sessions` returned to its pre-spike count — the eight pre-existing
  leftovers were neither added to nor removed;
- `/tmp/probe-spike-run` and `/tmp/probe cwd@spike` deleted;
- `git status --porcelain .agent/skills/agent-tabs/` → 0 lines, so the
  `187 passed, 2 skipped` baseline holds by construction.

## Cost

Spike 1 was budgeted at ~10 minutes. It took roughly **three hours**, almost
entirely spent on D1, D3 and the trust dialog — the substrate defects *were* the
work.

This is a signal for T4's estimates, which assume ~60 sequential spawns proceed
without human intervention. On this evidence they will not: each spawn into an
untrusted cwd needs a trust dialog answered, each worker needs approval dialogs
cleared under the default permission mode, and `send` currently refuses idle
agents outright.

## Files

| File | What it is |
|---|---|
| `evidence/probe-s1-bus.jsonl` | Spike 1 — both human-input cases, and the ordering pairs |
| `evidence/probe-s2-bus.jsonl` | The trust-dialog spawn failure, incl. the blank `Last screen:` |
| `evidence/probe-s3-bus.jsonl` | The successful Route A run |
| `evidence/routeA-commands.jsonl` | The captured `PreToolUse` line — Route A's proof |
| `evidence/routeA-settings.json` | The `.claude/settings.json` that produced it |
| `evidence/make_route_a.py` | Regenerates the probe cwd (space + `@`) and its hook |
| `evidence/ordering_probe.sh` | Reproduces the ordering measurement |
