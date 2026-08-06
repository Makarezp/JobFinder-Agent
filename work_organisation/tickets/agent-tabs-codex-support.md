# Agent-Tabs — Codex Worker Support

**Track:** Tooling / meta
**Status:** Proposed
**Discovery baseline:** `codex-cli 0.146.1`, inspected locally on 2026-08-06. Its interactive invocation is `codex [OPTIONS] [PROMPT]`; it exposes `--model`, `--sandbox {read-only,workspace-write,danger-full-access}`, `--ask-for-approval {untrusted,on-request,never}`, and `--cd`. It does **not** expose the Claude `--settings` hook mechanism used by the existing spawn handshake.

### Ticket 10: Add Codex as an Explicit Agent-Tabs Worker Provider

#### Overview

Allow `agentctl spawn` to run an interactive Codex worker in a tmux window while preserving the inbox/outbox protocol and the safety properties of existing Claude workers. Codex must be modeled as a provider with its own command construction and lifecycle semantics; simply resolving a binary named `codex` would currently generate unsupported Claude flags and wait forever for Claude-only hooks.

#### Implementation Steps

1. **Provider model and persisted schema — `.agent/skills/agent-tabs/agentctl.py`.** Add a closed `WorkerProvider` `StrEnum` with exactly `claude`, `agy`, and `codex`. Add `provider: str` to `AgentMeta`, serialize it in `meta.json`, and make `AgentMeta.load()` backward-compatible: a metadata file without this field is interpreted as `claude` so existing runtime directories remain readable. Add an optional `--provider {claude,agy,codex}` option to the `spawn` parser. With no `--provider`, retain today's binary resolution (`claude`, then `agy`) and infer the matching provider from the resolved executable; with `--provider codex`, resolve only `codex` unless `--binary` is supplied. `--binary` remains authoritative for the executable path but must not silently change an explicit provider: reject a basename conflict, and require `--provider codex` when launching a nonstandard Codex executable name.

2. **Provider-owned launch argv — `.agent/skills/agent-tabs/agentctl.py`.** Extract the current Claude/AGY branches from `spawn_agent()` into one provider-to-argv function receiving the resolved binary, working directory, model, and provider-specific options. For `codex`, construct a true argv vector in this order: `[binary, "--cd", str(working_dir), "--sandbox", sandbox, "--ask-for-approval", approval]`, followed by `--model <model>` only when `model` is provided. Do not pass Claude-only `--settings`, `--setting-sources`, or `--permission-mode` flags to Codex. Add `--sandbox` and `--ask-for-approval` to `spawn`; for Codex default them to `workspace-write` and `never`, respectively. Keep the existing `--permission-mode` argument available only for `claude` and `agy`; reject it for Codex when the caller supplies a non-default value instead of guessing an equivalence. Never use `--dangerously-bypass-approvals-and-sandbox` as an implementation shortcut.

3. **Codex lifecycle — `.agent/skills/agent-tabs/agentctl.py`.** Keep Claude's generated `settings.json`, `SPAWNED` hook wait, and `TURN_START` bootstrap acknowledgement unchanged. Codex does not get `write_settings()` and must not wait for `SPAWNED` or `TURN_START`, because no supported Codex hook currently writes those events. After `backend.open()` succeeds and remains alive, append one synthetic `EventType.SPAWNED` event with `data={"provider": "codex", "source": "agentctl"}`; then write the standard bootstrap inbox file and ring its one-line doorbell exactly once. Return successful `AgentMeta` only after the inbox write and the doorbell send succeed. If the window dies before either operation, raise `SpawnError` containing `codex` and the last 40 screen lines, perform the existing cleanup, and append the existing `ERROR` event. Do not reuse `_bootstrap()` for Codex and do not add a fixed sleep: a process liveness check is the only launch proof available without a provider hook.

4. **Message delivery and state constraints — `.agent/skills/agent-tabs/agentctl.py`.** Keep inbox-first delivery and copy-mode checks provider-independent. Refactor `_input_row_looks_busy()` behind a provider-specific renderer lookup: retain the current Claude `❯` parser for `claude`/`agy`, and make the Codex renderer return `False` until a literal Codex tmux screen capture has been recorded and tested. This deliberate fail-open fallback preserves delivery (the inbox makes a lost doorbell recoverable) and must log a debug message naming the unavailable Codex composer detector. Do not fabricate `TURN_START` or `TURN_END` events from terminal output. For Codex, `reply`, `question`, and `blocked` remain the authoritative observable outcomes; `question`/`blocked` continue to move the worker into `awaiting_human` through the existing outbox/event path.

5. **Worker instructions and user-facing docs — `.agent/skills/agent-tabs/WORKER.md` and `.agent/skills/agent-tabs/SKILL.md`.** Change provider-neutral wording such as “hooks” only where it currently implies every worker has lifecycle hooks. Document that a Codex worker must read the bootstrap/inbox, send its final or blocking result through `agentctl reply`, and that `agentctl status` cannot infer Codex turn boundaries. Add a Codex spawn example:
   ```sh
   agentctl spawn reviewer --provider codex --role path/to/ROLE.md --run demo \
     --sandbox workspace-write --ask-for-approval never
   ```
   State that this starts the interactive TUI, not `codex exec`; `exec` is non-interactive and would defeat the human-visible, conversational window requirement. Document that the default stays Claude, and that users must choose `--provider codex` explicitly.

6. **Tests — `.agent/skills/agent-tabs/tests/test_spawn.py`, `.agent/skills/agent-tabs/tests/test_send.py`, and new `.agent/skills/agent-tabs/tests/test_codex_provider.py`.** Extend the existing fake-backend tests to assert: (a) Codex argv contains `--cd`, `--sandbox workspace-write`, and `--ask-for-approval never`; (b) a model is forwarded exactly once; (c) Claude-only flags are absent; (d) Codex metadata contains `provider: "codex"`; (e) legacy metadata without `provider` loads as Claude; (f) an explicit provider/binary mismatch raises before `backend.open`; and (g) Codex spawn emits the synthetic `SPAWNED` event, sends one bootstrap pointer, and does not call `wait_for_event` for `SPAWNED` or `TURN_START`. Add tests that a dead Codex window raises a diagnosable `SpawnError` and leaves no live fake window. In `test_send.py`, assert the Codex renderer fallback is fail-open and still preserves the copy-mode refusal. Add an opt-in tmux integration test, guarded by `AGENT_TABS_E2E=1`, `tmux`, and `codex`, that starts a Codex worker with a harmless role, verifies its tmux window stays alive through bootstrap, then closes the run in `finally`. Do not make the default suite spend an authenticated Codex request.

#### Explicit Constraints & Warnings

- **Provider boundary:** `claude`, `agy`, and `codex` are worker providers, not terminal backends. Do not add Codex behavior to `Backend`, `TmuxBackend`, or `Viewer`.
- **No invented Codex hooks:** Do not create or pass `settings.json` to Codex, claim that Codex emits Claude event names, or block a Codex spawn waiting for `SessionStart`/`UserPromptSubmit`/`Stop`/`SessionEnd`.
- **No unsafe policy escalation:** `workspace-write` plus `never` is the Codex default for this visible worker integration. Do not pass `--dangerously-bypass-approvals-and-sandbox`; a caller who needs a wider sandbox must explicitly select `--sandbox danger-full-access`.
- **Preserve existing workers:** Calls without `--provider` retain today's Claude-then-AGY resolution and the matching provider behavior. Claude retains its hook-generated event handshake; AGY remains supported as its existing explicit/fallback provider and is not refactored beyond the shared argv extraction.
- **Interaction remains visible:** Do not replace the interactive `codex` invocation with `codex exec`, JSONL output parsing, a cloud task, or an opaque background process.
- **State honesty:** Codex's lifecycle has no observed turn-start/turn-end signal. Status must report only real synthetic spawn, outbox, reply, question, blocked, error, and terminal-liveness evidence.
- **Test typing:** Fully annotate every new test function; `test.sh` runs `mypy --strict` when it is installed.

#### Acceptance Criteria

- [Automated] A fake Codex spawn records `provider: "codex"` in `meta.json`, opens the exact Codex argv, and includes no Claude-only settings or permission flags.
- [Automated] The Codex path appends exactly one synthetic `spawned` event, sends exactly one bootstrap doorbell, and never waits for Claude hook events.
- [Automated] A dead Codex window fails with a `SpawnError` mentioning `codex`, appends an `error` event, and does not leave a live window or worktree.
- [Automated] Metadata created before this ticket, without a `provider` key, still loads and behaves as provider `claude`.
- [Automated] The Codex composer fallback does not block delivery merely because no Codex-specific input-row capture is recognized, while copy-mode still blocks delivery.
- [Manual] With tmux and a logged-in Codex CLI, `agentctl spawn reviewer --provider codex --role <path> --run codex-demo` opens a visible interactive Codex window, writes `agents/reviewer/meta.json` with `provider: "codex"`, and places bootstrap message `0001.md` in its inbox.
- [Manual] The Codex worker can read the bootstrap file and run `agentctl reply --status reply` with a short body; `agentctl read reviewer --outbox --run codex-demo` displays that body and `agentctl status reviewer --run codex-demo` does not claim a fabricated turn boundary.
