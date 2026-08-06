# Defensive Review — Agent-Tabs Iteration 1

Reviewed against the actual machine and repo, not against the ticket's own claims. Findings marked **[VERIFIED]** were reproduced empirically; **[UNVERIFIED]** means I could not test it (tmux is not installed) and it must be confirmed before coding.

Overall: the architecture is sound and the invariants (inbox-first doorbell, state-derived-from-events, adapter isolation) are the right ones. But three defects will stop Iteration 1 dead on *this* machine, and all three are in Tickets 1 and 3 — the critical path.

---

## BLOCKERS

### B1 — Hook commands are shell-parsed; this repo's path has spaces. Every spawn will time out. [VERIFIED]

**Where:** Ticket 3, Step 3 (settings generation).

The ticket's template embeds the absolute path unquoted:

```json
{"type":"command","command":"<abs> hook spawned --run R --agent A"}
```

The repo root is `/Users/acc/Library/CloudStorage/GoogleDrive-makarezp1@gmail.com/My Drive/Projects/CVviewer` — **two spaces and an `@`**. Claude Code executes the `command` string through a shell, so `<abs>` splits into `.../CloudStorage/GoogleDrive-makarezp1@gmail.com/My`, `Drive/Projects/...`.

I tested this with a real `claude -p` session and a hook script under a path containing a space:

| settings.json `command` | Hook fired? |
|---|---|
| unquoted (as the ticket specifies) | **No — silent** |
| `shlex.quote`d (control) | Yes, `argv` exactly correct |

The failure mode is the dangerous part: **the session started normally and printed its answer, exit code 0, no error anywhere.** Nothing surfaces. So `spawn` blocks for its full 60s `--spawn-timeout`, kills the window, and reports "readiness handshake failed" with 40 lines of a screen that looks perfectly healthy. This will read as "the handshake concept doesn't work" when in fact only the quoting is wrong — precisely the wrong conclusion to draw about Iteration 1's core hypothesis.

**Correction.** Build the command with `shlex.quote` on every element:

```python
import shlex, sys
cmd = " ".join(shlex.quote(p) for p in [sys.executable, str(AGENTCTL_ABS), "hook", ev, "--run", run, "--agent", name])
```

Add to Ticket 3's acceptance criteria: *a test writes settings into a tmp path containing a space and an `@`, then asserts `shlex.split(command)` round-trips to the exact expected argv list.* Asserting the string merely "contains the absolute path" (the current AC) passes on the broken version.

---

### B2 — `git rev-parse --show-toplevel` resolves differently inside a worktree. Workers write to a runtime directory the orchestrator never reads. [VERIFIED]

**Where:** Ticket 1, Step 2 (root resolution) interacting with Ticket 3, Step 4.3 (`--worktree`).

Ticket 1 resolves the runtime root dynamically as `<git-root>/.agent/runtime`. Ticket 3 places workers in `git worktree add <runtime>/worktrees/<name>`. Inside a worktree, `--show-toplevel` returns *the worktree*, not the main repo. Reproduced:

```
orchestrator resolves : <repo>/.agent/runtime
worker resolves       : <repo>/.agent/runtime/worktrees/critic/.agent/runtime   ← nested, different
```

So a `--worktree` agent calling `agentctl reply` writes its outbox into a private nested runtime tree. `read --outbox` returns nothing, `wait --until 'type=reply'` never matches and times out at 900s. Worse, the derived state still looks healthy because the *hooks* run from generated settings — this desynchronises the two channels rather than failing cleanly.

**Correction.** The runtime root must be resolved **once, by the orchestrator, and then pinned** — never re-derived by the worker:

1. Add a global `--runtime <abs>` flag to `agentctl`, taking precedence over `$AGENT_TABS_RUNTIME` and the git-root fallback.
2. Emit `--runtime <abs>` into every generated hook command (alongside the B1 quoting).
3. Document in `WORKER.md` that `agentctl reply` inherits the root from `$AGENT_TABS_RUNTIME`, and set that variable in the spawned session's environment.
4. Keep the git-root fallback only for the orchestrator's own convenience, and use `git rev-parse --path-format=absolute --git-common-dir` (which correctly yields the *main* `.git` from inside a worktree) rather than `--show-toplevel`.

Add an AC: *a test invokes `reply` with cwd set to a git worktree nested under the runtime root and asserts the outbox file lands in the orchestrator's runtime tree.*

---

### B3 — The concurrency test cannot work as specified: macOS uses the `spawn` start method. [VERIFIED]

**Where:** Ticket 1, Step 7 — explicitly called out as "the critical test — write it first".

The ticket mandates two things that are mutually incompatible here:
- load `agentctl.py` by path via `spec_from_file_location` in a **session-scoped conftest fixture**, and
- append from **8 concurrent `multiprocessing.Process` workers**.

Python on macOS defaults to `spawn` (confirmed: `multiprocessing.get_start_method()` → `spawn` on this box, Python 3.14.2). Each child is a fresh interpreter that re-imports and unpickles its target. The fixture-loaded module is not importable by name and is not picklable. I built the exact layout the ticket prescribes and ran it under the project's own pytest:

```
TypeError: cannot pickle 'module' object
  when serializing tuple item 2 ... multiprocessing.Process object
```

It fails at `p.start()`, before a single event is written — so it fails without ever testing the locking it exists to test.

Note the underlying `flock` design is fine. I tested the append-under-`flock` pattern directly (8 processes × 25 events) both in this repo and on local disk: **200/200 lines, seq 1..200, zero duplicates, ~0.09s.** The bus concurrency model works; only the test harness is unbuildable as written.

**Correction.** Specify in the ticket that the child must re-load the module by path itself, and that only picklable primitives cross the boundary:

```python
# module level in test_bus.py — importable in the spawned child
def _append_worker(src: str, bus: str, n: int) -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("agentctl", src)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    for _ in range(25):
        mod.append_event(...)
```

Pass `str` paths only — never the fixture's module object. Keep the session fixture for the in-process tests; it is only the multiprocessing test that needs this treatment.

---

## HIGH

### H1 — `./scripts/test.sh` runs `mypy .` in strict mode over `tests/`, under `set -e`. [VERIFIED]

The ticket's constraints section names only ruff (`line-length = 150`, `E,F,I,UP,B`, `py311`). It never mentions mypy. But `scripts/test.sh` step 3 runs `mypy .` with `set -e`, and `[tool.mypy] strict = true`. I probed the actual boundaries:

| Path | ruff `check .` | mypy `.` |
|---|---|---|
| `.agent/skills/agent-tabs/agentctl.py` | **lints it** | skips it (hidden dir) |
| `tests/agent_tabs/*.py` | lints it | **checks it, strict** |

An unannotated `def f(x)` dropped into `tests/unit/` produced `error: Function is missing a type annotation [no-untyped-def]` and broke the run. So **every new test function needs full annotations** (`-> None` at minimum), or `./scripts/test.sh` fails at step 3 and never reaches pytest. Six new test files are in scope; this is not a small tax.

**Correction.** Add to each ticket's constraints: *test functions must be fully annotated (`def test_x(...) -> None:`) — `mypy .` runs strict over `tests/`.* Also state explicitly that `agentctl.py` is linted by ruff but not type-checked by mypy, so its annotations are for humans, not a gate.

### H2 — A spawned worker will hit a permission prompt and deadlock the handshake. [VERIFIED that the flag exists; behaviour unverified]

Ticket 3's `spawn` signature has `--model` but **no permission mode**. A fresh `claude` session in a tmux window that hits a permission prompt sits waiting for a human keypress. From the bus's point of view it is `busy` forever: `turn_start` fired, `turn_end` never will. `wait` burns its full timeout and the orchestrator has no way to distinguish "thinking hard" from "blocked on a modal nobody is looking at".

`claude --help` confirms `--permission-mode <mode>` with choices `acceptEdits, auto, bypassPermissions, manual, dontAsk, plan`.

**Correction.** Add `--permission-mode` to `spawn` (plumbed into the argv), and make an explicit decision on the default — I'd suggest `acceptEdits` for workers doing implementation and leaving `bypassPermissions` opt-in, but this is a human call and belongs in Open Questions. Separately, `status <name>` should surface "busy with no `turn_end` for > N seconds" as a distinct hint, because this failure will recur.

### H3 — The doorbell failsafe does not cover the bootstrap turn.

Ticket 4's central invariant is excellent: the payload lands in `inbox/NNNN.md` before any keystroke, and `WORKER.md` tells the agent to *"check your inbox at the start of every turn"*, so a mangled keystroke is cosmetic.

That argument has a hole at turn 1. If the bootstrap doorbell keystroke (Ticket 3, step 4.7) is lost or mangled, the agent **never takes a turn at all** — so the "check inbox every turn" failsafe never executes. The agent sits idle forever with a perfectly good `0001.md` on disk that nothing will ever read. Every other message is recoverable; this one is not.

**Correction.** After ringing the bootstrap doorbell, `spawn` should confirm it landed: wait for a `turn_start` event (not just `spawned`) within a short window, and retry the doorbell once before giving up. Ticket 3's manual AC already implies this — it expects `bus.jsonl` to show `spawned` **followed by `turn_start`** — so promote that from an observation to an enforced step.

### H4 — `"<run>:<name>"` is not a stable or unique tmux handle. [UNVERIFIED — tmux not installed]

Ticket 2 fixes the handle format as `<run>:<name>`, i.e. tmux resolves the target by *window name*. Two known tmux behaviours make that fragile: window names are **not required to be unique** within a session (so `-t run:critic` silently resolves to whichever matches first), and the `automatic-rename` option can rewrite a window's name from the running process. Ticket 3's duplicate-name guard only checks agents *alive in this run*, which does not cover a window left behind by a crashed reap.

`#{window_id}` (`@0`, `@1`, …) is unique per session and immutable for the window's lifetime.

**Correction.** Have `open` capture the id at creation — `tmux new-window -P -F '#{window_id}' ...` — and use that as the handle; `alive` becomes an exact match against `tmux list-windows -F '#{window_id}'`. Keep the human-facing name as a separate field in `meta.json` for display. This is one extra field and removes a whole class of "the orchestrator talked to the wrong window" bugs.

**Before coding Ticket 2, verify against the installed tmux:** (a) whether `send-keys` accepts the `--` terminator the ticket mandates, (b) whether `new-window` treats trailing argv as a true exec vector or joins-and-shells it (this determines whether the "never build a shell string" rule actually holds at the tmux boundary, not just the `subprocess` one), and (c) that `-n <name>` disables `automatic-rename`. If any differ, report back rather than guessing — same rule the ticket already applies to `claude --help`.

---

## MEDIUM

### M1 — The `integration` marker is already taken, and its runner is gated on Docker. [VERIFIED]

Ticket 2 reuses `@pytest.mark.integration` for the tmux tests. In `pyproject.toml` that marker is documented as *"marks tests that hit real infrastructure (spins up a Postgres container)"*, and `scripts/test.sh` runs `pytest -m integration` **only if `docker info` succeeds**. Consequences: with Docker down the tmux tests never run (yet report as "skipped integration tests", implying Postgres); with Docker up they run interleaved with testcontainers, and a missing tmux binary fails the Postgres suite's run.

**Correction.** Register a distinct marker in `pyproject.toml` (`tmux: requires a local tmux binary`), mark Ticket 2's file `pytestmark = pytest.mark.tmux`, add `tmux` to `addopts` exclusion (`-m 'not integration and not tmux'`), and give `scripts/test.sh` its own block gated on `command -v tmux`. Ticket 2's AC "default `pytest` collects zero tests from this file" still holds.

### M2 — `--settings` is additive; workers inherit the project's own hooks.

`claude --help`: `--settings` loads *additional* settings. The worker will therefore also load `.claude/settings.local.json` from its cwd, plus user-level settings. Any hook there fires inside every spawned worker. Decide explicitly whether that is wanted; `--setting-sources` exists to constrain it. At minimum, Ticket 3 should state the intended layering rather than leaving it emergent.

### M3 — `append_event` and `wait` both re-read the entire log every time.

Ticket 1 step 4 reads back the whole file under the lock to compute `seq+1` on *every* append — O(n) per write, O(n²) over a run, with the exclusive lock held for the read. Ticket 5 step 3 polls at 250 ms and (as written) re-reads to find new lines. Neither matters at 200 events; both matter at a long multi-agent run, and the lock-held read is the one that will bite, since hooks from several agents contend on it.

**Correction.** Keep the last seq in a sidecar (`bus.seq`) written under the same lock, falling back to a full replay if it is missing or inconsistent — this preserves the ticket's own rule that the log stays the primary truth. For `wait`, track a byte offset and `seek` to it each tick.

### M4 — `close` sends `/exit` as literal text. [UNVERIFIED]

Ticket 6 step 3 does `backend.send(handle, "/exit", enter=True)`. With `-l` (mandated in Ticket 2), `/exit` is typed literally into the composer — which is what you want, but only if the composer is focused and empty. If the agent is mid-turn or a dialog is open, `/exit` is typed into whatever has focus and the graceful path silently degrades to the `--timeout 30` kill. Worth stating that the graceful path is best-effort and the timeout is the real guarantee, so nobody later "fixes" it by extending the timeout.

### M5 — Runtime directory sits inside a Google Drive folder.

`.agent/runtime/` will hold a high-churn append-only log plus git worktrees, inside `~/Library/CloudStorage/GoogleDrive-.../`. Adding it to `.gitignore` (Ticket 3/7) does not stop Drive from syncing it. I found no active CloudStorage FUSE mount and file locking performed at local-disk speed, so this is a caution rather than a finding — but confirm Drive is not set to sync this tree before running multi-agent sessions, and consider defaulting `$AGENT_TABS_RUNTIME` to a local path outside the synced folder.

---

## Notes on the ticket's own Open Questions

**Q2 — `--no-enter` as the default.** Keep Enter-by-default as specified. The inbox-first invariant already makes a bad send recoverable, and requiring a human keypress per message removes the orchestrator's ability to run a round trip unattended, which is the point of the framework. The one place to reconsider is the bootstrap doorbell, per H3 — but the answer there is *confirm delivery*, not *ask a human*.

**Q3 — Tickets 1→2→3 as a first slice.** Agreed, and B1/B2/B3 reinforce it: all three blockers live in that slice. Fix them and the slice genuinely proves the concept. 4–7 are mechanical once `spawned` and `turn_start` fire reliably.

**Prerequisite.** `tmux` is confirmed **not installed** (`tmux: command not found`), so `brew install tmux` is a genuine hard gate on Tickets 2, 3 and 6, and on resolving H4's three open tmux questions.

---

## What I verified, and how

| Claim | Method | Result |
|---|---|---|
| `flock` + `fsync` append is safe here | 8 processes × 25 events, in-repo and on local disk | Works: 200/200, seq 1..200, no dupes, 0.09s |
| Ticket 1's multiprocessing test design | built the prescribed layout, ran under project pytest | Fails: `cannot pickle 'module' object` |
| Hook `command` quoting | real `claude -p` run, unquoted vs `shlex.quote`d control | Unquoted silently never fires; quoted works |
| Git root inside a worktree | real `git worktree add` under the runtime path | Resolves to the worktree — nested, divergent |
| ruff / mypy coverage of new paths | probe files in `.agent/` and `tests/unit/` | ruff lints `.agent/`; mypy skips it but checks `tests/` strictly |
| `claude` CLI surface | `claude --help` | `--settings`, `--model`, `--permission-mode` all exist as assumed |
| tmux behaviours (H4, M4) | — | **Not tested — tmux is not installed** |

All probe files were removed; the repo is unchanged.
