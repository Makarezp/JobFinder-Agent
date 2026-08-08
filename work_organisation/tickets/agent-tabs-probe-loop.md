# Agent-Tabs — Probe Loop (Iteration 2)

**Revision 4** — incorporates two rounds of defensive review **and a live spike** (`probe-spike`, Opus, 2026-08-08) that answered both open questions and found four defects. Sprint: `sprint_v3_agent_tabs_hardening.md`. See *Review dispositions* at the foot of this document.

> **T0 gates part of this ticket.** T0's live verification remains pending; T2's `dirty-composer` criteria must not begin until T0 is marked Done.

> **Read W11 before implementing any step.** Both prior revisions shipped confident, specific, wrong claims — and in round 2 every new defect was in text the *previous fix* introduced. Verify each specific against the source before acting on it.

**Track:** Tooling / meta (not part of archived `history/sprints/sprint_v2_search_ledger.md`)
**Depends on:** `history/tickets/agent-tabs-iteration-1.md` (shipped), `history/tickets/agent-tabs-codex-support.md` (shipped)
**Goal:** A self-improving conformance harness that measures whether `SKILL.md` and `WORKER.md` actually induce correct behaviour in real workers and orchestrators, records what it has already explored, and emits specs for what it finds.

## Context

`.agent/skills/agent-tabs/tests/` is ~2.7k lines against a 2.4k-line tool, and it is good. But it tests one half of every claim the protocol makes.

`agentctl` *sends* a doorbell — proven. A worker *re-reads its inbox at the start of every turn* — unproven, and unprovable by pytest, because the receiving end is a language model reading prose. The same asymmetry holds for the orchestrator: `SKILL.md` forbids polling `wait`, forbids parsing replies out of `--screen`, and requires stopping when an agent is `awaiting_human`. Nothing measures whether an orchestrator that reads that document complies.

Those documents are the product. This iteration builds the instrument that measures them.

### The two metric families

| Family | Question | Instrument |
|---|---|---|
| **Conformance** | Is the documented behaviour produced? | nonce round-trip, pass rate over N trials |
| **Fluency** | Is producing it *smooth*? | counters derived from `bus.jsonl` |

A run can be 10/10 conformant and still take five turns, three clarifying questions and a human rescue to do a one-turn job. Conformance says the doc is followed; fluency says it is good.

### Architecture

```
Layer 4  TRIAGE      oracle role + spec emission          T7
Layer 3  MEMORY      journal.jsonl -> COVERAGE.md         T6
Layer 2  MEASURE     conformance briefs (T4), fluency + orchestrator checks (T5)
Layer 1  SUBSTRATE   probe.py, sut, assert, nonce (T1), puppet (T2), claims (T3)
```

### Decisions

| Decision | Choice |
|---|---|
| Harness location | `.agent/skills/agent-tabs/probe/` — **inside** the tool dir; a framework ships its own conformance suite |
| Language | Python 3.11+, stdlib only, `mypy --strict` clean — same constraint as `agentctl.py` |
| Default counterparty | **Real worker** (`--model haiku`). Not a protocol mock — see Warning W1 |
| Puppet scope | Timing and fault states only; holds no protocol semantics |
| Grading | **Mechanical wherever possible** (nonce sets, event counts, exit codes). LLM judgement is a last resort, not the default |
| SUT isolation | Separate `--runtime` root **and** separate tmux session per trial |
| Assertion source | `bus.jsonl`, `inbox/`, `outbox/`, `tmux`, exit codes — **never** `agentctl list`/`status`/`read` |
| Ticket destination | `work_organisation/probe/` — quarantined from human-authored tickets |
| Loop closes at | The spec. **No auto-fix.** See Warning W2 |

### Deferred decisions

| Item | Why deferred |
|---|---|
| Blind pairwise A/B judging of doc revisions | Needs ~20 full-loop runs per arm to beat variance. Build after T5 gives mechanical fluency deltas — those may be sufficient on their own |
| Free adversarial exploration (unbounded prober) | Lowest yield per token. Sources 1–3 in T3/T6 are systematic and unexhausted |
| Model-capability control (haiku vs sonnet on the same brief) | Ledger carries the `model` field from T4 so this is a query later, not a migration |
| Scripted-human interference (`human.sh`) | Depends on T2's puppet proving the injection pattern first |

---

## Explicit Constraints & Warnings (whole iteration)

These apply to every ticket below. **They were reviewed and are not to be re-litigated.**

- **W1 — Do not build a protocol-speaking mock worker.** A mock that correctly reads its inbox proves only that the author wrote it to. Worse, it becomes a second implementation of the protocol that silently drifts from `WORKER.md`, leaving the suite green while docs and runtime disagree — on a project whose deliverable *is* the docs. `puppet.py` (T2) exists solely to hold timing states a real model cannot be asked to hold, and must contain **no** inbox-reading or reply-emitting logic.

- **W2 — The loop stops at the spec. Do not implement auto-fix.** A patch applied by agents running *on* agent-tabs can corrupt the substrate that would have detected the bad patch, and every later probe result becomes untrustworthy without anyone knowing when it started.

- **W3 — Assertions read ground truth only.** If a probe asserts via `agentctl list` or `agentctl status`, a bug in those commands hides itself. `probe/lib/ground.py` is the only module permitted to parse `bus.jsonl` and the mailbox tree, and it may import from `agentctl.py` **only these five inert data carriers**: `EventType` (`:219`), `Event` (`:256`), `OutboxStatus` (`:378`), `OutboxMessage` (`:392`), `RunPaths` (`:168`). All five are frozen dataclasses or enums — they carry data, they are not the parsers under test. What W3 forbids is reusing `read_events`, `read_outbox` or `derive_state`, which are exactly the read paths a probe exists to check.

- **W4 — `tests/test_genericity.py` will scan everything you add.** `test_the_host_repository_name_appears_nowhere_in_the_tool` rglobs every `.py` and `.md` under `.agent/skills/agent-tabs/` and fails on the host repository's name. Artifact paths captured from this machine contain it. Therefore: **artifact paths are written only to `.jsonl` files** (not scanned) and never interpolated into a `.md`. `COVERAGE.md` (T6) must reference artifacts by journal entry id, never by absolute path. Verify by running `test.sh -k genericity` after every ticket.

- **W5 — There is no `awaiting_human` event.** `EventType` is exactly: `spawned`, `turn_start`, `turn_end`, `message_sent`, `reply`, `blocked`, `question`, `exit`, `error`, `__unknown__`. `awaiting_human` is an `AgentState` derived by `derive_state()`. Fluency counters must count `question` + `blocked` events, not a nonexistent event type.

- **W6 — `spawn` has no channel for passing arguments or environment to a worker.** There is no `--cmd` flag; the flags are `--binary` and `--provider`. Beyond that:
  - `_worker_argv` (`:1315-1363`) builds the launch vector **entirely from provider templates**. A caller cannot contribute an argument.
  - The window environment is hardcoded to exactly three keys — `env = {ENV_RUNTIME: ..., ENV_RUN: ..., ENV_AGENT: name}` (`:1440`) — and tmux windows do not inherit the caller's environment. There is no arbitrary-env channel.
  - `_known_provider` (`:1273-1282`) **substring-matches** `codex`, `agy` and `claude` against the executable's basename. A binary named `claude-puppet` silently lands on the Claude launch vector.

  Consequence for T2: any per-invocation state must be encoded **in the executable itself** — one thin wrapper script per state — and the wrapper's filename must contain none of those three substrings.

- **W6b — `spawn` proves liveness in two stages, and kills the window if either fails.** For any non-Codex provider:
  1. `:1477` blocks on a `SPAWNED` event within `--spawn-timeout` (default 60s), raising otherwise.
  2. If the doorbell is enabled, `_bootstrap` (`:1528-1534`) rings it and blocks on `TURN_START` within `--bootstrap-timeout`, **twice**, then raises `never started a turn after two bootstrap attempts`.

  The `except` arm at `:1488-1493` calls `backend.kill(handle)` on any exception — this is C002 working exactly as documented, and it will fire on a puppet. Therefore **every puppet state must emit `spawned` as its first action**, and `spawn_puppet` must pass `--no-doorbell` (`:1961`), which is the only flag that skips `_bootstrap` (guarded at `:1480`).

- **W7 — `test.sh` runs `ruff check` and `mypy --strict` over the whole tool directory.** Everything added under `probe/` inherits that gate. Full annotations on every function, including test functions (this was review item H1 in Iteration 1 and still holds).

- **W8 — `./test.sh` with bare `python3` silently skips every gate on this machine.** `ruff`, `mypy` and `pytest` are installed in the repo's `.venv`, not in `/opt/homebrew/bin/python3`, and `test.sh` reports missing tools as a yellow *skip* rather than a failure. An agent that runs `./test.sh`, sees "Skipping lint — ruff not available", and concludes the code is clean has verified nothing. Always run:
  ```sh
  AGENTCTL_PYTHON="<repo>/.venv/bin/python" ./test.sh
  ```
  **Verified baseline at commit `1bb37a7`, before any work in this iteration: 187 passed, 2 skipped (both `AGENT_TABS_E2E`-gated), ruff clean, `mypy --strict` clean over 11 source files.** Any deviation from that baseline is caused by your change, not by pre-existing debt.

- **W9 — tmux 3.7b is installed on this machine.** The Iteration 1 review's `[UNVERIFIED]` findings were written when it was not; tmux-dependent tests now genuinely execute. Any tmux test added here is expected to **run, not skip** — a skip means the guard or the fixture is wrong, and must not be accepted as environmental.

- **W10 — There is no `tmux` pytest marker. Do not use one.** Iteration 1's ticket specified it (item M1); it was never implemented, and Revision 1 of *this* ticket propagated that stale claim without checking. The actual idiom is a module-level skipif:
  ```python
  HAS_TMUX = shutil.which("tmux") is not None
  needs_tmux = pytest.mark.skipif(not HAS_TMUX, reason="requires a local tmux binary")
  ```
  — `tests/test_backend.py:25-26`, `tests/test_send.py:20-21`. Use `@needs_tmux`.

  The trap: the tool directory has no pytest config, so `rootdir` resolves to the repo root `pyproject.toml`, which registers **only** `integration` (`:52-54`) and sets `addopts = "-ra -q -m 'not integration'"`. A bare `@pytest.mark.tmux` would raise `PytestUnknownMarkWarning` and **skip nothing** — the test runs unconditionally and fails on machines without tmux, the exact opposite of the intent.

- **W11 — Verify every claim this ticket makes against the code before acting on it.** W10 exists because Revision 1 trusted a prior ticket's specification instead of the source. Line numbers here were verified at commit `1bb37a7`; if one does not resolve to the quoted prose, treat the surrounding instruction as suspect rather than working around it.

---

### Ticket 1: Probe substrate — isolated SUT, ground-truth readers, nonces

#### Overview
Build the foundation every later ticket stands on: a way to create a throwaway system-under-test, read its true state without going through the tool being tested, and tag messages so a real model's compliance leaves a mechanical fingerprint.

#### Implementation Steps

1. **`probe/lib/sut.py` — SUT lifecycle.**
   Define `@dataclass(frozen=True) class Sut` with fields `runtime: Path`, `run: str`, `agentctl: Path`, `env: dict[str, str]`.
   - `create_sut(brief_id: str, *, spacey: bool = False) -> Sut` mints `runtime = Path(tempfile.mkdtemp(prefix=...))` and `run = f"sut-{brief_id}-{int(time.time())}"`. When `spacey=True`, the temp directory name must contain **both a space and an `@`** — this is the standing regression control for review finding B1 (unquoted hook commands under such paths, which failed *silently*).
   - `env` returns a dict suitable for `subprocess.run(env=...)`, setting `AGENT_TABS_RUNTIME`, `AGENT_TABS_RUN`, and `AGENT_TABS_VIEWER=none`. The viewer setting is mandatory: without it, ten trials open ten iTerm tabs.
   - **`create_sut` must pass an explicit `--permission-mode` and pre-seed workspace trust for the SUT's `cwd`.** Both were discovered empirically by the spike and neither is optional:
     - The default permission mode blocks a fresh worker on approval dialogs for reading its **own inbox** and for running **`agentctl reply`** — the protocol's own reporting channel. Under `tempfile.mkdtemp()` roots, every trial hangs on a dialog nobody is watching.
     - Claude Code now shows a **workspace-trust prompt** for any `cwd` the user has not trusted. It blocks *before* `SessionStart`, so `spawn` times out at 60s and the C002 except-arm kills the window. One spike window died exactly this way with `agent 's2' never reported SessionStart within 60s`.
   - `destroy_sut(sut: Sut, *, preserve: bool) -> Path | None` calls `agentctl close-run --force`, **then unconditionally runs `tmux kill-session -t <run>` ignoring its exit status**, then deletes the runtime tree unless `preserve` is set (failing trials preserve; passing trials do not).
     The belt-and-braces kill is deliberate: teardown currently runs through the subject under test, so a regression in `close-run` would leak one tmux session per trial, and the next trial's `ground.windows()` would read a polluted server. A bug in `close-run` must not destroy the harness's ability to detect that bug.

2. **`probe/lib/ground.py` — ground-truth readers.**
   Import only the five inert data carriers W3 permits — `EventType` (`:219`), `Event` (`:256`), `OutboxStatus` (`:378`), `OutboxMessage` (`:392`), `RunPaths` (`:168`) — using the `sys.path` insertion idiom already in `tests/conftest.py` (the directory name has a hyphen and is not importable as a package). `Event` and `OutboxMessage` are required by the signatures below and are frozen dataclasses, not parsers.
   Functions, all reading the filesystem or `tmux` directly:
   - `events(sut, agent=None, type=None) -> list[Event]` — parses **`<runtime>/<run>/bus.jsonl`** line by line. Note the run segment: `RunPaths.bus` is `self.root / "bus.jsonl"` where `root` is the *run* root, and `runtime_root` is `root.parent` (`agentctl.py:180-185`). Confirm with `agentctl paths --run <id>` rather than assuming; an earlier revision of this ticket had it wrong.
   - `inbox_files(sut, agent) -> list[Path]` — sorted; `agentctl` writes zero-padded names via `next_inbox_path` and never overwrites.
   - `outbox_messages(sut, agent) -> list[OutboxMessage]`.
   - `windows(sut) -> list[str]` — shells `tmux list-windows -t <run> -F '#{window_id}'`; returns `[]` when the session is gone.
   - `screen(sut, agent, lines) -> str` — `tmux capture-pane`. **Observation only**; no assertion helper may call it except `assert_screen_lacks`.

3. **`probe/lib/nonce.py` — fingerprinting.**
   - `ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"` — 32 characters, excluding `I`, `O`, `0` and `1`, which are ambiguous in a terminal font.
   - `mint() -> str` returns a **sentinel-prefixed** token: `f"TOK-{''.join(random.choices(ALPHABET, k=4))}"`, e.g. `TOK-K7QX`. **`mint` must dedupe against a module-level set of tokens already issued**, redrawing on a hit. `random.choices` guarantees nothing: the space is `32**4 = 1,048,576`, so the birthday probability of a collision across 100 draws is ≈ **0.47%** — one red build per ~210 runs, arriving months later as an unreproducible failure. Uniqueness is cheap to guarantee and expensive to debug.
   - `tokens_in(text: str) -> set[str]` extracts with `re.findall(r"\bTOK-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{4}\b", text)`.

   **The sentinel is not cosmetic.** An unprefixed `\b[A-Z2-9]{4}\b` matches ordinary words a worker writes in a reply — `TODO`, `JSON`, `HTTP`, `DONE`, `HEAD`, `FAIL`, `NOTE` — and under T4's set-equality grading a single stray uppercase word fails the trial. The severity is not the false negative: a `0.6` rate produced by regex noise is **indistinguishable from the ambiguous-prose signal this entire iteration exists to detect**, and T7's oracle would route it to `doc-rewrite`. The instrument would generate rewrites of `WORKER.md` for prose that is fine. The noise floor must not overlap the signal.

   This is the mechanism that makes a nondeterministic worker deterministically gradable: every message carries a token, the probe role requires echoing consumed tokens, and grading becomes a set comparison.

4. **`probe/lib/assertions.py`.**
   `assert_tokens` (see below), `assert_exit`, `assert_event_absent`, `assert_event_count`, `assert_inbox_contains`, `assert_screen_lacks`, `assert_no_windows`. Each raises `ProbeFailure(brief_id, expected, observed)` — a structured exception, because T7's oracle consumes its fields as JSON, not as prose.

   **`assert_screen_lacks` must carry a positive control and refuse to pass on an empty capture.** tmux panes in an *unattached* session repaint only on resize, so `capture-pane` returns blank or stale content — a real spawn failure produced a `Last screen:` of 40 blank lines. An absence assertion against a blank screen **passes vacuously**: a green result proving nothing, which is the precise failure class this iteration exists to eliminate. The helper must first assert the capture is non-empty and contains an expected landmark (the composer marker, say), and raise a **harness error** — not a probe failure — if it cannot. Note this is the same defect family as T0 (`agent-tabs-composer-readiness-regression.md`); if T0 fixes the capture path, simplify here rather than keeping two mitigations.

   `assert_tokens(echoed: set[str], expected: set[str], minted: set[str])` applies **two** conditions, never set equality:
   - `expected ⊆ echoed` — every token the brief sent was accounted for;
   - `(echoed ∩ minted) ⊆ expected` — no token minted for a *different* message leaked in.

   Set equality would fail a worker that correctly echoed all three tokens and also wrote the word `DONE`. Subset-plus-no-foreign-tokens is the assertion the claim actually needs.

5. **`probe/probe.py` — preserve only real commands.**
   T3 owns the working `coverage` command and T5a owns `checks`. T1 must not advertise `run` or `explore` before their real behavior exists: T4 introduces `run` together with briefs and ledger semantics; T6 introduces `explore` together with its journal semantics. Empty command handlers would make the probe claim a capability it does not have.

6. **`tests/test_probe_substrate.py`.**
   Assert: `create_sut(spacey=True)` produces a path containing both `" "` and `"@"`; `destroy_sut(preserve=False)` removes the tree and `preserve=True` retains it; **`tokens_in` recovers all 100 of 100 minted nonces from a body of surrounding prose** (assert the round-trip, not the uniqueness — uniqueness is `mint`'s job and asserting it here is what makes the test flaky) and ignores lowercase and unprefixed 4-character uppercase words; `ground.events()` parses a hand-written `bus.jsonl` fixture including a line with an unknown `type` (which must degrade to `EventType.UNKNOWN`, matching `EventType.parse`'s forward-compatibility contract); `ground.windows()` returns `[]` rather than raising when the tmux session does not exist. Use `@needs_tmux` (W10) for anything touching a real server.

#### Explicit Constraints & Warnings
- **Do not import `agentctl`'s `derive_state`, `read_events` or `read_outbox` into `ground.py`.** They are subjects under test. `ground.py` re-implements the reads deliberately — this is the one place duplication is correct, and a comment must say so or a future cleanup pass will "fix" it. The five data carriers W3 permits are fine to import; the parsers are not.
- **`create_sut` must not reuse the default runtime root.** `~/.local/state/agent-tabs/<repo>-<hash>/` is the human's real tree; a probe that writes there pollutes the log it is reading and a teardown bug destroys real work.
- **Guard tmux-dependent tests with `@needs_tmux`, not a marker.** See W10 — the `tmux` marker does not exist and a bare `@pytest.mark.tmux` skips nothing.

#### Acceptance Criteria
- [Automated] `tests/test_probe_substrate.py` asserts a `bus.jsonl` fixture containing `{"type":"future_event_from_a_newer_version"}` parses to `EventType.UNKNOWN` with the raw string preserved, rather than raising.
- [Automated] **`tokens_in("TODO: check the JSON payload over HTTP, then mark it DONE") == set()`.** This is the regression guard for the unprefixed-regex defect described in step 3; without it the whole instrument has a noise floor that overlaps its signal.
- [Automated] `assert_tokens` passes when `echoed` is a strict superset of `expected` containing no foreign minted tokens, and fails when a token minted for another message appears.
- [Automated] A test asserts `create_sut(spacey=True).runtime` matches `r"[ ].*@|@.*[ ]"` — both characters present.
- [Automated] A test asserts `ProbeFailure` serialises to a dict with exactly the keys `brief_id`, `expected`, `observed`.
- [Manual] `python3 probe/probe.py --help` lists the implemented `coverage` and `checks` subcommands, and runs on a machine with no virtualenv active and no `pip install` performed.
- [Manual] The T1 lifecycle API builds its spawn command with an isolated runtime, trusted `cwd`, `--viewer none`, and explicit `--permission-mode bypassPermissions`; real passing/failed worker trials are introduced with T4's brief runner.

#### Status

**DONE — HUMAN-SIGNED-OFF (2026-08-08).** Archived record: `history/tickets/agent-tabs-probe-substrate.md`. The user-approved scope correction keeps `run` and `explore` absent until T4 and T6 own their actual behavior; the T1 lifecycle, readers, nonces, and assertions remain the shared substrate.

---

### Ticket 2: `puppet.py` — deterministic fault states

#### Overview
A real model cannot be asked to be busy for exactly twenty seconds, or to leave a composer half-filled, or to die without firing its exit hook. Puppet holds those states on command so `send`'s three readiness gates can be tested against a known-bad counterparty at a known instant.

#### Implementation Steps

1. **Step 0 — spike, before writing anything else.** Revision 1 of this ticket asked only about argv and would have produced four states that `spawn` kills before any of them can hold anything. The spike must answer **three** questions, and record all three:

   **(a) Lifecycle.** Confirm against a live run what W6b states from the source: `spawn` blocks on `SPAWNED` (`:1477`), `_bootstrap` blocks on `TURN_START` twice (`:1528-1534`), and the `except` arm kills the window (`:1488-1493`). Trace what Revision 1 specified, and why each state died:

   | State (rev 1) | Emitted | Outcome |
   |---|---|---|
   | `busy` | `turn_start`, sleep, `turn_end` | no `spawned` → `SpawnError` at 60s, window killed |
   | `deaf` | `spawned`, block | no `turn_start` → `SpawnError` after 2×30s, window killed |
   | `dirty-composer` | `spawned`, partial write, block | same |
   | `hard-kill` | `spawned`, SIGKILL | same, plus a window race |

   Required corrections, to be confirmed empirically: **every state emits `spawned` first**, and `spawn_puppet` passes **`--no-doorbell`**.

   **(b) Argument delivery.** Confirm W6: `_worker_argv` (`:1315-1363`) admits no caller arguments and the window env is the three hardcoded keys at `:1440`. `puppet.py --state busy --for 20` is therefore **undeliverable** as specified in Revision 1.

   **(c) Argv shape.** Capture what the wrapper actually receives. Expect the Claude vector — `_known_provider` returns `None` for an unrecognised name, so the Claude default stands and `:1358` builds `[binary, "--settings", P, "--permission-mode", M]`, with an **optional tail**: `--setting-sources ""` when `--isolated-settings` (`:1359-1360`) and `--model X` when a model is given (`:1361-1362`). With probe's default `--model haiku` the real vector has six elements. Do not hard-code a count; the wrapper ignores argv entirely.

   **Write all three outcomes into `probe/lib/sut.py` as a module docstring.** The next person will otherwise repeat this spike.

2. **`probe/puppet.py` — states.** Exactly four, and **no others**. Every one emits `spawned` as its first action, by shelling `agentctl hook spawned`; puppet fires no Claude hooks, so nothing else will:
   - `busy` — `spawned`, then `turn_start`, sleeps, `turn_end`. Reads nothing.
   - `deaf` — `spawned`, then blocks forever without reading stdin. Simulates a lost or mangled doorbell keystroke.
   - `dirty-composer` — `spawned`, writes a partial line to the terminal **without a newline**, then blocks. Simulates half-typed human text in the composer.
   - `hard-kill` — `spawned`, **then sleeps `HARD_KILL_DELAY = 3.0` seconds**, then `os.kill(os.getpid(), signal.SIGKILL)`. Emits no `exit` event: this is what a window that vanished with no exit hook looks like.

     The delay is load-bearing, not politeness. `spawn` only returns after `wait_for_event` observes the `spawned` event (`:1477`), which polls the log; a kill issued immediately races that poll and the window can be gone before `spawn` returns, making the spawn itself fail intermittently. The delay must be long enough for `spawn` to return and short enough that no brief waits on it. It is **not** a fix for a state that cannot come up — see the timeout constraint below.

   State and duration arrive **from the wrapper's own argv**, not from `spawn` — see step 3.

3. **State delivery: one generated wrapper per state.** Since no argument or environment channel exists (W6), encode the state in the executable. `sut.py` writes thin wrappers into the SUT tempdir at setup:

   ```sh
   #!/bin/sh
   # <sut-tmp>/pupp-busy-20 — every field below is interpolated at generation time
   exec "/abs/path/to/python3" "/abs/path/to/puppet.py" --state busy --for 20
   ```

   Interpolate `sys.executable` and the resolved `puppet.py` path explicitly. There is no shell variable to expand here — the wrapper runs with the three-key environment from `:1440` and nothing else, so a `$PY` left in the template expands to empty and `exec ""` fails.

   `spawn_puppet(sut, name, state, duration=None)` generates the wrapper, `chmod 0o755`, and calls `agentctl spawn <name> --binary <abs-wrapper> --no-doorbell --viewer none`.

   Two hard constraints on the generated name, both from `agentctl.py`:
   - **Absolute path, executable bit set.** `_resolve_worker` (`:1285-1312`) resolves via `shutil.which(name)` or `Path(name).resolve()`; a bare relative name will not be found.
   - **The filename must contain none of `codex`, `agy`, `claude`.** `_known_provider` (`:1273-1282`) substring-matches those against the basename, and a match silently selects the wrong launch vector. Hence the `pupp-` prefix rather than anything descriptive that might collide.

4. **`tests/test_probe_puppet.py`** (`@needs_tmux`, per W10): each state produces the expected `bus.jsonl` events and nothing else; `hard-kill` leaves no `exit` event of its own; a wrapper whose name contains `claude` is rejected by a guard in `spawn_puppet` before it reaches `spawn`.

#### Explicit Constraints & Warnings
- **Puppet must contain no inbox reading, no `agentctl reply`, and no notion of what a message means.** See W1. If a reviewer can describe puppet as "a fake worker", it has been built wrong — it is a fault injector, the tmux equivalent of unplugging a cable. The only protocol surface it touches is `agentctl hook`, and only to make itself observable.
- **`--no-doorbell` is mandatory on every puppet spawn.** It is the only flag that skips `_bootstrap` (`:1480`). Without it, every state fails the `TURN_START` proof twice and its window is killed — and the failure surfaces as `never started a turn after two bootstrap attempts`, which reads like a puppet bug rather than a missing flag.
- **Do not raise `--spawn-timeout` or `--bootstrap-timeout` to work around a state that will not come up.** That converts a 60-second failure into a slower one. If a state cannot emit `spawned`, the state is wrong.
- **Do not add a fifth state speculatively.** Each state exists to test a specific documented gate; a state with no claim behind it is dead code that will be maintained forever.
- `puppet.py` is under the tool directory and therefore inside `mypy --strict` and `ruff` scope (W7). The generated wrappers live in the SUT tempdir, outside it, and are not scanned.

#### Acceptance Criteria
- [Automated] Every state reaches a live window: `ground.events()` contains a `spawned` event for it, and — **for `busy`, `deaf` and `dirty-composer`** — `ground.windows()` is non-empty immediately after `spawn_puppet` returns. This is the regression guard for the Revision 1 defect where all four states were killed during spawn.
- [Automated] `hard-kill` is **exempt from the window half** of the criterion above and asserts only that its `spawned` event landed and that `spawn_puppet` returned without raising. Its window is expected to vanish; asserting liveness on a state whose purpose is to die converts a latent race into a guaranteed intermittent failure.
- [Automated] With a puppet in `busy` for 20s, `agentctl send <name> "x" --queue` exits `3`, the message is present in `inbox_files()`, and `assert_screen_lacks` confirms the payload was never typed into the pane — proving the doorbell was withheld, not merely unnoticed. **The capture must be proven non-empty first**; on a blank screen this assertion passes vacuously and proves nothing.
- [Automated] With a puppet in `dirty-composer`, `send` without `--force` does not deliver; with `--force` it does. This is the documented human escape hatch at `SKILL.md:128`.

  > **BLOCKED ON T0.** This criterion asserts against `_input_row_looks_busy`, which is broken today: Claude Code 2.1.226 renders placeholders in the composer row, so the gate reports an **idle** agent as `human_typing` and every `send` exits 3. A `dirty-composer` test written now would pass for the wrong reason — the gate fires on everything. Land `agent-tabs-composer-readiness-regression.md` first.
- [Automated] After `hard-kill` and a subsequent reconciliation, `bus.jsonl` contains **exactly one** `EXIT` event carrying `{"reason": "window_vanished"}` (`agentctl.py:1734`), however many times `list` is called. Assert on that reason specifically — a union assertion over `exit`/`error` counts would pass while hiding an unexpected `ERROR`, which is a different bug.
- [Manual] All three Step 0 spike outcomes — lifecycle, argument delivery, argv shape — are recorded as a docstring in `probe/lib/sut.py`, including the observed argv verbatim.

#### Status

**DONE — HUMAN-SIGNED-OFF (2026-08-08).** Archived record: `history/tickets/agent-tabs-probe-puppet.md`. The shared `Sut` lifecycle and `puppet.py` fault injector are ready for T4’s real-worker briefs.

---

### Ticket 3: Claim registry — complete

Archived record: `history/tickets/agent-tabs-probe-claim-registry.md`.

### Ticket 4: Conformance briefs — real workers, nonce grading, rate ledger

#### Overview
Measure whether the documented worker behaviour actually occurs, using real models and mechanical grading, and record the result as a **rate** rather than a boolean.

#### Implementation Steps

1. **`probe/roles/probe-worker.md`.** Thin: point at `WORKER.md`, plus one addition — *"when you reply, list on their own line the `TOK-XXXX` token from every inbox file you consumed this turn."* Nothing else. The role must not restate `WORKER.md`'s rules, or the brief measures the role instead of the document under test.

2. **Brief format — `probe/briefs/B002.md`**, YAML front matter plus prose:
   ```yaml
   ---
   id: B002
   claim: C014
   cell: [C014, lost-doorbell, real-haiku, claude, 1]
   trials: 10
   expect_rate: 1.0
   control: B002-control
   wait_timeout: 10        # REQUIRED — see the timeout constraint below
   ---
   ```
   The body names the arrange/act steps; the grade is a named function in `probe/grades.py`, never prose.

3. **Seed three briefs plus their controls.** All three grade with `assert_tokens` (subset plus no-foreign-tokens), never set equality:
   - **B001 → C003/C014, inbox discipline.** Send three nonced messages normally. Grade: `{A,B,C} ⊆ echoed`.
   - **B002 → C014, lost doorbell.** Send A normally; write B **directly into the inbox** with no doorbell; send C normally. Grade: `{A,B,C} ⊆ echoed`. This is the claim that carries the whole doorbell design, and reaching past `agentctl` to create the fault is the only way to test it.

     **B's file must be byte-indistinguishable from what `send` writes, and its number must never be hard-coded.** Otherwise the brief measures whether a worker tolerates a malformed filename, not whether it re-reads its inbox — and a failure would route to `doc-rewrite`, rewriting `WORKER.md` over a harness defect.

     The rule: **compute `highest + 1` at write time by the same scan `next_inbox_path` performs** (`agentctl.py:459-469` — glob `*.md`, `max(int(stem))`, format with `INBOX_WIDTH = 4` at `:62`), then write with `open("x")` so a collision fails loudly instead of destroying a message.

     Do not reason about which number that will be. `spawn` writes the bootstrap into the inbox **unconditionally** at `:1416` — inside the `try:`, before the `if doorbell:` branch at `:1480` — so the bootstrap owns `0001.md` whether or not `--no-doorbell` was passed, and `send A` takes `0002.md`. A hard-coded `0002.md` for B therefore either raises `FileExistsError` (if written with `open("x")`) or **silently overwrites message A** (if written with `write_text`). The second is the dangerous one: the trial then measures a worker that received two messages while the grade expects three tokens, the rate drops, the control still passes, and T7 routes a harness bug to `doc-rewrite` — exactly the failure this constraint exists to prevent.

     Computing the number survives any future change to what `spawn` deposits. Hard-coding it does not.
   - **B003 → C005, watermark.** Capture `seq`, spawn, send, then `wait --from-seq $WM`. Grade: `wait` exits `0` with the event, and a second `wait` with a watermark taken *after* the reply exits `2` (timeout) rather than instantly matching history.

     **This brief requires an explicit `--timeout`.** `DEFAULT_WAIT_TIMEOUT = 900.0` (`agentctl.py:1556`), and B003's grade deliberately waits for a timeout: at the default that is 900s × 10 trials × 2 (with control) ≈ **five hours for one brief**. Set `wait_timeout: 10` — ample for a watermark claim, since the assertion is that nothing matches, not that something eventually does.

4. **Controls are mandatory.** Every brief declares a `control` — the same scenario with the fault removed, which must pass at `expect_rate`. `probe.py` runs the control first and **aborts with exit 2 (harness error) if the control fails**, because a failing control means the brief is broken, not that a finding was made. This single rule eliminates most false positives before a human sees them.

5. **`probe/ledger.jsonl`** — one line per brief run:
   ```json
   {"ts":"2026-08-07T02:14:00Z","brief":"B002","cell":["C014","lost-doorbell","real-haiku","claude",1],
    "commit":"1bb37a7","model":"haiku","trials":10,"passed":6,"rate":0.6,
    "control_rate":1.0,"outcome":"finding","artifacts":["<abs path>"],"entry":"E0412"}
   ```

6. **`tests/test_probe_briefs.py`**: every brief's front matter parses; every `claim` exists in the registry; every `control` names a brief that exists; every brief's grade function exists in `probe/grades.py`. These are cheap structural tests that run without tmux or a model.

#### Explicit Constraints & Warnings
- **Rate, not pass/fail, is the metric.** `0.6` is the interesting reading and it has no boolean equivalent: it means the document is ambiguous — followed sometimes. A brief at `0.0` is a mechanical bug in `agentctl`; a brief at `0.6` is a prose defect. Conflating them loses the finding this whole iteration exists to surface.
- **Always spawn with `--viewer none`.** Ten trials otherwise open ten iTerm tabs (`SKILL.md:74-76`).
- **Never poll `wait` in a loop** — `SKILL.md:140-141` forbids it, and a harness that violates the protocol it is measuring has no standing. Run it as a blocking subprocess with an explicit `--timeout`.
- **`wait_timeout` is required in every brief's front matter, and `probe.py` must reject a brief without it.** The 900s default is a five-hour trap for any brief whose grade expects a timeout (see B003). Never rely on the default.
- **Capture `seq` before every `send`** (`SKILL.md:189-193`), or a fast reply lands between spawn and wait and the trial records a spurious timeout.
- **Grade with `assert_tokens`, never set equality.** A worker that echoes all three tokens and also writes `DONE` is compliant. Equality would fail it and route a harness artefact to `doc-rewrite`.
- **Cost has two dimensions, and Revision 1 only counted one.** Tokens: 3 briefs × 10 trials × ~2 Haiku turns is cents. **Wall-clock: ~60 real spawns across the three briefs plus controls, each with a 60s spawn budget plus model latency.** State the measured wall-clock in the ledger run and in the journal entry. Trials run **sequentially** in this iteration — "separate tmux session per trial" makes parallelism look free, but concurrent SUTs on one tmux server share a namespace and have no isolation story yet. Parallel trials are a later ticket, not an implementation detail.

#### Acceptance Criteria
- [Automated] A structural test asserts every brief in `probe/briefs/` names an existing claim, an existing control, an existing grade function, **and a `wait_timeout`**.
- [Automated] A test using a stubbed outbox asserts the B002 grade fails when the echoed set omits one token, and passes when all three are present — grading logic proven without spending a model call.
- [Automated] A test asserts the B002 grade **passes** on a stubbed reply containing all three tokens plus the words `TODO`, `JSON` and `DONE`. This is the paired guard for the nonce defect: T1 proves the regex ignores them, this proves the grade does.
- [Automated] A test asserts B002's hand-written inbox file matches `next_inbox_path`'s naming exactly — generate the expected name via `agentctl`'s own `INBOX_WIDTH` formatting and compare, so a change to `INBOX_WIDTH` breaks the brief loudly rather than silently invalidating it.
- [Automated] A test asserts `probe.py` exits `2`, not `1`, when the control fails, and that no ledger line with `outcome: finding` is written in that case.
- [Manual] `python3 probe/probe.py run B002 --trials 10` completes, appends exactly one ledger line, and preserves artifact directories only for the failing trials.
- [Manual] The three seeded briefs have a real rate recorded against commit `1bb37a7`. A rate below `1.0` is a **successful** run of this ticket, not a failure of it.

#### Status

**DONE — HUMAN-SIGNED-OFF AT REDUCED SMOKE SCOPE (2026-08-08).** Archived record: `history/tickets/agent-tabs-probe-conformance-briefs.md`. The owner accepted one corrected control-plus-target live trial for B001, B002, and B003 instead of the prescribed ten-trial rate measurement.

---

### Ticket 5: Orchestrator conformance and fluency counters

#### Overview
`SKILL.md`'s rules for the orchestrator are entirely unmeasured. Five of them are mechanically detectable from a log of `agentctl` invocations, and the fluency counters come free from the same data. Highest yield in the iteration.

#### Implementation Steps

1. **Step 0 — spike: how to observe the orchestrator's `agentctl` calls at all.** Revision 1 specified a PATH shim. It observes nothing, and fails *silently* — the exact silent-success shape as review finding B1 in Iteration 1. Verified:
   - `which agentctl` → **not found**. There is no `agentctl` on `PATH` on this machine.
   - Hooks embed an absolute vector: `[sys.executable, str(Path(__file__).resolve()), "hook", ...]` (`:1141-1145`).
   - Workers are handed the absolute path in their bootstrap: `f"- Report with \`{Path(__file__).resolve()} reply ...\`"` (`:1221`), and `WORKER.md:24-25` says the same.

   A shim first on `PATH` is therefore bypassed by every hook and every worker, and intercepts an orchestrator only if it types a bare `agentctl`, which nothing instructs it to do. The result is an empty `commands.jsonl` and five checks reporting a clean sheet.

   Two routes, in order of preference:

   - **Route A — CONFIRMED WORKING. Build this; Route B is not needed.** `SKILL.md:232-238` states settings are additive and a worker also loads any `.claude/settings*.json` in its working directory. `spawn` takes `--cwd`. The harness points the orchestrator-under-test at a probe-owned directory containing a `.claude/settings.json` whose `PreToolUse` hook on `Bash` appends the command to **`<runtime>/<run>/commands.jsonl`** — the run root, beside `bus.jsonl`, not the runtime root.

     The spike captured this on the first attempt, under a `cwd` containing **both a space and an `@`**:
     ```json
     {"hook_event":"PreToolUse","tool":"Bash","command":"echo PROBE_MARKER_12345",
      "cwd":"/private/tmp/probe cwd@spike","agent_env":"s3","run_env":"probe-s3"}
     ```
     Hook fires: yes. Full command string: yes. Agent perturbed: no — its turn completed normally.

     **Bonus the ticket did not anticipate:** the hook inherits the three-key window environment from `:1440`, so `AGENT_TABS_AGENT` and `AGENT_TABS_RUN` arrive for free. Attribution needs no `session_id` correlation.

     **Hard prerequisite — workspace trust.** Claude Code shows a trust prompt for any `cwd` the user has not trusted, and it blocks *before* `SessionStart`, so `spawn` times out at 60s and C002 kills the window. The probe `cwd` must be pre-seeded as trusted or **every trial dies at spawn**. This cost the spike one window before it was diagnosed.
     Confirm in the spike: the hook fires; it captures the full command string; it does not perturb the orchestrator. Two constraints — **do not pass `--isolated-settings`** (it maps to `--setting-sources ""` at `:1359-1360` and would disable the whole mechanism), and **`shlex.quote` every element of the hook command**, since the cwd may contain spaces and an `@` (this is review finding B1 from Iteration 1, and it failed silently there too).

   - **Route B — NOT NEEDED. Do not build it.** Recorded only so nobody re-derives it. It would have read an `AGENT_TABS_CMDLOG` env var at `main()` entry and wrapped the `args.handler(...)` dispatch at `:2383-2385`. Route A makes it unnecessary, and Route B would have modified the subject under test and made the log self-reported — a partial W3 breach. **Route A is confirmed; there is no `agentctl.py` ticket to write.**

     Two consequences that must be stated rather than discovered: **(a)** this is a permanent change to the subject under test and belongs in its own human-authored ticket against `agentctl.py`, not smuggled in by a probe author under W2; **(b)** the log becomes self-reported by the subject, a partial W3 breach — mitigate by cross-checking every check that can be cross-checked against `bus.jsonl`.

   **Either way: an empty `commands.jsonl` is a harness error (exit 2), never a clean sheet.** That single rule is what stops the Revision 1 failure mode from recurring under any future observation mechanism.

2. **`probe/lib/orchestrator_checks.py` — five checks, split by data source.** Two need only `bus.jsonl` and can therefore run against historical logs **today**, before Step 0 resolves. Three are blocked on it:

   | Check | Source | Detection | Violates |
   |---|---|---|---|
   | `ignored_awaiting_human` | **bus only** | a `message_sent` to agent A after A's `question`/`blocked`, with **no intervening `turn_start` for A** — subject to the 250 ms rule below | Rule 1 — **the big one** |
   | `no_teardown` | **bus + tmux** | see the run-end definition below | Rule 5 |
   | `polling_wait` | cmdlog | two `wait` invocations with the same predicate < 5s apart | `SKILL.md:140-141` |
   | `screen_parsing` | cmdlog | a `read --screen` followed by a `send` whose body shares a distinctive substring with the captured screen | `SKILL.md:153-155`, Rule 3 |
   | `unwatermarked_send` | cmdlog | a `send` with no preceding `seq` in the same run | `SKILL.md:189-193` |

   **Two predicate definitions the checks cannot be built without.**

   > **EMPIRICALLY CONFIRMED.** The spike verified this on a live worker: `{"seq":9,"type":"question"} {"seq":10,"type":"turn_end"}`, then `tmux send-keys 'blue' Enter` → `{"seq":11,"type":"turn_start"}`. Also confirmed on an idle agent (+0.25 s). Mechanism: `HOOK_EVENTS` maps `UserPromptSubmit → TURN_START` (`agentctl.py:938-943`), so it is Claude Code's event, not an agent-tabs concept. **The check is not inverted and can be built.**

   **The 250 ms rule — mandatory, and this is the subtle part.** Because `turn_start` fires on *any* prompt submission, `agentctl send`'s own doorbell produces one too. So the check depends on `message_sent` being logged before the doorbell's `turn_start` — and `_deliver` (`:1232-1240`) types the keystroke **first** and appends `message_sent` **second**:

   ```python
   backend.send(handle, doorbell_text(inbox_path), enter)   # submits the prompt
   append_event(paths, agent, EventType.MESSAGE_SENT, ...)  # logged only after
   ```

   That ordering is a **race between two processes**, not a construction guarantee. The orchestrator wins only because the worker's hook must cold-start a Python interpreter first. Measured: n=7 pairs, **0 inversions**, gaps 81–94 ms (mean 88 ms).

   Therefore: **treat a `turn_start` landing within ~250 ms *after* a `message_sent` as caused by it, not as evidence a human answered.** Without this, an inverted pair renders a genuine barge-in as `question → turn_start → message_sent` — byte-identical to the near-miss fixture this ticket declares *correct* behaviour — a false **negative** that silently clears the violation the check exists to catch.

   Treat `_deliver`'s type-then-log ordering as a **load-bearing invariant** of this check. If it ever changes, `ignored_awaiting_human` breaks silently. (Calibration, from the spike: 0/7 inversions is a small sample and is equally consistent with the ordering being genuinely reliable. This is recorded as a fragility to defend against, **not** as a defect in `agentctl`.)

   *`ignored_awaiting_human` — why `turn_start`, and not "pane input".* A human typing into a tmux pane produces **no event whatsoever**; there is no pane-input record in `bus.jsonl` or anywhere else, so a predicate phrased that way cannot be evaluated. The observable proxy is a turn: after `question`, A's turn has ended, so if a human answered in the window, A starts a new turn and emits `turn_start`. An orchestrator that barged in instead produces `message_sent` with no `turn_start` between. That is the violation.

   **Scope this check to Claude-provider agents.** Codex workers emit no turn boundaries at all (`SKILL.md:100-102`; the synthetic `spawned` at `agentctl.py:1476` is the only lifecycle event they produce), so an unscoped check reports a violation for every Codex worker that was ever asked a follow-up question. Filter on `meta.provider` (`:1176`), and record skipped agents in the result rather than silently dropping them.

   *`no_teardown` — what "the run ended" means.* There is no run-ended event. Two definitions, and the check must state which it used:
   - **historical logs** (the T5a manual criterion): the run ended at the last event in `bus.jsonl`. Violation = that last event is not an `exit` for every agent, **and** `tmux list-sessions` shows the session still alive.
   - **live runs** (B010): the harness marks the boundary itself when the orchestrator process exits.

   Report `inconclusive`, never `violation`, when the session is gone but no `close-run` is evidenced — the human may have killed it by hand, which is not an orchestrator defect.

   Note W5: `ignored_awaiting_human` keys on `question` and `blocked`. There is no `awaiting_human` event.

3. **`probe/lib/fluency.py` — six counters, split by source exactly as the checks are:**

   **Bus-only (ship with T5a):** `turns_per_task` (`turn_end` count between successive `message_sent` events), `question_rate` (`question`+`blocked` per task), `time_to_first_action` (`spawned` → first `turn_start`), `dead_air` (max `turn_start`-to-`turn_end` gap).

   **Cmdlog-dependent (blocked on Step 0, ship with T5b):** `doorbell_efficiency` (delivered vs. queued vs. forced, read from `send` exit codes) and `orchestrator_overhead` (agentctl calls per worker turn). Neither is derivable from `bus.jsonl`: it records `message_sent`, but nothing counts `list`, `status`, `seq` or `read` invocations, and exit codes appear nowhere in it.

4. **`probe/briefs/B010.md` — the full-loop brief.** A real orchestrator agent, given `SKILL.md` and a task genuinely requiring three workers, driving real workers. The harness only observes. Grade: zero violations from the five checks; fluency counters recorded to the ledger as a `fluency` object rather than graded, since there is no baseline yet.

5. **`tests/test_probe_orchestrator_checks.py`.** Each of the five checks gets a hand-written `commands.jsonl` + `bus.jsonl` fixture pair that trips it, **and** a near-miss fixture that must not trip it (e.g. two `wait` calls 30s apart with the same predicate is legitimate sequencing, not polling; a `read --screen` followed by an unrelated `send` is not screen-parsing).

#### Explicit Constraints & Warnings
- **Build the two bus-only checks before the spike, and both before any full-loop brief.** They are deterministic, they run against *any* run's log — including your real day-to-day usage, which is free data already on disk — and they test the document nobody is testing. Expect at least one to fire on existing logs.
- **An empty `commands.jsonl` is exit 2, never a pass.** The Revision 1 shim would have produced exactly that and reported five clean checks.
- **`screen_parsing` is a heuristic and will produce false positives.** Report it as `suspected`, never `violation`, and require T7's oracle to confirm it against the transcript. The other four are exact.
- **Do not grade fluency counters in this ticket.** Record them. A threshold invented before there is a baseline is a threshold invented from nothing, and it will be tuned to whatever the first run happened to produce.
- **Two of the six fluency counters depend on the cmdlog** — `doorbell_efficiency` and `orchestrator_overhead` — and are blocked on Step 0 along with the three cmdlog checks. The other four are bus-only. Do not file a counter under the wrong heading: the split is what a T5a implementer acts on.
- **If Route B is chosen, stop and write the `agentctl.py` ticket.** Do not modify the subject under test from inside a probe ticket. W2's reasoning — a change to the substrate invalidates every later probe result without anyone knowing when it started — applies to instrumentation as much as to fixes.

#### Acceptance Criteria
**T5a — bus-only. Satisfiable today, with no `commands.jsonl` in existence.**
- [Automated] `ignored_awaiting_human` and `no_teardown` each have a `bus.jsonl` fixture that trips them **and** a near-miss fixture that must not. The near-miss fixtures are the point: a check that fires on everything is worse than no check. For `ignored_awaiting_human` the near-miss is a `question` followed by a `turn_start` and *then* a `message_sent` — the human answered, which is correct behaviour.
- [Automated] A fixture with a Codex-provider agent that emits `question` and later receives `message_sent` with no `turn_start` reports **skipped, not violated** — the provider-scoping guard.
- [Automated] `no_teardown` reports `inconclusive`, not `violation`, when the tmux session is absent and no `close-run` is evidenced.
- [Automated] A fluency test asserts `question_rate` counts `question` and `blocked` events and does **not** look for a `type: "awaiting_human"` event (regression guard for W5).
- [Manual] **The two bus-only checks are run against at least one existing real run's `bus.jsonl` from `~/.local/state/agent-tabs/`**, and the result — violations, clean sheet, or inconclusive — is recorded in the journal. This is the cheapest available test of whether the whole iteration is worth finishing, and it requires nothing from Step 0.

#### Status

**DONE — HUMAN-SIGNED-OFF (2026-08-08).** Archived record: `history/tickets/agent-tabs-probe-bus-only-checks.md`. The user-approved shared reader and append-only journal primitive remain in the probe harness for T1 and T6 to extend.

**T5b — DONE — HUMAN-SIGNED-OFF (2026-08-08).** Archived record: `history/tickets/agent-tabs-probe-cmdlog-checks.md`.

---

### Ticket 6: Journal and coverage digest — the memory that stops repetition

#### Overview
Without a durable record, a fresh author agent rediscovers the same dead ends every session and bills for each rediscovery. The expensive thing to preserve is not the findings — it is the **negative results**.

#### Implementation Steps

1. **Coordinate system.** Every journal entry stamps a `cell`:
   ```
   (claim, fault, counterparty, provider, concurrency)

   fault         none | lost-doorbell | copy-mode | busy | dirty-composer |
                 hard-kill | spacey-path | corrupt-settings | human-interrupt |
                 inbox-discipline | watermark
   counterparty  real-haiku | real-sonnet | puppet | orchestrator-loop
   provider      claude | codex
   concurrency   1 | n-workers | worktree
   ```
   This makes "have we tried this?" a lookup rather than a reading-comprehension exercise.

2. **`probe/journal.jsonl`** — append-only, four entry kinds:
   - `trial` — a brief run (mirrors the T4 ledger line, plus `entry` id).
   - `explore` — an authoring session, **including ones that found nothing**. Fields: `tried: list[str]`, `ruled_out: str`, `outcome: finding | no-finding | dead-end | inconclusive`, `fault_proof: str`.
   - `verdict` — an oracle routing decision (T7).
   - `invalidate` — a claim hash changed; carries `stale_briefs`.

3. **`probe/lib/journal.py`**: `append(entry)`, `cell_status(cell) -> fresh | stale | dead-end | unvisited`, `regenerate_coverage() -> str`.

4. **`probe/COVERAGE.md` — the derived digest**, regenerated and never hand-edited. Sections: claims covered/uncovered/stale; rate trends per brief with regression arrows; **dead ends, with the reason**; unvisited cells ranked. This is what an author agent reads at the start of a session — the raw journal grows unboundedly and will eventually exceed a context window, which is precisely why the digest exists.
   This mirrors the tool's own invariant (`SKILL.md:40-41`): the journal is the log, `COVERAGE.md` is the cache, and a digest that cannot be regenerated from the journal is a bug.

5. **The gate, in `probe.py`:**
   - An author declares its target cell **before** exploring.
   - `probe.py explore --cell <...>` **refuses** a cell that is `fresh` or `dead-end` unless `--new-information "<reason>"` is supplied, and that reason is recorded.
   - A session that ends without appending a journal entry is a **failed session**. Agents are structurally biased toward reporting wins; without this, unproductive lines are quietly abandoned and the journal records only successes — making it useless for the exact purpose it exists for.

6. **`tests/test_probe_journal.py`**: `regenerate_coverage()` is a pure function of the journal (two calls over the same input produce byte-identical output); `cell_status` returns `stale` when the claim hash has changed since the entry; the explore gate refuses a fresh cell and accepts it with `--new-information`.

#### Explicit Constraints & Warnings
- **A `dead-end` entry must carry `fault_proof`.** "Nothing broke" and "I failed to construct the fault" look identical from outside, and the second wrongly poisons a cell forever. Without evidence the fault actually fired — the corrupted file, the tmux state, the injected timing — the entry records as `inconclusive` and the cell **stays open**.
- **`COVERAGE.md` is a `.md` under the tool directory (W4).** It must reference artifacts by `entry` id only. Absolute paths from this machine contain the host repository name and will break `test_genericity.py`.
- **Never hand-edit `COVERAGE.md`.** Add a generated-file header saying so, or someone will.

#### Acceptance Criteria
- [Automated] A test asserts `regenerate_coverage()` produces byte-identical output across two runs on a fixed journal fixture.
- [Automated] A test asserts an `explore` entry with `outcome: dead-end` and no `fault_proof` is rejected at append time — the cell must not be poisoned by an unevidenced claim.
- [Automated] A test asserts `COVERAGE.md` output contains no absolute filesystem paths (regex for a leading `/Users` or `/tmp` segment).
- [Manual] After running T4's three briefs, `COVERAGE.md` lists the covered claims, the remaining uncovered ones from the T3 seed, and at least one ranked unvisited cell.

#### Status

**IMPLEMENTED — AWAITING HUMAN REVIEW (2026-08-08).**
- [Automated] `test_probe_journal.py` covers deterministic rendering, hash drift and legacy entries, unevidenced dead-end rejection, path redaction, explore-gate override recording, and derived T4 coverage.
- [Manual] Regenerated `probe/COVERAGE.md` shows the three covered T4 claims, twelve uncovered T3-seed claims, rate trends for B001–B003, and ranked unvisited cells.
- [Validation] Ruff and strict mypy pass. The full suite passes with the three expected opt-in E2E skips. `pre-commit run --all-files` passes after normalizing the journal cell and cmdlog phase types; all T6 files are formatted.

---

### Ticket 7: Oracle triage and spec emission

#### Overview
Route findings to the right kind of fix, and deduplicate them, before anything reaches a human's backlog. Without this, the loop produces forty tickets of noise and you stop reading them in week two.

#### Implementation Steps

1. **`probe/roles/oracle.md`.** Input is a fixed envelope, so the oracle is not parsing prose:
   ```json
   {"brief":"B002","rate":0.6,"claim":"C014","control_rate":1.0,
    "artifacts":["<abs path>"],"prior_rate":1.0,"prior_commit":"76f0155","entry":"E0412"}
   ```
   It reads the SUT's `bus.jsonl` and the worker transcript from the preserved artifact directory, then routes to exactly one verdict:

   | Verdict | Condition | Output |
   |---|---|---|
   | `code` | rate ~0.0; log contradicts the claim | spec against `agentctl.py` |
   | `doc-gap` | worker complied; no claim covers the behaviour | new claim + spec |
   | `doc-rewrite` | worker non-compliant; the claim is clear but ineffective | spec against `WORKER.md`/`SKILL.md` |
   | `harness` | the brief or control is at fault | brief fix, **no spec** |
   | `duplicate` | matches an open spec in `work_organisation/probe/` | journal entry only |

   The middle two rows are what a conventional test suite structurally cannot produce, and they will be most of the yield.

2. **The citation rule.** Every `code` and `doc-rewrite` verdict **must** cite a claim id. A finding that cannot cite one is `doc-gap` by definition — the spec is silent, which is a real defect and a cheap fix. This is the gate that stops the loop from generating opinion-tickets.

3. **Spec emission** via `.agent/skills/spec-writer/SKILL.md`, but written to **`work_organisation/probe/`**, not `work_organisation/spec/`. Each spec carries brief id, claim id, rate, commit, journal `entry` id, and the artifact path. Machine findings stay quarantined until a human promotes them.

4. **Wire into `probe.py`:** a `finding` outcome spawns the oracle via `agentctl` in the harness run — not the SUT run — and appends a `verdict` journal entry.

#### Explicit Constraints & Warnings
- **The oracle must not fix anything.** See W2. It routes and writes specs.
- **`work_organisation/probe/` must not be `work_organisation/tickets/`.** Machine findings silently joining the human backlog is how the backlog stops being read.
- **The oracle runs in the harness run, never the SUT run.** An oracle inside the system under test writes to the log it is judging.
- **Deduplication is by claim id first, prose similarity never.** Two findings against `C014` are the same finding until proven otherwise.

#### Acceptance Criteria
- [Automated] A test asserts a verdict of `code` or `doc-rewrite` carrying `claim: null` is rejected at append time.
- [Automated] A test asserts that when an open spec in `work_organisation/probe/` already cites claim `C014`, a second `C014` finding routes to `duplicate` and emits no new file.
- [Manual] One real finding from T4 or T5 produces a spec in `work_organisation/probe/` that names the reproducing brief, the rate, the commit, and a preserved artifact path a human can open.
- [Manual] The emitted spec follows the `spec-writer` template (Overview / Functional Requirements / Verification & Acceptance Criteria).

---

## Sequencing and the smallest useful slice

```
T1 ──┬── T2 ── T4 ──┬── T6 ── T7
     └── T3 ────────┘
     └── T5a  bus-only checks   (no dependencies; run first)
         T5b  cmdlog checks     (blocked on T5 Step 0)
```

**Revision 1 recommended "T3 + T5" as the cheap slice. That is no longer true**, and the correction matters: T5's three cmdlog checks now depend on either an unproven hook mechanism or a change to `agentctl.py` in a separate ticket. T5 is not uniformly cheap.

The revised smallest useful slice is **T3 + T5a**:
- **T3** — the claim registry, an hour of hand-work with no dependencies at all.
- **T5a** — `ignored_awaiting_human` and `no_teardown`, both derivable from `bus.jsonl` alone, runnable against the real run logs already sitting in `~/.local/state/agent-tabs/`.

Together those cost an afternoon, need no model calls, no tmux, and no change to the subject under test — and they answer the only question that matters before building the rest: *does an orchestrator reading `SKILL.md` actually obey it?*

**Order of work:** T3 and T5a first (independent, cheap). Then T5's Step 0 spike, since its outcome may spawn a prerequisite `agentctl.py` ticket that should be queued early. Then T1. T2 cannot be opened until its own three-part Step 0 spike is done — its Revision 1 form was unimplementable.

## Known weak points, stated up front

- **Claim extraction has poor signal-to-noise if automated.** T3 hand-seeds fifteen for exactly this reason.
- **`screen_parsing` is heuristic** and is reported as `suspected`, never as a violation.
- **`ruled_out` is where an author agent will be sloppiest.** The `fault_proof` requirement in T6 is the mitigation, and it should be spot-checked by a human for the first several sessions.
- **Full-loop briefs are noisy.** Variance across runs is large; a 5-run comparison will mislead. This is why doc A/B judging sits in Deferred until mechanical fluency deltas prove insufficient.
- **Observability of the orchestrator is not yet solved.** T5 Step 0 may conclude that Route A does not work, in which case three of five checks wait on a change to `agentctl.py`. Plan for that outcome rather than assuming it away.
- **Wall-clock, not tokens, is this iteration's real cost.** ~60 sequential real spawns at 60s of spawn budget each, plus model latency, before a single rate lands.

---

## Review dispositions

Revision 1 was reviewed against the codebase at `1bb37a7`. All findings are incorporated above except one.

| Finding | Disposition |
|---|---|
| T2: spawn kills all four puppet states | **Applied** — W6b, T2 Step 0(a), `--no-doorbell`, `spawned`-first |
| T2: no channel to deliver `--state` | **Applied** — W6, T2 step 3 wrapper scripts + naming constraint |
| T5: PATH shim observes nothing | **Applied**, with a different fix — see below |
| Nonce regex manufactures false findings | **Applied** — `TOK-` sentinel, subset grading, paired regression tests in T1 and T4 |
| `tmux` marker does not exist | **Applied** — W10, `needs_tmux` idiom throughout |
| W3 allowlist contradicts T1 signatures | **Applied** — five inert carriers named explicitly |
| `probe.py` CLI grammar collision | **Applied** — subcommands defined in T1 |
| B003 blocks 900s/trial | **Applied** — `wait_timeout` required in front matter, `probe.py` rejects briefs without it |
| `destroy_sut` uses the subject under test | **Applied** — unconditional `tmux kill-session` fallback |
| B002 inbox file must match byte-for-byte | **Applied, and promoted to HIGH** — same construct-validity class as the nonce defect |
| "exactly four Claude flags" | **Applied** — optional tail documented, count removed |
| `hard-kill` assertion too broad | **Applied** — asserts one `EXIT` with `reason: window_vanished` |
| **C003's line range is wrong** | **Rejected.** `SKILL.md:119` is blank; `:120` is "The payload is written to the agent's inbox **first**". The range `120-123` contains the complete claim including "the keystroke is a doorbell, never the message". Verified programmatically; `C003` stands unchanged. |

**Departure on the T5 fix.** The review's diagnosis is exact and its proposed fix — an `AGENT_TABS_CMDLOG` env var inside `main()` — is sound, but it modifies the subject under test and makes the log self-reported, both of which the review names and then accepts. T5 Step 0 therefore tries an external route first: a `PreToolUse` hook in a probe-controlled `--cwd`, exploiting the additive settings layering documented at `SKILL.md:232-238`. If that spike fails, the review's `CMDLOG` change is the documented fallback and becomes its own ticket against `agentctl.py`.

**Process note.** W10 exists because Revision 1 asserted a `tmux` pytest marker that Iteration 1's ticket specified but nobody implemented — a stale ticket claim propagated without checking the source. W11 generalises the lesson.

Revision 2 briefly suggested extending T3's claim-hashing to tickets. **That was wrong and is withdrawn.** Hashing detects *edits* to prose; every defect found in Revisions 1 and 2 was a claim that was specific enough to check and simply was not checked — none was an edit. A hash over Iteration 1's ticket would have caught none of them. W11 is the mechanism that does the work, and the disposition tables are what make it auditable, because each accepted finding is traceable to the source line that justified it.

---

## Review dispositions — round 2

Revision 2 was reviewed against the same commit. Its central observation: **all four newly-introduced defects were in text Revision 2 added.** Revision 1 said "write B directly into the inbox" (unfalsifiable); Revision 2 said "write `0002.md`" (falsifiable, and false). Precision manufactures surface area for being wrong — which is the point of it, and the reason a revision that fixes findings needs the same scrutiny as the one that prompted it. **Do not assume Revision 3 has converged.**

| Finding | Disposition |
|---|---|
| B002's inbox filename off by one; silent overwrite of message A | **Applied** — number is computed, never written down; bootstrap's unconditional `:1416` write documented; control asserts `0001.md` is the bootstrap |
| `hard-kill` cannot satisfy the new live-window criterion | **Applied** — `HARD_KILL_DELAY` added with its rationale, and the state exempted from the window half of the criterion |
| 100-nonce uniqueness assertion is ~0.47% flaky | **Applied** — `mint` dedupes; the criterion now asserts round-trip recovery, not uniqueness |
| `$PY` unexpanded in the generated wrapper | **Applied** — fully interpolated, with a note on why no shell variable survives |
| T1 step 2 still listed three imports against W3's five | **Applied** — the original finding was fixed in the warning and not in the body |
| `doorbell_efficiency` / `orchestrator_overhead` misfiled as bus-only | **Applied** — counters split by source, matching the check table |
| T4 manual criterion used pre-subcommand grammar | **Applied** |
| T5 acceptance list not split along T5a/T5b | **Applied** — T5a is now satisfiable with no `commands.jsonl` in existence |
| `ignored_awaiting_human` predicate referenced pane input, which is in no log | **Applied** — intervening `turn_start` is the discriminator; check scoped to Claude-provider agents, Codex reported as skipped |
| `no_teardown` had no run-ended signal | **Applied** — separate definitions for historical and live runs; `inconclusive` verdict added |
| Extending claim-hashing to tickets | **Withdrawn** — see the process note above |

---

## Spike dispositions — round 3 (execution, not review)

The `probe-spike` run executed T2 Step 0 and T5 Step 0 against live workers. Unlike rounds 1 and 2, these findings came from **running the system**, not reading it.

| Finding | Disposition |
|---|---|
| Spike 1: `turn_start` fires on human pane input, both idle and post-`question` | **Confirmed.** T5a's premise holds; the check is not inverted |
| Spike 2: Route A works first try under a space-and-`@` path | **Applied** — Route A marked confirmed, Route B struck, no `agentctl.py` ticket needed |
| Workspace-trust prompt blocks `SessionStart` for any untrusted `cwd` | **Applied** — hard prerequisite in T5 Step 0 and `create_sut`. Absent from every prior revision |
| `_deliver` orders keystroke-then-log; ordering is a 88 ms race, 0/7 inversions | **Applied** — 250 ms tolerance rule, ordering stated as a load-bearing invariant. Recorded as a **fragility, not a defect** |
| D1: composer gate misreads placeholders; every `send` exits 3 | **Split out as T0.** Blocks T2's `dirty-composer` criteria |
| D2: captures blank on unattached panes; absence assertions pass vacuously | **Applied** to `assert_screen_lacks` and T2's criteria; root cause in T0 |
| D3: default permission mode dialog-blocks inbox reads and `agentctl reply` | **Applied** to `create_sut` |
| D4: `<runtime>/bus.jsonl` → `<runtime>/<run>/bus.jsonl` | **Applied** in Revision 3 |
| `importlib.util.spec_from_file_location` crashes on `agentctl` | **No change needed** — T1's `sys.path` conftest idiom was already correct, now empirically confirmed |

**What this round proves about the method.** Rounds 1 and 2 found defects by reading source; this round found a **live production bug** by running the tool, in about an hour, before the harness it was scoping even existed. Execution is now the cheaper reviewer. Ship T0 and T3 + T5a rather than commissioning a fourth review.
