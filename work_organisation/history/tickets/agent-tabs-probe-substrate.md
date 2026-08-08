# Agent-Tabs — Probe Substrate (T1)

**Sprint:** `sprint_v3_agent_tabs_hardening.md`
**Status:** **DONE — HUMAN-SIGNED-OFF (2026-08-08)**

## Delivered

- An isolated `Sut` lifecycle with a per-run runtime root, controlled viewer environment, and space-and-`@` path regression control.
- Claude workspace-trust pre-seeding for each SUT workspace, plus a canonical spawn-command builder enforcing that workspace, `--viewer none`, and explicit `--permission-mode bypassPermissions`.
- Belt-and-braces teardown: `close-run --force`, direct tmux session kill, and selective runtime preservation.
- Ground-truth readers for bus events, mailboxes, provider metadata, tmux windows, and captures. They parse files and tmux directly and do not call the `agentctl` parsers or state derivation they measure.
- Unique sentinel nonces, structured probe/harness errors, and assertions for token accounting, lifecycle events, inbox content, screen absence with positive controls, and residual windows.

## Scope correction

T1's original command-grammar requirement conflicted with the later tickets that own executable `run` and `explore` behavior. The approved correction leaves only real commands visible: T3's `coverage` and T5a's `checks`. T4 introduces `run` with its real brief/ledger semantics; T6 introduces `explore` with real journal semantics. No empty command handlers were added.

## Acceptance evidence

- `tests/test_probe_substrate.py` covers unknown-event preservation, nonce false positives and round-trips, foreign-token rejection, structured failure serialization, spacey trusted roots, teardown behavior, direct mailbox parsing, absent tmux sessions, and screen positive controls.
- Full required quality gate passed: ruff, formatting, mypy strict, and **218 passed, 3 opt-in E2E checks skipped**.
- No-virtualenv smoke command passed: `python3 .agent/skills/agent-tabs/probe/probe.py --help`; it lists exactly `coverage` and `checks`.
- Lifecycle smoke test created a trusted spacey runtime, force-tore it down, and verified its removal.
