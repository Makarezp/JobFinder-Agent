# Agent-Tabs — Iteration 1: Walking Skeleton

**Revision 2** — incorporates `agent-tabs-iteration-1-review.md` in full.
**Track:** Tooling / meta (not part of `sprint_v2_search_ledger.md`)
**Status:** DONE — archived 2026-08-08; shipped prerequisite of the probe loop.
**Goal:** A generic, project-agnostic framework that lets an orchestrating agent launch, message, observe, and close *human-visible* Claude sessions running in tmux windows.

## Context

Today `.agent/WORKFLOW.md` spawns subagents via the `Task` tool. The orchestrator controls them, but the human cannot see or talk to them. Conversely, `~/My Drive/cv-builder/scripts/launch-agents.sh` opens visible iTerm tabs, but it is fire-and-forget — the orchestrator has no handle, no readiness signal, and no return path.

This iteration builds the intersection: agents live in **tmux windows** (addressable, persistent, human-attachable), coordinate through a **filesystem bus**, and report state via **Claude Code hooks**.

### Architecture

```
Layer 4  WORKFLOW (project-specific)   — NOT in scope this iteration
Layer 3  PROTOCOL   SKILL.md + WORKER.md
Layer 2  BUS        inbox/ outbox/ events.jsonl   (pure Python, no tmux)
Layer 1  BACKEND    tmux adapter
```

### Decisions

| Decision | Choice |
|---|---|
| Backend | tmux, viewed inside an iTerm tab |
| Worker state | Hooks push events; agent-written outbox as fallback tier |
| Source location | `.agent/skills/agent-tabs/` (extracted to a generic repo later) |
| **Runtime location** | **`~/.local/state/agent-tabs/<repo>-<hash>/` — outside the repo and outside Google Drive** (rev2, M5) |
| Language | Python 3.11+, **stdlib only**, no venv, no `pip install` |
| Orchestrator placement | **Outside** tmux this iteration (see Deferred Decisions) |
| Worker permission mode | `acceptEdits` default; `bypassPermissions` opt-in, never framework-internal (rev2, H2) |
| Worker settings layering | Inherits user/project settings by default; `--isolated-settings` to restrict (rev2, M2) |
| tmux handle | `#{window_id}` (`@3`), **not** `<run>:<name>` (rev2, H4) |

### Review changes folded into Revision 2

| ID | Change | Lands in |
|---|---|---|
| B1 | `shlex.quote` every hook command element; AC asserts argv round-trip | T3 |
| B2 | Runtime root pinned by orchestrator, never re-derived by worker | T1, T3 |
| B3 | Multiprocessing test loads module in the child; only `str` crosses the boundary | T1 |
| H1 | All test functions fully annotated — `mypy .` is strict over `tests/` | T1–T6 |
| H2 | `--permission-mode` plumbed into spawn | T3 |
| H3 | Bootstrap doorbell confirmed via `turn_start`, retried once | T3 |
| H4 | Handle is `#{window_id}`; three tmux behaviours verified before coding | T2 |
| M1 | New `tmux` pytest marker, separate from `integration` | T2, T7 |
| M2 | Settings layering stated explicitly, `--isolated-settings` added | T3 |
| M3 | **Partial** — `seek` offset for `wait` accepted; `bus.seq` sidecar **deferred** | T5 |
| M4 | Graceful `close` documented as best-effort; timeout is the guarantee | T6 |
| M5 | **Escalated** — runtime root defaults outside the repo, not "consider" | T1 |
| N1 | *New:* tmux copy-mode gate in readiness check | T2, T4 |
| N2 | *New:* worker identity via environment, not agent-typed flags | T3, T7 |

### Accepted deviations from project conventions

`agentctl` is a standalone tool that must run in any repository, with or without a virtualenv, and is intended to be lifted into its own repo unchanged. That independence is the framework's core constraint and it overrides the conventions below. **These were reviewed and accepted — do not re-litigate them.**

| Rule | Deviation | Reason |
|---|---|---|
| DESIGN §2 — Pydantic schemas at boundaries | frozen `@dataclass` | No third-party deps. Raw dicts appear only at the JSON serialisation boundary, never between layers. |
| DESIGN §6 — all config via `Settings` | one `Config` dataclass reading env in exactly one place | `app.Settings` is unimportable from a standalone tool. "One truth, one path" is preserved locally. |
| CONV §4 — `structlog` tracing | `bus.jsonl` **is** the structured trace; stdlib `logging` to stderr for diagnostics | structlog is third-party. The event log is append-only, timestamped and structured. |
| DESIGN §8 — centralized `tests/` | tests colocated in `.agent/skills/agent-tabs/tests/` | The tool travels as one self-contained unit. Run with `pytest .agent/skills/agent-tabs/tests/`. |
| CONV §1 — `mypy --strict` gate | not wired into `scripts/test.sh` | mypy skips hidden dirs. Source is fully annotated and verified manually with an explicit path. |

CONV §2 (tools return errors rather than raising) is *aligned*, not deviated: the `hook` subcommand's exit-0-always rule is the CLI form of the same principle.

### Scope boundary

**In:** bus, tmux adapter, `spawn`, `send`, `read`, `wait`, `list`, `status`, `close`, `reap`, hook plumbing, protocol docs.
**Out:** anything CVviewer-specific. `agentctl` must not contain the words *ticket*, *sprint*, or *iteration*. Rewiring `WORKFLOW.md` is a later iteration.

### Prerequisite (human, one-time)

```bash
brew install tmux          # confirmed NOT installed
tmux -V                    # expect >= 3.0
```

---

## Ticket 1: Bus Layer — Runtime Root, Event Log, State Derivation

**Status: DONE**

#### Overview
Build the durable, terminal-independent core: an on-disk run directory plus an append-only event log from which every agent's state is derived. No knowledge of tmux; fully unit-testable without a terminal.

#### Implementation Steps

1. **Module skeleton — `.agent/skills/agent-tabs/agentctl.py`**
   Single-file CLI. Shebang `#!/usr/bin/env python3`, `chmod +x`. Stdlib only: `argparse`, `json`, `subprocess`, `fcntl`, `pathlib`, `dataclasses`, `datetime`, `os`, `sys`, `time`, `re`, `enum`, `shlex`, `hashlib`, `shutil`.

2. **Runtime root resolution — the pinning rule (B2, M5).**
   Resolution order, highest precedence first:
   1. global `--runtime <abs>` flag
   2. `$AGENT_TABS_RUNTIME`
   3. default: `~/.local/state/agent-tabs/<repo-basename>-<hash12>/`

   `<hash12>` is the first 12 hex chars of `sha1()` over the **absolute git common dir**, obtained with:
   ```
   git rev-parse --path-format=absolute --git-common-dir
   ```
   **Never `--show-toplevel`** — inside a worktree it returns the worktree, producing a divergent nested runtime tree. `--git-common-dir` correctly yields the *main* repo's `.git` from inside a worktree, so orchestrator and workers hash to the same value.

   Two independent reasons the default lives outside the repo:
   - This repo sits under `~/Library/CloudStorage/GoogleDrive-.../`. A high-churn append-only log plus **git worktrees** inside a cloud-synced tree is a corruption hazard — a sync daemon touching `.git` metadata mid-operation yields failures that look like git bugs. `.gitignore` does not stop Drive from syncing.
   - It keeps a disposable, absolute-path-bearing tree out of version control by construction rather than by discipline.

   Implement `RunPaths` as a `@dataclass(frozen=True)` resolving:
   ```
   <runtime_root>/<run_id>/
     bus.jsonl
     worktrees/<name>/
     agents/<name>/
       meta.json  state.json  settings.json  inbox/0001.md  outbox/0001.md
   ```

3. **Event schema** — a `@dataclass` `Event` serialising to exactly:
   ```json
   {"ts":"2026-08-06T14:22:31.123Z","run":"cvv","agent":"critic","type":"turn_end","seq":42,"data":{}}
   ```
   - `ts`: UTC ISO-8601, millisecond precision, `Z` suffix.
   - `seq`: monotonic per-run integer, assigned **inside** the write lock.
   - `type`: `EventType` str-enum — `spawned`, `turn_start`, `turn_end`, `message_sent`, `reply`, `blocked`, `question`, `exit`, `error`.
   - Unknown `type` read back from disk must not crash the reader; map to a sentinel and continue.

4. **Atomic append — `append_event(paths, event) -> Event`**
   No `flock` binary exists on macOS; use the stdlib:
   ```python
   with open(bus_path, "a+") as fh:
       fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
       # replay to find last seq, assign seq+1, write one line, flush, os.fsync
       fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
   ```
   Exactly one `\n`-terminated JSON line per call, built with `json.dumps` and written in a **single** `write()` inside the lock.

   *Performance note (M3, deliberate):* this replays the log per append — O(n) per write. Measured at 8 processes × 25 events: ~0.09s. A `bus.seq` sidecar would make it O(1) but reintroduces the cache-consistency problem this design exists to avoid. **Deferred until contention is measured**, not forgotten. Do not add it in this iteration.

5. **State derivation — `derive_state(events, outbox) -> AgentState`**
   A pure function of the event stream. `state.json` is a cache, never primary truth.
   ```
   spawned                                        -> idle
   turn_start                                     -> busy
   turn_end                                       -> idle
   turn_end + newest outbox status in
     {question, blocked}                          -> awaiting_human
   exit | error                                   -> dead
   ```
   `AgentState` str-enum: `idle`, `busy`, `awaiting_human`, `dead`.

6. **Inbox / outbox helpers**
   - `next_inbox_path(paths, agent) -> Path` — zero-padded 4-digit sequence. Never overwrite.
   - `write_inbox(paths, agent, body) -> Path`
   - `read_outbox(paths, agent, since=None) -> list[OutboxMessage]` — hand-rolled frontmatter parser (no PyYAML; stdlib only). Required key `status` ∈ `reply | question | blocked`. Missing or unparseable `status` surfaces as `status=reply, malformed=True` — **never dropped silently**.

7. **Tests — `tests/agent_tabs/test_bus.py` and `tests/agent_tabs/conftest.py` (new)**

   `agent-tabs` contains a hyphen inside a dot-directory, so it is **not importable as a package**. In `conftest.py`, a session-scoped fixture loads it by path:
   ```python
   import importlib.util, pathlib
   from types import ModuleType

   ROOT = pathlib.Path(__file__).resolve().parents[2]
   SRC = ROOT / ".agent/skills/agent-tabs/agentctl.py"


   def load_agentctl() -> ModuleType:
       spec = importlib.util.spec_from_file_location("agentctl", SRC)
       assert spec and spec.loader
       mod = importlib.util.module_from_spec(spec)
       spec.loader.exec_module(mod)
       return mod
   ```
   Do **not** create `tests/agent_tabs/__init__.py`.

   **The concurrency test needs special construction (B3).** macOS defaults to the `spawn` start method (verified: `multiprocessing.get_start_method()` → `spawn`, Python 3.14.2). Each child is a fresh interpreter that unpickles its target — and the fixture-loaded module is neither importable by name nor picklable. Passing it to `Process` fails at `p.start()` with `TypeError: cannot pickle 'module' object`, **before writing a single event**, so the test would fail without ever exercising the locking it exists to test.

   The child must re-load the module itself, and only `str` may cross the process boundary:
   ```python
   # module level in test_bus.py — importable by the spawned child
   def _append_worker(src: str, runtime: str, run: str, count: int) -> None:
       import importlib.util

       spec = importlib.util.spec_from_file_location("agentctl", src)
       mod = importlib.util.module_from_spec(spec)
       spec.loader.exec_module(mod)
       ...
   ```
   The session fixture stays for all in-process tests; only this one needs the treatment.

   Assert:
   - **Write this first:** 200 events from **8 concurrent `multiprocessing.Process` workers** yield `seq` `1..200` — strictly monotonic, zero duplicates, zero lost lines.
   - `derive_state` returns `awaiting_human` for `turn_end` when the newest outbox has `status: question`, and `idle` when it has `status: reply` — computed purely from `(events, outbox)` with no `state.json` present.
   - An event line with `"type":"future_thing"` parses without raising.
   - `next_inbox_path` returns `0002.md` after `0001.md`, and `0010.md` after `0009.md`.
   - A truncated final line in `bus.jsonl` is skipped by the reader, and the next append still succeeds.
   - Runtime root resolution: with `$AGENT_TABS_RUNTIME` set, that wins; unset, the default path is under `~/.local/state/agent-tabs/` and **not** under the repo.

#### Explicit Constraints & Warnings
- **Every test function must be fully annotated** — `def test_x(tmp_path: Path) -> None:`. `scripts/test.sh` step 3 runs `mypy .` in **strict** mode under `set -e`, and mypy checks `tests/` (it skips `.agent/` as a hidden dir). An unannotated test function fails the run before pytest is ever reached.
- `agentctl.py` is **linted by ruff but not type-checked by mypy**. Annotate it for humans; it is not a gate. Note `scripts/test.sh` step 1 runs `ruff format .`, which will reformat it.
- **Stdlib only.** No `pyyaml`, no `pydantic`, no `rich`. `pyyaml` *is* in the project's dev extras — do not be tempted; this tool must run in repos with no venv.
- **Never re-derive the runtime root in a worker context.** It is resolved once by the orchestrator and passed explicitly.
- **Do not** treat `state.json` as primary truth. Any read path that cannot fall back to replaying `bus.jsonl` is a bug.
- Target **py311** syntax; ruff `line-length = 150`, rules `E, F, I, UP, B`.

#### Acceptance Criteria
- [Automated] 8 concurrent processes appending 25 events each yield exactly 200 lines with `seq` `1..200` — no gaps, no duplicates. The test uses a module-level worker function and passes only `str` paths.
- [Automated] A test asserts `derive_state` distinguishes `awaiting_human` from `idle` with no `state.json` on disk.
- [Automated] A test writes a truncated final line, then asserts `read_events()` returns the intact prefix and `append_event()` still succeeds.
- [Automated] A test asserts the default runtime root is not a descendant of the git repo root.
- [Automated] A test invoked with cwd set to a git worktree resolves the **same** runtime root as one invoked from the main checkout.
- [Manual] `python3 .agent/skills/agent-tabs/agentctl.py --help` prints usage and exits 0 in a repo with no runtime directory yet.

---

## Ticket 2: tmux Backend Adapter + Fake Backend

**Status: DONE** — the three tmux behaviours in step 1 were verified against tmux 3.7b and all matched the assumptions. Recorded in `TmuxBackend`'s docstring.

#### Overview
Isolate every terminal-specific operation behind one interface, with an in-memory fake so everything above it is testable without a terminal. This interface is the only thing that changes to support iTerm or Ghostty later.

#### Implementation Steps

1. **Verify tmux behaviour before writing the adapter (H4).** tmux is not yet installed, so these are unconfirmed. After `brew install tmux`, check and record in the ticket:
   - (a) Does `send-keys` accept the `--` terminator this ticket mandates?
   - (b) Does `new-window` treat trailing argv as a true exec vector, or join-and-shell it? *This determines whether "never build a shell string" actually holds at the tmux boundary, not merely at the `subprocess` one.*
   - (c) Does `-n <name>` disable `automatic-rename`?
   **If any differ from the assumptions below, stop and report to the orchestrator rather than guessing** — same rule already applied to `claude --help`.

2. **Define the protocol** — a `typing.Protocol` named `Backend`:
   ```python
   def open(self, run: str, name: str, cmd: list[str], cwd: str, env: dict[str, str]) -> str: ...
   def send(self, handle: str, text: str, enter: bool) -> None: ...
   def capture(self, handle: str, lines: int) -> str: ...
   def in_mode(self, handle: str) -> bool: ...  # copy-mode / any pane mode  (N1)
   def kill(self, handle: str) -> None: ...
   def alive(self, handle: str) -> bool: ...
   def list_handles(self, run: str) -> list[str]: ...
   ```

3. **`TmuxBackend`** — **the handle is `#{window_id}`** (`@0`, `@3`, …), not `<run>:<name>` (H4). Window names are not required to be unique within a session, so `-t run:critic` silently resolves to whichever matches first; and `automatic-rename` can rewrite a name from the running process. `window_id` is unique per session and immutable for the window's lifetime. Keep the human-facing name as a separate `meta.json` field for display only.
   - `open`: ensure session (`tmux has-session -t <run>` → else `tmux new-session -d -s <run> -n __root__`), then capture the id at creation:
     ```
     tmux new-window -P -F '#{window_id}' -t <run> -n <name> -c <cwd> -e K=V ... -- <argv...>
     ```
     Pass `env` as repeated `-e KEY=VALUE` (N2). Pass argv as **separate `subprocess` list items** — never a shell string.
   - `send`: two separate calls — `tmux send-keys -t <handle> -l -- <text>`, then, only if `enter`, `tmux send-keys -t <handle> Enter`. The `-l` (literal) flag is mandatory: without it a newline inside a message submits a half-finished prompt to Claude. `--` guards text beginning with `-`.
   - `capture`: `tmux capture-pane -p -t <handle> -S -<lines>`.
   - `in_mode`: `tmux display-message -p -t <handle> '#{pane_in_mode}'` → truthy when the pane is in copy-mode.
   - `kill`: `tmux kill-window -t <handle>`.
   - `alive`: exact match of handle against `tmux list-windows -t <run> -F '#{window_id}'`.
   - All calls route through one `_tmux(*args)` helper raising `BackendError` (carrying stderr) on non-zero exit and `BackendUnavailable` when the binary is missing.

4. **`FakeBackend`** — in-memory `handle -> {"cmd","cwd","env","screen": list[str],"alive": bool,"in_mode": bool}`. Handles are synthetic (`@1`, `@2`, …) to mirror tmux. Used by every non-tmux test.

5. **Backend selection** — `get_backend(name)` reading `--backend` then `$AGENT_TABS_BACKEND`, defaulting to `tmux`, registered in a module-level dict so `iterm` is a one-line addition later.

6. **Register a dedicated pytest marker (M1).** `@pytest.mark.integration` is already taken — `pyproject.toml` documents it as *"spins up a Postgres container"*, and `scripts/test.sh` runs `pytest -m integration` **only if `docker info` succeeds**. Reusing it means: with Docker down the tmux tests never run but report as skipped Postgres tests; with Docker up they interleave with testcontainers, and a missing tmux binary fails the Postgres suite.
   - Add to `pyproject.toml` markers: `tmux: requires a local tmux binary`
   - Change `addopts` to `-ra -q -m 'not integration and not tmux'`
   - `tests/agent_tabs/test_backend_tmux.py` gets `pytestmark = pytest.mark.tmux`

7. **Tests**
   - `tests/agent_tabs/test_backend_fake.py` — `FakeBackend` satisfies `Backend`; `send(enter=False)` records text with no submit marker.
   - `tests/agent_tabs/test_backend_tmux.py` — `pytestmark = pytest.mark.tmux`. Open → capture shows the echoed marker → `in_mode` is False → kill → `alive` is False. Run id `agenttabs-test-<pid>`, torn down in a fixture `finally`.

#### Explicit Constraints & Warnings
- **Never build shell command strings.** Always `subprocess.run([...], shell=False)`. Agent messages contain quotes, backticks, `$`, and newlines — every one an injection hazard in a shell string, a non-event with argv lists.
- **Never omit `-l` on message text.** Enter is always a separate call.
- **Nothing above this layer may shell out to tmux.** A second place that calls tmux means the adapter has failed its purpose.
- macOS ships **bash 3.2** — do not add bash helpers relying on `declare -A` or `mapfile`.
- Test functions fully annotated (mypy strict over `tests/`).

#### Acceptance Criteria
- [Automated] A test asserts `TmuxBackend.send` produces exactly two invocations — the first containing `-l`, the second `Enter` — via a monkeypatched `_tmux` recorder, no real tmux needed.
- [Automated] A test asserts `open` parses the handle from `-P -F '#{window_id}'` output and stores the display name separately.
- [Automated] A message containing `"; rm -rf /"`, a backtick, and `$(...)` passes through `FakeBackend.send` byte-identical.
- [Automated] Default `pytest` collects zero tests from `test_backend_tmux.py`; `pytest -m tmux` collects them; `pytest -m integration` does **not**.
- [Manual] With tmux installed, run the tmux file, then `tmux ls` shows no leftover `agenttabs-test-*` sessions.

---

## Ticket 3: `spawn` — Hook Settings, Quoting, and the Readiness Handshake

**Status: DONE** — the stop-and-evaluate gate below was passed: a real `claude` in a real tmux window completed the full `spawned` → `message_sent` → `turn_start` → `turn_end` handshake in 10.74s. The core hypothesis is proven.

A defect worth remembering: `--runtime`/`--run` were declared only on the top-level parser while `hook_command` emitted them *after* the subcommand. argparse exited 2 before the exit-0-always handler could run, so **every real session's hooks failed silently while 63 unit tests passed** — the hook test used environment variables, the shipped command used flags. Fixed with `parents=[common]` + `default=argparse.SUPPRESS`, and pinned by `test_generated_hook_commands_actually_execute`, which runs the generated string through a real shell.

#### Overview
Launch a live Claude session in a tmux window, wired so it reports its own lifecycle to the bus. Replaces the legacy `BOOT_DELAY=4` guess with a real handshake.

> **This ticket contains the iteration's highest-risk defect (B1). Read step 3 before writing any code in this ticket.**

#### Implementation Steps

1. **CLI surface is verified.** `claude --help` confirms `--settings`, `--model`, `--permission-mode`, `--setting-sources` all exist, and the hook events `SessionStart`, `UserPromptSubmit`, `Stop`, `SessionEnd`. If anything differs at implementation time, stop and report rather than guessing.

2. **Hook subcommand** — `agentctl.py hook <event_type> --runtime <abs> --run <run> --agent <name>`.
   Reads the hook payload JSON from **stdin** (may be empty — tolerate it), appends the `Event`, refreshes `state.json`, exits **0 unconditionally**. Wrap the entire body in a broad `try/except` that writes a `type=error` event and still exits 0 — a traceback here pollutes the human's view of the session and may disturb it.

3. **Settings generation — `write_settings(...)`. Quote every element (B1).**

   The hook `command` is a **string executed through a shell**. This repo's absolute path is
   `/Users/acc/Library/CloudStorage/GoogleDrive-makarezp1@gmail.com/My Drive/Projects/CVviewer` — **two spaces and an `@`**. Unquoted, it splits into `.../CloudStorage/GoogleDrive-makarezp1@gmail.com/My` and `Drive/Projects/...`, and the hook silently never fires.

   This was reproduced against a real `claude -p` session:

   | `command` form | Hook fired? |
   |---|---|
   | unquoted | **No — and the session ran normally, exit 0, no error anywhere** |
   | `shlex.quote`d | Yes, argv exactly correct |

   The silence is the hazard: `spawn` would block its full 60s timeout, kill the window, and report "readiness handshake failed" alongside 40 lines of a perfectly healthy-looking screen — leading straight to the false conclusion that the event-handshake concept doesn't work.

   ```python
   import shlex, sys

   argv = [sys.executable, str(AGENTCTL_ABS), "hook", ev, "--runtime", str(runtime_root), "--run", run, "--agent", name]
   command = " ".join(shlex.quote(p) for p in argv)
   ```

   Note `--runtime` is baked in (B2): the worker must **never** re-derive the root.

   ```json
   {"hooks": {
     "SessionStart":     [{"hooks":[{"type":"command","command":"<quoted argv ... hook spawned>"}]}],
     "UserPromptSubmit": [{"hooks":[{"type":"command","command":"<quoted argv ... hook turn_start>"}]}],
     "Stop":             [{"hooks":[{"type":"command","command":"<quoted argv ... hook turn_end>"}]}],
     "SessionEnd":       [{"hooks":[{"type":"command","command":"<quoted argv ... hook exit>"}]}]
   }}
   ```

4. **Settings layering, stated not emergent (M2).** `--settings` is **additive** — the worker also loads user-level settings and any `.claude/settings*.json` in its cwd, so hooks defined there fire inside every spawned worker.
   - Default: **inherit** (least surprise; the human's own configuration keeps working).
   - `--isolated-settings` passes `--setting-sources` to restrict the worker to the generated file only.
   - `SKILL.md` must state this layering explicitly.

5. **Worker environment — identity by env, not by typed flag (N2).** Nothing should require the agent to *type* its own identity; an agent will eventually get it wrong or hallucinate it. `open()` sets, via `tmux new-window -e`:
   ```
   AGENT_TABS_RUNTIME=<abs runtime root>
   AGENT_TABS_RUN=<run id>
   AGENT_TABS_AGENT=<name>
   ```
   `agentctl reply` reads these; its `--run`/`--agent` flags exist only as an override.

6. **`spawn` command**
   ```
   agentctl spawn <name> --role <path/to/SKILL.md> [--run <id>] [--model opus|sonnet]
                         [--permission-mode <mode>] [--isolated-settings]
                         [--worktree] [--cwd <dir>] [--no-doorbell]
                         [--spawn-timeout 60] [--bootstrap-timeout 30]
   ```
   Sequence:
   1. Validate `--role` exists and is readable; fail fast.
   2. Reject a name already alive in this run, or containing characters outside `[A-Za-z0-9_-]`.
   3. If `--worktree`: `git worktree add <runtime>/worktrees/<name> --detach HEAD`. Record the path in `meta.json`. On any later failure, remove it before raising.
   4. Write `meta.json` (role, model, permission mode, display name, handle, worktree, created_at) and `settings.json`.
   5. `backend.open(...)` with the `claude` argv including settings, model and `--permission-mode` (default `acceptEdits`; `bypassPermissions` opt-in only, never used framework-internally). Resolve the binary via `shutil.which("claude")`.
   6. **Block for `spawned`** on the bus, or `--spawn-timeout`. On timeout: kill the window, remove the worktree, write `type=error`, exit non-zero including the last 40 lines of `capture`. **Never leave a half-live agent behind.**
   7. Unless `--no-doorbell`: write inbox `0001.md` (role path, worker-protocol path, run/agent identity) and ring the doorbell via the Ticket 4 send path.
   8. **Confirm the bootstrap landed (H3).** Every *other* message is recoverable because `WORKER.md` says "check your inbox at the start of every turn" — but if the **bootstrap** keystroke is lost, the agent never takes a turn, so that failsafe never runs. Turn 1 is the one unrecoverable message in the system. Therefore: wait for `turn_start` within `--bootstrap-timeout`; **retry the doorbell once**; if still absent, fail the spawn loudly rather than leaving an idle agent with a perfectly good `0001.md` nothing will read.

7. **Tests — `tests/agent_tabs/test_spawn.py` (new)**, `FakeBackend` plus a bus pre-seeded to simulate the handshake.
   - **Quoting round-trip (B1):** write settings into a tmp path containing a space and an `@`, then assert `shlex.split(command)` round-trips to the exact expected argv list. *Asserting the string merely "contains the absolute path" passes on the broken version — do not weaken this.*
   - Assert generated settings contain four hook entries, each carrying `--runtime`, `--run`, `--agent`.
   - Assert a spawn whose `spawned` never arrives kills the handle and exits non-zero (`--spawn-timeout 1`), and the worktree directory is gone.
   - Assert a missing `turn_start` triggers exactly **one** doorbell retry, then fails (`--bootstrap-timeout 1`).
   - Assert `open()` received `AGENT_TABS_RUNTIME/RUN/AGENT` in `env`.
   - Assert `hook` exits 0 and writes `type=error` on malformed stdin.
   - Assert `reply` invoked with cwd set to a **git worktree nested under the runtime root** writes its outbox into the orchestrator's runtime tree (B2).

#### Explicit Constraints & Warnings
- **`shlex.quote` every hook command element.** The single highest-value line in this iteration.
- **Do not use `time.sleep()` as a readiness mechanism.** Polling the bus on a short interval is fine; sleeping a fixed duration and assuming readiness is the exact defect being removed.
- **The hook subcommand must never fail loudly.** It runs inside the worker's session.
- **Absolute paths only** in generated settings; the worker may run in a worktree with a different cwd.
- **Never re-derive the runtime root inside a worker.** It arrives via `--runtime` and `$AGENT_TABS_RUNTIME`.
- The runtime tree is **disposable, not portable** — it bakes absolute paths.
- Test functions fully annotated.

#### Acceptance Criteria
- [Automated] Settings written to a path containing a space and an `@` produce a `command` whose `shlex.split` equals the expected argv exactly.
- [Automated] On spawn timeout, `FakeBackend.kill` was called and the worktree directory no longer exists.
- [Automated] A missing `turn_start` produces exactly two doorbell sends (initial + one retry) and a non-zero exit.
- [Automated] `agentctl hook turn_start` with `stdin=""` exits 0 and appends exactly one event.
- [Automated] `reply` run from a nested worktree cwd lands its outbox in the orchestrator's runtime tree.
- [Manual] `agentctl spawn critic --role .agent/skills/critical-thinker/SKILL.md` returns within ~15s; `tmux attach -t <run>` shows a live session in a window named `critic` with the bootstrap message submitted.
- [Manual] `cat <runtime>/<run>/bus.jsonl` shows `spawned` **followed by** `turn_start`.

---

## Ticket 4: `send` (Doorbell) and `read`

**Status: DONE** — composer fixtures are literal captures from a live Claude Code v2.1.223 session, not approximations. The heuristic deliberately fails *open*.

#### Overview
Deliver instructions without pushing the payload through the keyboard, and let the orchestrator observe both deliberate replies and the raw screen the human sees.

#### Implementation Steps

1. **`send` command**
   ```
   agentctl send <name> [<message> | --file <path> | -] [--run <id>]
                        [--no-enter] [--force] [--queue] [--wait-idle 120]
   ```
   Doorbell sequence:
   1. Write the payload to `inbox/NNNN.md` — **always first**, before any terminal interaction.
   2. Readiness check (step 2). Default blocks up to `--wait-idle`; `--queue` returns immediately with status `queued` (exit 3); `--force` skips the check.
   3. `backend.send(handle, doorbell, enter=not no_enter)` where the doorbell is a single line with no newlines:
      `[orchestrator] new instruction: <relative-path-to-inbox-file>`
   4. Append `message_sent` carrying the inbox path.

2. **Readiness — `is_ready(...) -> tuple[bool, str]`. Three gates, all must pass.**
   - **State gate:** derived state is `idle` or `awaiting_human` (never `busy` or `dead`).
   - **Copy-mode gate (N1):** `backend.in_mode(handle)` must be False. When the human presses `Ctrl-b [` to scroll back through an agent's output, the pane enters copy-mode and `send-keys` is interpreted **by copy-mode** — the text never reaches Claude's composer, and it fails **silently, precisely when the human is inspecting that agent**, which is the scenario this framework exists to support. **Refuse** with reason `copy_mode`; do **not** auto-`send-keys -X cancel`, which would yank the human's scroll position out from under them mid-read.
   - **Human gate:** `backend.capture(handle, 6)`; report not-ready if the input row appears to hold pending human text. Implement as one clearly-named isolated function `_input_row_looks_busy(screen: str) -> bool`, with a docstring stating plainly that it is a best-effort heuristic over TUI output and may break when the TUI changes.

3. **`read` command**
   ```
   agentctl read <name> [--outbox] [--screen N] [--since <seq>] [--json]
   ```
   - `--outbox` (default): structured messages the agent deliberately wrote — the reliable channel.
   - `--screen N`: `capture-pane` of the last N lines, so the orchestrator can see what the *human* said in that window and stay coherent.
   - `--json` for machine consumption; human-readable text by default.

4. **Worker-side reply path** — `agentctl reply --status <reply|question|blocked>`, body on stdin, run/agent/runtime from the environment (N2). Writes the outbox file and appends the matching event.

5. **Tests — `tests/agent_tabs/test_send.py` (new)**
   - Inbox file is written even when `backend.send` raises — the payload must survive terminal failure.
   - Doorbell text contains **no `\n`** for a multi-line, multi-paragraph payload.
   - `--no-enter` results in `backend.send(..., enter=False)`.
   - A `busy` agent with `--queue` returns exit 3 and performs **zero** backend sends, with the inbox file still on disk.
   - **Copy-mode:** `FakeBackend.in_mode = True` on an otherwise `idle` agent yields not-ready with reason `copy_mode`, zero sends, and no `send-keys -X cancel`.
   - `read --outbox --since` filters correctly; a malformed outbox file is returned flagged, not dropped.

#### Explicit Constraints & Warnings
- **Never send the payload as keystrokes.** The doorbell is a pointer. This is the invariant that makes a mangled keystroke cosmetic rather than a lost instruction — with the single exception of bootstrap, handled in T3 step 6.8.
- **The doorbell line must never contain a newline.** Collapse all whitespace runs to single spaces before sending.
- **Do not** make `--force` the default or use it in framework-internal paths. It exists as a human escape hatch and is honestly racy.
- **Do not** parse replies out of `capture-pane`. Screen scraping is observation only; every machine-consumed reply comes from the outbox.
- Keep the TUI heuristic in exactly one function — inlined twice means a future Claude Code release breaks the framework in two places.
- Test functions fully annotated.

#### Acceptance Criteria
- [Automated] A 5000-character multi-paragraph message produces text handed to `backend.send` under 300 characters containing no `\n`.
- [Automated] With `backend.send` raising `BackendError`, the inbox file exists afterwards and a `type=error` event was recorded.
- [Automated] A `busy` agent with `--queue` triggers zero `backend.send` calls.
- [Automated] An agent in copy-mode is refused with reason `copy_mode` and zero sends.
- [Manual] With a live agent, `agentctl send critic "summarise your role" --no-enter` places the doorbell in the composer **without submitting**; pressing Enter causes the agent to read the inbox file and act.
- [Manual] Scroll a live agent's pane into copy-mode, then `agentctl send` — it refuses with `copy_mode` and the scroll position is undisturbed.

---

## Ticket 5: `wait` — Predicate Tail Over the Bus

**Status: DONE**. Deviations: `status` dropped from the predicate grammar (it could only ever match nothing, and for a blocking call that is indistinguishable from "still working" — it is now a hard error pointing at `type=`); `wait_for_event` refactored onto `BusTail` rather than left as a second, independently-drifting tail implementation.

#### Overview
An event-driven block instead of polling. Run under background Bash, `wait` exits the moment a matching event lands and the harness re-invokes the orchestrator.

#### Implementation Steps

1. **`wait` command**
   ```
   agentctl wait --until '<predicate>' [--run <id>] [--timeout 900] [--from-seq N] [--json]
   ```
   Exit codes: `0` match (event printed as JSON to stdout), `2` timeout, `1` usage/other error.

2. **Predicate grammar — deliberately dumb.** Comma-separated `key=value`, ANDed; keys limited to `agent`, `type`, `status`; values may use `|` for alternation:
   ```
   agent=critic,type=reply
   type=question|blocked
   ```
   Parse with `str.split` — not a regex engine, and never `eval`. Reject unknown keys with a usage error naming the valid ones.

3. **Tailing (M3, accepted portion).** Start from `--from-seq` (default: current end of log), then poll for new content at 250 ms. **Track a byte offset and `seek` to it each tick** rather than re-reading the file. Handle the file not existing yet; handle a partially-written final line by re-reading it next tick rather than treating it as corrupt.

4. **Watermark helper** — `agentctl seq --run R` prints the current max seq, so an orchestrator can capture a watermark *before* sending and wait from it, closing the race where a reply arrives between `send` and `wait`.

5. **Tests — `tests/agent_tabs/test_wait.py` (new)**
   - `agent=critic,type=reply` matches neither a `reply` from another agent nor a `turn_end` from `critic`.
   - `type=question|blocked` matches both.
   - An event appended *before* `wait` starts does not match under the default watermark.
   - Timeout returns exit 2 within the window (1s timeout) with empty stdout.
   - An unknown predicate key exits 1 with a message naming valid keys.
   - The byte-offset tail returns each new event exactly once across 50 sequential appends.

#### Explicit Constraints & Warnings
- **Never `eval` the predicate.** It may one day carry text originating from an agent.
- **Do not default `--from-seq` to 0.** Matching historical events makes `wait` fire instantly and breaks orchestration in a way that looks like success.
- **Do not** add a general-purpose expression language. Two operators is the feature; a workflow needing more calls `wait` twice.
- `wait` must be safe to run concurrently — it opens the log read-only.
- Test functions fully annotated.

#### Acceptance Criteria
- [Automated] A thread appending a matching event after 300 ms causes `wait` to return 0 with the correct event JSON on stdout.
- [Automated] Timeout returns exit 2 with empty stdout.
- [Automated] A pre-existing matching event does not satisfy a default `wait`.
- [Automated] 50 sequential appends are each yielded exactly once by the offset-based tail.
- [Manual] `agentctl wait --until 'type=turn_end' --timeout 60 &`, then typing into a live agent's window, causes the backgrounded command to exit 0 and print the event.

---

## Ticket 6: `list`, `status`, `close`, `reap` — Reconciliation and Teardown

**Status: DONE** — signed off after manual verification against live tmux.

Deviations accepted during implementation:
- Reconciliation keys idempotency on *the absence of an `exit` event*, not on derived state. `error` also derives to `dead`, so the ticket's "non-dead agents" rule would permanently exclude a live agent after one failed keystroke.
- `reap` ships as `[--apply] [--all] [--dry-run]`. The ticket's flag list was internally inconsistent — dry-run as the default leaves `--dry-run` meaningless and nothing to make it act. `--dry-run` wins over `--apply` when both are given.
- `list` reports total outbox count, not "unread": nothing records what the orchestrator has read, by design (`read --since` puts that on the caller).
- `validated_worktree()` split out of `remove_worktree()` so callers validate *before* acting; `main_checkout()` added because git refuses to remove the worktree it is standing in.

#### Overview
Make liveness observable and teardown reliable. Orphaned agents in a detached tmux session burn tokens invisibly; this is the defence, and it ships now rather than later.

#### Implementation Steps

1. **`list`** — table of `name, state, model, handle, uptime, unread-outbox`. Before rendering, **reconcile**: for each non-`dead` agent, call `backend.alive(handle)`; if the window is gone, append `exit` with `{"reason":"window_vanished"}`. tmux is the authority on liveness; the bus is the authority on meaning.

2. **`status <name>`** — full `meta.json`, derived state, last 15 events, unread outbox count. **Additionally surface a distinct hint when an agent has been `busy` with no `turn_end` for more than N seconds (default 300)** — this is what a worker deadlocked on an unattended permission prompt looks like, and the orchestrator otherwise cannot distinguish it from "thinking hard" (H2).

3. **`close <name> [--force] [--timeout 30]`**
   Graceful path so the transcript flushes: `backend.send(handle, "/exit", enter=True)` → await `exit` up to `--timeout` → `backend.kill(handle)`. `--force` goes straight to kill. Either path then removes the recorded worktree and appends `exit` if the hook did not.

   **The graceful path is best-effort; the timeout is the real guarantee (M4).** With `-l`, `/exit` is typed literally into the composer — correct only if the composer is focused and empty. Mid-turn, in copy-mode, or with a dialog open, it lands wherever focus is and the path silently degrades to the kill. Document this so nobody later "fixes" it by extending the timeout.

4. **`reap [--all] [--dry-run]`** — sweep for non-`dead` agents whose handle is not alive, worktrees under `runtime/worktrees/` with no live agent, and (with `--all`) the tmux session once empty. **Default output is dry-run semantics** — say exactly what would be removed; require the flag to act.

5. **`close-run [--force]`** — `tmux kill-session -t <run>` plus worktree cleanup for every agent. The atomic teardown that motivated one-session-per-run.

6. **Tests — `tests/agent_tabs/test_lifecycle.py` (new)**, all `FakeBackend`.
   - `list` appends `exit` for a vanished handle; a second `list` appends no duplicate.
   - `close` sends `/exit` before `kill`; `--force` skips the send.
   - `close` removes a recorded worktree.
   - `reap` without `--all` reports but does not delete.
   - `status` flags an agent `busy` beyond the threshold with no `turn_end`.

#### Explicit Constraints & Warnings
- **Reconciliation must be idempotent.** `list` in a loop must not append an `exit` per call.
- **Never `git worktree remove` a path outside `<runtime>/worktrees/`.** Validate the path is a descendant of the runtime root before any removal. A bug here deletes user work.
- **Do not** make `reap` destructive by default.
- If the orchestrator ever runs inside the tmux session (a later iteration), `close-run` would kill itself. Leave a comment marking that as a known gap rather than half-implementing a guard.
- Test functions fully annotated.

#### Acceptance Criteria
- [Automated] Three `list` calls against a vanished handle produce exactly one `exit` event.
- [Automated] `close` on an agent with `worktree: null` performs zero git calls.
- [Automated] A `meta.json` with a worktree path of `/tmp/evil` (outside the runtime root) causes `close` to raise and perform **no** removal.
- [Automated] `status` reports the stalled-turn hint for a `busy` agent past the threshold.
- [Manual] With two live agents, `agentctl close-run` leaves `tmux ls` free of the run's session and `git worktree list` free of runtime worktrees.

---

## Ticket 7: Protocol Documents and Orchestrator Entry Point

#### Overview
The two documents that make the framework usable by an agent rather than by a human reading `--help`, plus the convenience wrapper and test-runner wiring.

#### Implementation Steps

1. **`.agent/skills/agent-tabs/SKILL.md`** — orchestrator-facing protocol. Frontmatter `name: agent-tabs` plus a `description:` matching the style of sibling skills in `.agent/skills/`. Content:
   - Mental model: tmux session = run, window = agent — with the **terminology warning** that a tmux session is not a Claude session.
   - The verb surface, one worked example each.
   - The canonical round trip:
     ```
     WM=$(agentctl seq --run R)
     agentctl spawn critic --role <skill> --run R
     agentctl send critic --file brief.md --run R
     agentctl wait --until 'agent=critic,type=reply|question|blocked' --from-seq $WM --run R   # background
     agentctl read critic --outbox --run R
     agentctl close critic --run R
     ```
   - `wait` runs under **background Bash**, never polled in a loop.
   - When state is `awaiting_human`, the orchestrator **stops and tells the human which window to look at** — it must not answer on the human's behalf.
   - **Settings layering** (M2): what a worker inherits by default and what `--isolated-settings` changes.
   - **Runtime root** lives outside the repo by default; the tree is disposable and bakes absolute paths.

2. **`.agent/skills/agent-tabs/WORKER.md`** — injected into every spawned agent alongside its role skill. Keep it **short**; it costs tokens in every session.
   - "You are running in a tmux window. A human can see this window and may type to you directly. Both the human and an orchestrator can address you."
   - **Check your inbox at the start of every turn** — the failsafe that makes a lost keystroke harmless.
   - How to reply: `agentctl reply --status reply|question|blocked`, body on stdin, and when to use each status. **Identity comes from the environment — do not pass `--run`/`--agent` yourself** (N2).
   - "Never assume the orchestrator is watching your screen. Anything it must know goes through `reply`."
   - Do not run `spawn`, `close`, or `reap`. Workers do not manage workers.

3. **Convenience wrapper — `scripts/agentctl`** — executable one-liner: `exec python3 "$(dirname "$0")/../.agent/skills/agent-tabs/agentctl.py" "$@"`. POSIX-sh compatible; no bashisms (macOS bash is 3.2).

4. **~~`scripts/test.sh` — add a tmux block (M1).~~ SUPERSEDED.** The original instruction was to wire `pytest -m tmux -ra` into the host repository's test runner. That is backwards: it makes the host repo's pipeline depend on the tool, which is the coupling this iteration exists to avoid, and it does not survive extraction. It was also unbuildable as written — T2 deliberately replaced M1's marker with `pytest.mark.skipif` so the tool needs no host pytest configuration, and `testpaths` excludes `.agent/` anyway.

   **Instead: the tool carries its own gate.** `.agent/skills/agent-tabs/test.sh`, POSIX sh, self-contained. Requires only `pytest`; runs `ruff` and `mypy --strict` when they are importable and reports them as skipped when they are not. Honours `$AGENTCTL_PYTHON`. Nothing in the host repository references it.

5. **README section** in `SKILL.md`: the `brew install tmux` prerequisite, `Ctrl-b <n>` / `Ctrl-b d` basics, and a pointer to iTerm's `tmux -CC` mode which renders windows as native iTerm tabs.

#### Explicit Constraints & Warnings
- **No CVviewer vocabulary anywhere.** No *ticket*, *sprint*, *iteration*, or role names from `.agent/skills/`. Examples use placeholders like `reviewer` / `implementer`. This is the genericity contract — the framework is extracted to its own repo later, and coupling introduced now becomes a painful diff then.
- **Do not rewrite `.agent/WORKFLOW.md`.** That is the next iteration and needs the skeleton proven first.
- Test functions fully annotated.

#### Acceptance Criteria
- [Automated] A test greps `SKILL.md`, `WORKER.md`, and `agentctl.py` for case-insensitive `ticket`, `sprint`, `cvviewer` and asserts zero matches — the genericity contract encoded as a test rather than an intention.
- [Manual] `./scripts/agentctl list` runs identically from the repo root and from a subdirectory.
- [Manual] `.agent/skills/agent-tabs/test.sh` passes standalone, from outside the repository, and with tmux absent prints the skip note rather than failing. The host repository's `scripts/test.sh` is **unchanged**.
- [Manual] End-to-end: spawn two agents with different roles, `send` distinct instructions, watch both in `tmux attach`, type a follow-up into one as the human, confirm `agentctl read <name> --screen 40` shows that exchange, then `close-run` and confirm clean teardown.

---

## Ticket 8: `Viewer` Plugin — Reveal a Spawned Agent Without a Manual Attach

**Status:** Not started

#### Overview
Today `spawn` leaves every window detached; a human only sees an agent after manually running `tmux attach` or `tmux -CC attach` (`SKILL.md:61-70`). This ticket adds an optional, swappable "viewer" step that runs right after a window is created, so e.g. an iTerm user can get a live tab per agent automatically — without hard-wiring iTerm into `spawn` or into the `Backend` protocol, which must stay terminal-emulator-agnostic (it is also driven by `FakeBackend` in every non-tmux test).

Inspiration: `~/Library/CloudStorage/GoogleDrive-makarezp1@gmail.com/My Drive/cv-builder/scripts/launch-agents.sh` already does the useful part of this manually — it drives iTerm via `osascript` to open one new tab per agent, `cd`s into place, and types a bootstrap prompt. This ticket generalises the "open a tab and attach" half of that script into a pluggable `Viewer`, independent of `Backend`. Reusing that script's own approach (`claude --model ... ; delay ...`) is explicitly **not** in scope — this framework already has a real readiness handshake (T3); the new viewer only has to attach a terminal to an *existing* tmux window, never re-launch or re-bootstrap the agent.

#### Implementation Steps

1. **Define the protocol** — in `agentctl.py`, next to the `Backend` protocol (`agentctl.py:566-588`), add:
   ```python
   @runtime_checkable
   class Viewer(Protocol):
       def reveal(self, run: str, handle: str) -> None: ...
   ```
   `reveal` takes only the tmux run id and window handle — nothing viewer-specific should leak into `spawn_agent`'s signature. A viewer that cannot do its job (program not installed, wrong OS, `osascript` failure) must raise `ViewerError` (new exception, subclass of `AgentTabsError`, mirroring `BackendError`) — it must **never** raise a *different* exception type, so the one `except` clause in step 4 stays exhaustive.

2. **`NullViewer`** — `reveal` is a no-op. This is today's behaviour (manual attach) and stays the default; adding the plugin must not change any existing test's expectations for `spawn` without `--viewer`.

3. **`ItermTabViewer`** — the one real implementation this ticket ships.
   - Opens a **new iTerm tab in the current window** (not a new OS window) and runs a **plain `tmux attach`**, not `tmux -CC`:
     ```
     TMUX= tmux attach -t =<run> \; select-window -t <handle>
     ```
     This is a normal tmux client attach + jump-to-window, so it works whether the run has one agent or ten, and does not depend on iTerm's tmux control-mode integration (`tmux -CC`) at all — control mode attaches to the *whole session* as a batch of native tabs, which is a different mode this ticket deliberately does not build (see the SKILL.md's own `-CC` note, which remains the documented manual alternative).
     - **The target must be `=<run>` (exact match), not bare `<run>`.** `TmuxBackend._target` (`agentctl.py:635-638`) exists specifically because a bare name silently resolves to whichever session matches first — e.g. `tmux attach -t cvv` can drop the human into `cvv-hotfix` while `select-window -t <handle>` still (correctly, since window ids are server-global) jumps to the right window, landing them attached to the *wrong session* showing the *right* window. Reuse `_target` itself (make it a module-level function both `TmuxBackend` and `ItermTabViewer` call) rather than re-deriving the `=` rule a second time.
     - **`TMUX= ` prefix is required**, not decorative: if `agentctl` (and therefore the new iTerm tab, which inherits its environment) is itself run from inside a tmux client, `$TMUX` is set and `tmux attach` refuses with *"sessions should be nested with care"* — turning every `reveal` call into a `ViewerError` the moment the orchestrator itself runs under tmux.
   - Two independent escaping layers, both required, neither optional (this is the same class of defect as B1 in `agent-tabs-iteration-1-review.md`, and must be tested the same way — round-trip, not "contains the substring"):
     1. `shlex.quote` on `=<run>` (the whole target token, not just `run`) and on `handle`, when building the `tmux attach ...` command string — that string is executed by the *shell running inside the new iTerm tab*, exactly like `launch-agents.sh`'s `write text` targets are shell command lines, not argv lists. The `\;` tmux command separator is a **literal**, written as-is (or as `';'`) — it must never be passed through `shlex.quote` itself, only the tokens around it.
     2. AppleScript string-literal escaping of the *whole* resulting command (backslash, then double-quote) before it is embedded in the `write text "..."` line — reuse the exact escaping rule `launch-agents.sh`'s `esc()` helper implements (`~/Library/CloudStorage/GoogleDrive-makarezp1@gmail.com/My Drive/cv-builder/scripts/launch-agents.sh:44`), since `run` (user-supplied, e.g. via `--run`) is **not** validated against `AGENT_NAME` (`agentctl.py:780`) or any pattern today, so it may legitimately contain quotes or backslashes.
   - Build the full AppleScript as one string:
     ```applescript
     tell application "iTerm"
       activate
       if (count of windows) = 0 then create window with default profile
       tell current window
         set s to (current session of (create tab with default profile))
         tell s
           write text "<escaped tmux attach command>"
         end tell
       end tell
     end tell
     ```
   - Run it via **stdin**, not `-e`, to avoid AppleScript's own line-splitting quirks with multi-line `-e` scripts: `subprocess.run(["osascript", "-"], input=script, text=True, capture_output=True, check=False)`.
   - Accept an injectable runner for testability, mirroring `TmuxBackend`'s own `_run`/`_exe` split (`agentctl.py:618-627`): `ItermTabViewer(runner: Callable[[str], subprocess.CompletedProcess[str]] | None = None)`, defaulting to the real `subprocess.run` call above. A non-zero exit or a missing `osascript` binary (`shutil.which("osascript") is None`) raises `ViewerError` carrying stderr — never a bare `subprocess.CalledProcessError` or `FileNotFoundError`.

4. **Registry — mirror `get_backend`'s actual signature (`agentctl.py:757-768`), not just its shape.** `get_backend` is `get_backend(name: str | None = None, config: Config | None = None)`, with `cfg = config if config is not None else Config.from_env()` — both parameters optional, `config` defaulted and resolved internally when omitted. Match that exactly:
   ```python
   VIEWERS: dict[str, type[Viewer]] = {"none": NullViewer, "iterm-tab": ItermTabViewer}


   def get_viewer(name: str | None = None, config: Config | None = None) -> Viewer:
       cfg = config if config is not None else Config.from_env()
       chosen = name or cfg.viewer
       try:
           factory = VIEWERS[chosen]
       except KeyError as exc:
           raise ViewerError(f"unknown viewer {chosen!r}; available: {', '.join(sorted(VIEWERS))}") from exc
       return factory()
   ```
   Add `ENV_VIEWER = "AGENT_TABS_VIEWER"` and `DEFAULT_VIEWER = "none"` next to the existing `ENV_BACKEND`/`DEFAULT_BACKEND` constants (`agentctl.py:52-55`), and a `viewer: str` field on `Config` (`agentctl.py:74-97`), read in `Config.from_env` exactly like `backend` is today. **Do not** add `--viewer` to the shared `common` parser used by every subcommand — only `spawn` creates a window worth revealing, so `--viewer` belongs on `spawn_parser` alone (`agentctl.py:1621-1633`), next to `--backend`'s existing per-command precedent.

5. **Wire into `spawn_agent`** (`agentctl.py:1104-1191`). Add a `viewer: Viewer = NullViewer()` keyword parameter. Call `viewer.reveal(paths.run, handle)` **immediately after `handle = backend.open(...)`** (right after `agentctl.py:1168`), *before* the `wait_for_event` block — so the human can watch the agent's own boot handshake happen live in the new tab, rather than only seeing it once already idle. The call site sits inside `spawn_agent`'s own `try:` block (opens at 1143), whose `except Exception` handler (1192) kills the window, removes the worktree, and re-raises — so the reveal call must **never let anything propagate out of it**, not merely anything typed `ViewerError`:
   ```python
   try:
       viewer.reveal(paths.run, handle)
   except Exception as exc:  # noqa: BLE001 - a cosmetic step must never fail a spawn
       log.warning("viewer %r could not reveal %s: %s", viewer, handle, exc)
   ```
   Catching only `ViewerError` here is a real defect, not a stylistic choice: it only protects against a viewer that already behaves, which is not the failure this catch exists for. An `AttributeError` in the AppleScript builder, a `TypeError` from a misbehaving injected runner, or an `OSError` `ItermTabViewer` forgot to wrap would otherwise propagate straight into `spawn_agent`'s cleanup handler and **kill a healthy agent and its worktree over a cosmetic failure**. `ViewerError` remains the type a well-behaved viewer *should* raise for diagnosis (it carries stderr, etc.) — correctness at this call site must not depend on viewers honouring that convention. This mirrors the reasoning already used twice elsewhere in this file: the hook subcommand's exit-0-always rule, and `spawn_agent`'s own cleanup handler.

   Note also that `reveal` runs before the readiness handshake: if the spawn subsequently times out or fails, the window (and the iTerm tab attached to it) is killed out from under the human. This leaves an orphaned iTerm tab whose `tmux attach` has simply exited — cosmetic, not a token-burning orphan the way a live but forgotten agent would be (Ticket 6's concern), and accepted as-is for this ticket. Do not build teardown for it.

6. **CLI plumbing** — `_cmd_spawn` (`agentctl.py:1770-1788`) passes `viewer=get_viewer(args.viewer, config)`. Add `spawn_parser.add_argument("--viewer", help="viewer name (default: none); overrides $AGENT_TABS_VIEWER")`.

7. **Tests — `tests/test_viewer.py` (new)**, plus a few additions to `tests/test_spawn.py`.
   - **Quoting round-trip, done the B1 way:** build a viewer with a recording runner, call `reveal` with a `run` value containing a space, a double quote, and a backslash (e.g. `My "Run"\Two`) and a handle like `@3`. Assert the exact tmux command embedded in the captured AppleScript, once **both** unescaping steps are undone (AppleScript string-literal unescape, then `shlex.split`), equals `["TMUX=", "tmux", "attach", "-t", "=My \"Run\"\\Two", ";", "select-window", "-t", "@3"]` — or equivalent exact-argv assertion. Note the leading `"TMUX="` token: `shlex.split` treats the env-var-clearing prefix as its own word (it does not understand shell assignment-prefix semantics), so an implementation that gets everything else right will still fail a test that forgets this token — build the expected list by running `shlex.split` over the real intended command line while writing the test, not by hand-transcribing it. Note the separator token: `shlex.split` resolves a shell-escaped `\;` to a bare `;`, not to `\;` — build the expected list by actually running `shlex.split` over the intended literal command during test-writing, don't hand-transcribe it, or the test will fail against a *correct* implementation and pass only if the separator is mangled into a literal backslash-semicolon (which breaks the `select-window` chain in real tmux). Also note the target is `=My "Run"\Two`, the exact-match form, not the bare run id. Asserting the script merely "contains the run id substring" passes on a broken version; do not weaken this, per the standing rule from B1.
   - `NullViewer().reveal(...)` is a no-op and returns `None` for any input, including nonsense strings.
   - `get_viewer("iterm-tab", config)` returns an `ItermTabViewer`; `get_viewer("nonsense", config)` raises `ViewerError` naming the valid choices.
   - `get_viewer(None, config)` with `$AGENT_TABS_VIEWER=iterm-tab` in the environment returns an `ItermTabViewer`; with nothing set, returns `NullViewer` (the default-off contract from the design decision above).
   - A viewer whose runner returns a non-zero exit code causes `reveal` to raise `ViewerError` carrying the captured stderr.
   - In `tests/test_spawn.py`: extend the existing `FakeBackend`-driven spawn test (pattern at `test_spawn_reports_identity_through_the_environment`, `agentctl.py`/`tests/test_spawn.py:137`) with a small local test double implementing `Viewer` (recording `reveal` calls) — **not** a new shipped `FakeViewer`, since only `spawn` consumes `Viewer` today, unlike `Backend` which every command touches. Assert:
     - `spawn_agent(..., viewer=recorder)` calls `reveal(run, handle)` exactly once, with the handle `FakeBackend.open` returned.
     - A recorder whose `reveal` raises `ViewerError` does not prevent the spawn from completing successfully (the existing `wait_for_event`/bootstrap flow still runs and `spawn_agent` still returns a `meta`).
     - Omitting `viewer=` entirely (the CLI default) behaves exactly as today — no new call, no new attribute on `meta`.

8. **Update `SKILL.md`'s watch section (`SKILL.md:61-70`).** It currently presents `tmux -CC attach -t <run>` as "the intended way to watch a run," with no mention of a per-agent alternative. Add a short note presenting `-CC attach` and `--viewer iterm-tab` as two *mutually exclusive* ways to watch a run, and say plainly not to mix them within one run (a plain attach and a control-mode attach to the same session in the same iTerm window is a real footgun — see the constraint below). Ticket 7's genericity test (`agentctl.py`, `SKILL.md`, `WORKER.md` greeped for `ticket`/`sprint`/`cvviewer`) still applies to this edit — keep it generic.

#### Explicit Constraints & Warnings
- **`Viewer` must stay orthogonal to `Backend`.** It has no knowledge of tmux internals beyond a run id and an opaque handle string; it must not call `backend.*` methods directly, and `Backend` must not gain a `reveal` method. Keeping the roles-in-tmux abstraction and the how-does-a-human-see-it abstraction separate is the entire point of this ticket — collapsing them is the mistake to avoid.
- **This is not `tmux -CC`.** Do not attempt to detect or reuse an existing `tmux -CC` control-mode connection; `ItermTabViewer` always does a plain client attach. Mixing a plain attach and a control-mode attach to the same session in the same iTerm window is a real tmux/iTerm footgun and out of scope.
- **Never re-type the bootstrap or role prompt from the viewer.** That already happens through the T3 handshake and the T4 doorbell; a viewer that also "helpfully" types something into the pane risks colliding with, or duplicating, an in-flight doorbell keystroke.
- **`run` is attacker-adjacent, not just untrusted-in-theory.** It is a CLI argument with no validation today (unlike agent names, which are checked against `AGENT_NAME`). Treat it exactly like B1 treated the repo's own path: quote defensively, prove it with a round-trip test, never with a substring check.
- **Do not make `iterm-tab` the default.** Per the design decision behind this ticket: `spawn` without `--viewer` must behave exactly as it does today. This also keeps headless/CI use of `agentctl` (no display, no iTerm, possibly no `osascript`) working unchanged.
- **A viewer must never be able to fail a spawn.** The `spawn_agent` call site (step 5) catches `Exception`, deliberately broadly — not just `ViewerError` — because the whole point of the catch is to survive a viewer that misbehaves, not just one that behaves and raises the documented type. `ViewerError` is what a well-written viewer *should* raise for diagnosis; it is not what correctness may depend on.
- Test functions fully annotated — `mypy --strict` runs over `tests/` per the standing project rule (H1 in the review doc).
- macOS-only in practice (`osascript`, `iTerm`), but nothing in the `Viewer` protocol itself is macOS-specific — a future `TerminalTabViewer` (plain Terminal.app) or a Linux/`gnome-terminal` viewer is a one-`class` addition to `VIEWERS`, same as `iterm` would be for `Backend` (`SKILL.md`'s own aspiration, `agentctl.py:757`).

#### Acceptance Criteria
- [Automated] A `run` value containing a space, a double quote, and a backslash produces a captured AppleScript whose embedded tmux command round-trips via AppleScript-unescape + `shlex.split` to the exact expected argv (leading `"TMUX="` token, target `=<run>`, separator a bare `;` after `shlex.split`, per step 7) — not merely "contains" it.
- [Automated] The attach target is `=<run>`, never bare `<run>` — asserted separately from the round-trip test so a future edit can't silently drop the `=` while keeping the rest of the argv correct.
- [Automated] `spawn_agent` with no `viewer=` argument makes zero calls to any viewer and returns the same `AgentMeta` as before this ticket (regression guard against changing default behaviour).
- [Automated] `spawn_agent` with a `viewer` whose `reveal` raises **any** exception type — not just `ViewerError` (e.g. a bare `RuntimeError`) — still returns a successful `meta`. This is the AC that actually exercises T8-2; a test that only raises `ViewerError` would pass against the defective narrow-catch version too.
- [Automated] `get_viewer` resolution order matches `get_backend`'s, including the no-argument defaults: `get_viewer()` with no args reads `Config.from_env()`; explicit name wins over `$AGENT_TABS_VIEWER`, which wins over the `none` default.
- [Manual] `agentctl spawn reviewer --role <path> --run demo --viewer iterm-tab` opens a new iTerm tab in the current window, already attached to the right window, within a couple seconds of the command returning — no `tmux attach` typed by hand.
- [Manual] With two runs live (`demo` and `demo-hotfix`), spawning with `--viewer iterm-tab --run demo` attaches the new tab to `demo`, never `demo-hotfix`.
- [Manual] The same command with `--viewer` omitted behaves exactly as before: the window is created detached, nothing appears on screen.
- [Manual] Running `agentctl spawn ... --viewer iterm-tab` from inside an existing tmux client (i.e. with `$TMUX` set) still succeeds — the nested-session refusal is suppressed.

---

## Ticket 9: Stop `spawn` Silently Preferring `agy` Over `claude`

**Status:** Not started

#### Overview
`spawn_agent` picks a worker binary with `binary = claude_binary or shutil.which("agy") or shutil.which("claude")` (`agentctl.py:1261`) — on any machine with both `agy` (Antigravity CLI) and `claude` installed, `agy` silently wins even though the caller asked for neither explicitly. This was not a hypothetical: spawning an agent with `agentctl spawn viewer-impl --role ... --run ticket8 --model sonnet` (no `--binary`) on this machine picked `agy`, whose bootstrap path is a blind `time.sleep(1.5)` followed by an unconditional blank `backend.send(handle, "", enter=True)` (`agentctl.py:1304-1306`) — the exact "sleep-and-hope" pattern this framework's own `spawn` command exists to eliminate (`SKILL.md`'s spawn section: *"there is no sleep-and-hope"*). `agy` exited on its own within that 1.5s window (for a reason nothing in `agentctl` captured), tmux closed the now-empty window, and the blind `send-keys` a moment later failed with an opaque `can't find window: @123` — a message that names a tmux mechanics failure and says nothing about the real cause, `agy` itself refusing to start. Re-running with `--binary "$(which claude)"` explicitly worked immediately.

Two distinct problems, both in scope: (1) the *default* silently favors the binary that (as implemented today) is more likely to fail and offers no readiness handshake of its own, and (2) once it does fail, there is no information anywhere — not on stdout, not in `meta.json`, not in the error message — recording *which* binary was chosen, so the failure is far harder to diagnose than it needs to be.

#### Implementation Steps

1. **Flip the default precedence — `agentctl.py:1261`.** Change
   ```python
   binary = claude_binary or shutil.which("agy") or shutil.which("claude")
   ```
   to
   ```python
   binary = claude_binary or shutil.which("claude") or shutil.which("agy")
   ```
   `claude` is the binary this framework's readiness handshake (T3), doorbell (T4), and every hook in `write_settings` are built and tested against; `agy` is reached only as an explicit, opt-in fallback via `--binary agy` or `--binary "$(which agy)"`, never by silent default. Update the error message at `agentctl.py:1262-1263` (currently `"neither agy nor claude is installed or on PATH"`) to name `claude` first, matching the new precedence.

2. **Record which binary was actually used — new field on `AgentMeta` (`agentctl.py:1143-1152`).** Add `binary: str` (the resolved absolute path, not the raw `claude_binary` argument, so `meta.json` shows what actually ran even when resolution fell through `shutil.which`). Pass it into the `AgentMeta(...)` construction at `agentctl.py:1308-1318`. This is the same category of fix as the model/permission-mode fields that already exist there — a spawn's own record should be able to answer "what did this actually launch" without cross-referencing PATH state that may have since changed.

3. **Surface the choice at spawn time, not just after the fact.** `_cmd_spawn`'s success line (`print(f"{meta.name}\t{meta.handle}\t{meta.cwd}")`, near `agentctl.py:1921`) tells the caller nothing about which binary ran. Extend it to include the resolved binary, e.g. `print(f"{meta.name}\t{meta.handle}\t{meta.cwd}\t{meta.binary}")`, and update any test asserting the exact stdout format (`tests/test_spawn.py`) accordingly.

4. **Give the `agy` bootstrap path a diagnosable failure, since it still exists as an opt-in.** At `agentctl.py:1304-1306`, before the blind `send`, check `backend.alive(handle)`. If it is already `False` (the process exited during the sleep, as reproduced live), raise a `SpawnError` that says so explicitly — `f"agy exited on its own within {AGY_BOOT_DELAY}s of starting; last screen:\n{backend.capture(handle, 40)}"` — using whatever of `capture`'s last output is still available, rather than letting the blind `send-keys` fail with a generic tmux-mechanics message that names the wrong layer. This does not fix `agy`'s own instability (out of scope — `agentctl` does not own that binary) and does not turn the blind sleep into a real handshake (a deeper change, and `agy`'s own readiness signalling, if any, is unexplored) — it only makes the failure legible instead of opaque, matching the standing rule that a spawn which cannot be proven must fail with enough information to say why.

5. **Tests — extend `tests/test_spawn.py`.**
   - With both `shutil.which("agy")` and `shutil.which("claude")` monkeypatched to return paths, and no `--binary` given, assert the resolved binary is the `claude` path, not the `agy` one (the precedence flip's own regression guard — the previous behaviour must not silently come back).
   - `--binary` explicitly set to an `agy`-shaped path still takes that path unconditionally (precedence is a *default* only, not a removal of the option).
   - `meta.json` written by a successful spawn contains a `binary` field equal to the resolved path used to `backend.open(...)`.
   - A `FakeBackend` whose `alive(handle)` returns `False` immediately after `open()`, with a binary named `agy...`, causes `spawn_agent` to raise `SpawnError` mentioning `agy` and *not* to reach the blind `backend.send` call at all (assert zero entries were added to `FakeBackend.sends` for that handle).

#### Explicit Constraints & Warnings
- **This ticket does not touch `agy`'s own bootstrap mechanism beyond the liveness check in step 4.** Replacing the `sleep(1.5)` + blind `Enter` with a real event-driven handshake for `agy` is a larger change (it would need to know what, if anything, `agy` reports on startup) and is explicitly out of scope here — track it separately if `agy` becomes a first-class supported binary rather than an opt-in fallback.
- **Do not remove `agy` support.** The fix is precedence and diagnosability, not deletion — `--binary agy` (or an absolute path to it) must keep working exactly as it does today.
- **`--binary` explicit values must still win over everything.** Nothing in this ticket may make the flag less authoritative than the default; the precedence change only affects what happens when the caller specifies nothing.
- Test functions fully annotated — `mypy --strict` runs over `tests/` per the standing project rule.

#### Acceptance Criteria
- [Automated] With both `agy` and `claude` present on `PATH` and no `--binary` given, `spawn_agent` resolves to the `claude` path.
- [Automated] `meta.json` after a successful spawn contains a `binary` field naming the resolved path actually passed to `backend.open`.
- [Automated] A backend that reports the window as dead immediately after `open()`, combined with an `agy`-named binary, raises `SpawnError` naming `agy` and never calls `backend.send` for that handle.
- [Manual] On this machine (both `agy` and `claude` installed), `agentctl spawn <name> --role <path> --run <run>` with no `--binary` produces a `meta.json` whose `binary` field points at `claude`, and the handshake completes without the `can't find window` failure reproduced above.
- [Manual] `agentctl spawn <name> --role <path> --run <run> --binary agy` still attempts `agy` as before — the opt-in path is unchanged.

---

## Build Order

1. **T1** — nothing works without the bus. Write the concurrency test first, in the B3-corrected form.
2. **T2** — verify the three tmux behaviours *before* writing the adapter.
3. **T3** — the B1 quoting fix is the single highest-value line in the iteration.

**Stop here and evaluate.** T1→T3 is the slice that proves the core hypothesis: that `spawned` and `turn_start` fire reliably from a live TUI session. All three blockers lived in this slice. If the handshake holds, T4–T7 are mechanical.

4. T4 → T5 → T6 → T7.
5. **T8** is independent of T4–T7 — it only touches `spawn`'s window-creation path (step 5, after `backend.open`) and ships behind an opt-in `--viewer` flag. Build it any time after T3; it does not block or get blocked by T4–T7.
6. **T9** is also independent — a small, self-contained fix to `spawn`'s binary resolution (`agentctl.py:1261`), found live while spawning an agent to build T8. Build it any time after T3; it has no dependency on T8 and vice versa.

## Deferred Decisions

1. **Orchestrator placement.** Assumed **outside** tmux. Moving it to window 0 makes runs survive closing iTerm and makes the protocol symmetric, but changes how work starts and needs a self-kill guard in `close-run` (T6 leaves a marked gap). Decide before iteration 2.
2. **`bus.seq` sidecar** (M3). Deferred until append contention is measured. Revisit if a run exceeds ~10k events or hook writes visibly contend.
3. **`--no-enter` as the default for `send`.** Resolved: **keep Enter-by-default.** The inbox-first invariant makes a bad send recoverable, and requiring a human keypress per message would remove the orchestrator's ability to run an unattended round trip — the point of the framework. The one place this was genuinely at risk was the bootstrap doorbell, and the answer there is *confirm delivery* (H3), not *ask a human*.
