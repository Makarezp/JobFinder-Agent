# Agent-Tabs — Bus-Only Orchestrator Checks (T5a)

**Sprint:** `sprint_v3_agent_tabs_hardening.md`
**Status:** **DONE — HUMAN-SIGNED-OFF (2026-08-08)**

## Delivered

- A ground-truth reader for `bus.jsonl`, agent provider metadata, and tmux-session presence. It parses persisted evidence directly and does not call `agentctl.read_events` or `derive_state`.
- `ignored_awaiting_human`, scoped to Claude workers. It reports Codex as `skipped`, and handles the 250 ms `message_sent`/`turn_start` logging race without clearing a genuine barge-in.
- Historical `no_teardown`, with explicit `clean`, `violation`, and `inconclusive` results.
- Ungraded bus-only fluency counters: turns per task, question rate, time to first action, and dead air.
- A working `probe.py checks --runtime <root> --run <id>` command that records a T6-compatible append-only `explore` journal entry.

## Shared-scope correction

T5a originally depended implicitly on the T1-only ground reader and T6-only journal, despite declaring itself independent and requiring a real-log journal record. The human-approved correction added only the shared reader and append primitive required for T5a. T1 still owns the SUT lifecycle and remaining readers; T6 still owns journal indexing and coverage-digest generation. No production `agentctl.py` behavior changed.

## Acceptance evidence

- Fixture tests cover tripping and near-miss human-handoff cases, Codex provider skipping, session-absent inconclusive teardown, and question/blocked fluency counting.
- Required quality gate passed: ruff, formatting, mypy strict, and **207 passed, 3 opt-in E2E checks skipped**.
- The command ran successfully against the existing `probe-spike` log. It reported `ignored_awaiting_human: clean` and `no_teardown: violation`; the latter is the correctly reported historical finding of a live session without final exits. Each manual execution appended an `explore` record to `.agent/skills/agent-tabs/probe/journal.jsonl`.
