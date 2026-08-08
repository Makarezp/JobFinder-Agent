# Agent-Tabs — Claim Registry (T3)

**Sprint:** `sprint_v3_agent_tabs_hardening.md`
**Status:** **DONE — HUMAN-SIGNED-OFF (2026-08-08)**

## Overview

`SKILL.md` and `WORKER.md` contain normative propositions. This ticket turned fifteen hand-verified propositions into a finite, mechanically auditable coverage surface. It deliberately did not auto-extract claims: candidate prose has poor signal-to-noise, and downstream probes must begin with a trustworthy registry.

## Delivered

- `.agent/skills/agent-tabs/probe/claims.jsonl` holds one JSON object per claim, with `id`, exact `src` range, nearest `section`, claim text, kind, assigned briefs, and SHA-256 source hash.
- The hand-seeded claims are C001–C010 and C014–C018. They cover event-log state, spawn cleanup, inbox-first delivery, readiness gates, watermarks, the outbox, reconciliation, teardown, human handoff, worker identity, inbox rereads, reply identity, bootstrap assignment, screen visibility, and worker-management boundaries.
- `.agent/skills/agent-tabs/probe/lib/claims.py` validates the registry; hashes exact inclusive source ranges; reports stale, missing, and moved source; and identifies claims without briefs.
- `python3 probe/probe.py coverage` reports covered, uncovered, and stale counts without requiring a virtual environment or installed packages.
- `tests/test_probe_claims.py` proves every seeded source resolves, verifies the hash changes only when its cited lines change, checks uncovered classification, and exercises the coverage command.

## Constraints preserved

- Claims were seeded by hand; no LLM-driven extraction was added.
- `section` anchors preserve human context when line ranges eventually drift.
- No repository-specific paths were added to files scanned by the genericity contract.
- T3 introduced only the working `coverage` command. T1 retains ownership of the runner grammar when `run` has real behavior, so no placeholder subcommands exist.

## Acceptance evidence

- `AGENTCTL_PYTHON="$PWD/.venv/bin/python" .agent/skills/agent-tabs/test.sh` passed ruff, formatting, mypy strict, and pytest: **200 passed, 3 opt-in E2E checks skipped**.
- LSP diagnostics for the new command, library, and tests were clean.
- Manual command output:
  ```text
  covered: 0
  uncovered: 15
  stale: 0
  ```
  Zero covered and fifteen uncovered are the expected pre-brief state; zero stale confirms the registry matches the current protocol documents.
