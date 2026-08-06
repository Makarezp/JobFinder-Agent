# Agent-Tabs — Iteration 1: Walking Skeleton

**Revision 2** — incorporates `agent-tabs-iteration-1-review.md` in full.
**Track:** Tooling / meta (not part of `sprint_v2_search_ledger.md`)
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
       mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
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
   def in_mode(self, handle: str) -> bool: ...      # copy-mode / any pane mode  (N1)
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
   argv = [sys.executable, str(AGENTCTL_ABS), "hook", ev,
           "--runtime", str(runtime_root), "--run", run, "--agent", name]
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

4. **`scripts/test.sh` — add a tmux block (M1).** After the existing Docker-gated integration block, add a parallel block gated on `command -v tmux`, running `pytest -m tmux -ra`, with a yellow skip message when tmux is absent — mirroring the Docker pattern already there.

5. **README section** in `SKILL.md`: the `brew install tmux` prerequisite, `Ctrl-b <n>` / `Ctrl-b d` basics, and a pointer to iTerm's `tmux -CC` mode which renders windows as native iTerm tabs.

#### Explicit Constraints & Warnings
- **No CVviewer vocabulary anywhere.** No *ticket*, *sprint*, *iteration*, or role names from `.agent/skills/`. Examples use placeholders like `reviewer` / `implementer`. This is the genericity contract — the framework is extracted to its own repo later, and coupling introduced now becomes a painful diff then.
- **Do not rewrite `.agent/WORKFLOW.md`.** That is the next iteration and needs the skeleton proven first.
- Test functions fully annotated.

#### Acceptance Criteria
- [Automated] A test greps `SKILL.md`, `WORKER.md`, and `agentctl.py` for case-insensitive `ticket`, `sprint`, `cvviewer` and asserts zero matches — the genericity contract encoded as a test rather than an intention.
- [Manual] `./scripts/agentctl list` runs identically from the repo root and from a subdirectory.
- [Manual] `./scripts/test.sh` completes all six steps; with tmux absent it prints the skip message rather than failing.
- [Manual] End-to-end: spawn two agents with different roles, `send` distinct instructions, watch both in `tmux attach`, type a follow-up into one as the human, confirm `agentctl read <name> --screen 40` shows that exchange, then `close-run` and confirm clean teardown.

---

## Build Order

1. **T1** — nothing works without the bus. Write the concurrency test first, in the B3-corrected form.
2. **T2** — verify the three tmux behaviours *before* writing the adapter.
3. **T3** — the B1 quoting fix is the single highest-value line in the iteration.

**Stop here and evaluate.** T1→T3 is the slice that proves the core hypothesis: that `spawned` and `turn_start` fire reliably from a live TUI session. All three blockers lived in this slice. If the handshake holds, T4–T7 are mechanical.

4. T4 → T5 → T6 → T7.

## Deferred Decisions

1. **Orchestrator placement.** Assumed **outside** tmux. Moving it to window 0 makes runs survive closing iTerm and makes the protocol symmetric, but changes how work starts and needs a self-kill guard in `close-run` (T6 leaves a marked gap). Decide before iteration 2.
2. **`bus.seq` sidecar** (M3). Deferred until append contention is measured. Revisit if a run exceeds ~10k events or hook writes visibly contend.
3. **`--no-enter` as the default for `send`.** Resolved: **keep Enter-by-default.** The inbox-first invariant makes a bad send recoverable, and requiring a human keypress per message would remove the orchestrator's ability to run an unattended round trip — the point of the framework. The one place this was genuinely at risk was the bootstrap doorbell, and the answer there is *confirm delivery* (H3), not *ask a human*.
