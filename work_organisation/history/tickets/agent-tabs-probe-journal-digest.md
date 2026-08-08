# Agent-Tabs — Journal and Coverage Digest (T6)

**Sprint:** `sprint_v3_agent_tabs_hardening.md`
**Status:** **DONE — HUMAN-SIGNED-OFF (2026-08-08)**

## Delivered

- A validated append-only journal supporting `trial`, `explore`, `verdict`, and `invalidate` entries.
- A five-axis cell coordinate system with compatibility for historical integer/string single-worker concurrency. The existing T4 evidence required `inbox-discipline` and `watermark` fault values; the vocabulary now documents both.
- Source-range hashes stamped at append time. Hashless legacy entries and entries whose source has changed classify as stale without rewriting historical JSONL.
- An exploration gate that rejects fresh or verified dead-end cells unless `--new-information` states why the cell is being revisited; the override reason is persisted.
- Deterministic `COVERAGE.md` generation from journal, claim registry, and rate ledger. It reports claim coverage/drift, B001–B003 rate trends, proven dead ends, and ranked baseline cells. It has a generated-file header and redacts absolute artifact paths.
- T4 runner results now produce a `trial` journal entry alongside their rate-ledger entry.
- Cmdlog phase parsing was narrowed explicitly to `pre` or `post`, repairing the pre-commit type gate.

## Verification

```text
pre-commit run --all-files                         passed
ruff check .agent/skills/agent-tabs                passed
mypy --strict .agent/skills/agent-tabs             passed
pytest .agent/skills/agent-tabs/tests -ra -q       passed; 3 opt-in E2E skips
```

## Manual Evidence

The signed-off digest showed three covered claims (`C003`, `C005`, `C014`), twelve uncovered claims, B001–B003 rate trends, and ranked unvisited cells. The disposable exploration-gate scenario accepted its initial complete entry, rejected a repeat without new information, and accepted an override while retaining its stated reason.
