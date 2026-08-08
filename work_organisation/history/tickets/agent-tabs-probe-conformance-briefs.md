# Agent-Tabs — Conformance Briefs (T4)

**Sprint:** `sprint_v3_agent_tabs_hardening.md`
**Status:** **DONE — HUMAN-SIGNED-OFF AT REDUCED SMOKE SCOPE (2026-08-08)**

## Delivered

- Thin real-worker role pointing at `WORKER.md`, with only the required nonce-reporting addition.
- Typed YAML-front-matter briefs for B001 inbox discipline, B002 lost doorbell, B003 watermark semantics, and their controls.
- Structural brief validation for claims, controls, grades, and mandatory bounded wait timeouts.
- Sequential Haiku runner: control first, rate-based results, failure-only retained artifacts, durable `ledger.jsonl` and journal records, and no auto-fix path.
- B002 direct-inbox injection delegates filename selection to `agentctl.next_inbox_path` and writes exclusively with flush plus fsync.
- B003 records its watermark only after the durable bootstrap reply, preventing historical bootstrap replies from satisfying the token-reply wait. Its controlled doorbell uses `--force` only if Claude has replied but remains without `turn_end`; the actual watermark assertion remains bounded and normal.

## Automated evidence

- `ruff check .agent/skills/agent-tabs` passed.
- `mypy --strict .agent/skills/agent-tabs` passed.
- `pytest .agent/skills/agent-tabs/tests -ra -q` passed, with three opt-in live E2E tests skipped.
- Brief structural/grade suite: 6 passed.

## Live smoke evidence

The owner explicitly reduced the prescribed ten trials per brief to one control-plus-target trial per brief. Corrected B001, B002, and B003 each recorded target and control rate `1.0`; no corrected run retained an artifact directory. B003’s corrected smoke run took 82.13 seconds.

This is runner smoke evidence, not the originally specified ten-trial rate measurement. The owner accepted that reduced criterion.
