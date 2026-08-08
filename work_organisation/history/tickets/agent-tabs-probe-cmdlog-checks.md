# Agent-Tabs — Cmdlog Checks (T5b)

**Sprint:** `sprint_v3_agent_tabs_hardening.md`
**Status:** **DONE — HUMAN-SIGNED-OFF (2026-08-08)**

## Delivered

- Route A instrumentation in a probe-owned, workspace-trusted `.claude/settings.json`; it records Bash tool calls at `<runtime>/<run>/commands.jsonl` without modifying `agentctl.py`.
- Durable PreToolUse and PostToolUse command records containing full command, cwd, session id, and inherited agent/run attribution.
- Pre-read screen snapshots only for `agentctl read --screen`, so the screen-parsing heuristic compares a later send body against retained evidence rather than a current or blank pane.
- Strict command-log loader: absent, empty, or malformed logs are harness errors and cause `probe.py checks` to exit `2`.
- Cmdlog checks for polling waits, screen parsing, and unwatermarked sends. The screen check reports `suspected`, never `violation`.
- Cmdlog fluency: command calls per observed worker turn and delivered/queued/forced doorbell outcomes. The live PostToolUse payload lacks Bash exit status, so delivery is derived from agentctl's mutually exclusive `sent`/`queued` stdout contract.

## Evidence

- Live Route A smoke ran in a trusted workspace containing both a space and `@`; the hook captured `echo T5B_ROUTE_A_MARKER` with its complete command text and inherited run/agent environment. The worker completed and replied `HOOK_READY`.
- A direct run-local bus/cmdlog smoke returned five clean checks and recorded `delivered: 1`, `queued: 0`, `forced: 0`.
- `probe/journal.jsonl` contains the Route A and combined-checks `t5b-*` entries.

## Verification

```text
ruff check .agent/skills/agent-tabs                 passed
ruff format --check [all T5b files]                 passed
mypy --strict .agent/skills/agent-tabs              passed
pytest .agent/skills/agent-tabs/tests -ra -q        passed
```

Three opt-in live E2E tests remained skipped. The whole-tree formatter has a pre-existing unrelated difference in `tests/test_send.py:418`; no T5b file is unformatted.
