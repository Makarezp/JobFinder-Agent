# Agent-Tabs Probe Loop Operator

This is the operating contract for an agent that measures Agent-Tabs protocol behavior. It is not permission to change the system under test.

## Mission

Measure one unverified protocol claim at a time with durable, inspectable evidence. Preserve both findings and non-findings. Route a genuine finding into a quarantined specification, then stop for human review.

## Boundaries

- **Workspace root:** repository root.
- **Python:** `.venv/bin/python`.
- **CLI:** `.agent/skills/agent-tabs/probe/probe.py`.
- **Protocol documents under test:** `.agent/skills/agent-tabs/SKILL.md` and `.agent/skills/agent-tabs/WORKER.md`.
- **Evidence:** `.agent/skills/agent-tabs/probe/ledger.jsonl`, `journal.jsonl`, and generated `COVERAGE.md`.
- **Machine-authored findings:** `work_organisation/probe/` only. They are not tickets.

## Non-negotiable rules

1. Never modify `agentctl.py`, `SKILL.md`, `WORKER.md`, `claims.jsonl`, briefs, tests, or an existing specification.
2. Never manufacture a failing trial merely to produce a spec.
3. Never promote a machine-authored spec into `work_organisation/tickets/`. A human must promote, reject, or request more evidence.
4. Never run conformance briefs or trials concurrently. The harness deliberately has no concurrent-SUT isolation story.
5. Never classify a control failure as a protocol finding. `probe.py run` exit code `2` is a harness failure.
6. Never rely on screen text as the protocol channel. Read `bus.jsonl`, inboxes, outboxes, and tmux only as the relevant ground-truth reader permits.
7. Never hand-edit `COVERAGE.md`; regenerate it.
8. End every manual exploration with a journal record. A session that leaves no record is failed exploration.

## Standard campaign

Set these shell variables from the repository root:

```bash
PY=".venv/bin/python"
PROBE=".agent/skills/agent-tabs/probe/probe.py"
```

### 1. Establish the current coverage surface

```bash
$PY "$PROBE" coverage --write
```

Read `.agent/skills/agent-tabs/probe/COVERAGE.md` before choosing work. It reports:

- covered, uncovered, and stale claims;
- recorded B001–B003 rate trends;
- proven dead ends;
- ranked unvisited baseline cells.

Select an uncovered or stale claim/cell. Do not re-run a fresh or dead-end exploration unless genuinely new evidence exists.

### 2. Run one real-worker conformance brief

The seeded T4 briefs are `B001`, `B002`, and `B003`.

```bash
$PY "$PROBE" run B001
```

Use `--trials N` only for a deliberate diagnostic or campaign-size decision:

```bash
$PY "$PROBE" run B001 --trials 1
```

A normal brief runs its control and target sequentially. Each default 10-trial brief therefore consumes 20 real worker spawns; all three seed briefs consume 60. Do not parallelize them.

Interpret the result:

| Result | Meaning | Required action |
|---|---|---|
| Exit `0`, `outcome: no-finding` | Target rate met expectation. | Keep the trial evidence; continue with the next selected cell. |
| Exit `0`, `outcome: finding` | Target rate fell below expectation. | Inspect the automatically appended oracle verdict and any quarantined spec. |
| Exit `2` | Control, model, spawn, or harness failure. | Record the error; do not call it a protocol finding. |

Every completed brief appends one rate entry to `ledger.jsonl` and one `trial` entry to `journal.jsonl`. Failed target trials preserve their artifact directories.

### 3. Inspect automatic oracle triage

A measured target `finding` automatically launches the T7 oracle in a separately isolated harness runtime. The oracle reads only the preserved trial's allowed bus/inbox/outbox evidence and appends one `verdict` record.

| Verdict | Meaning | Output |
|---|---|---|
| `code` | Evidence contradicts a cited protocol claim. | Quarantined spec targeting `agentctl.py`. |
| `doc-gap` | Observed behavior has no claim. | Quarantined claim/spec proposal. |
| `doc-rewrite` | Clear claim did not induce compliant worker behavior. | Quarantined `SKILL.md`/`WORKER.md` spec. |
| `harness` | Brief, control, or test timing caused the result. | Verdict only; no spec. |
| `duplicate` | An open quarantined spec already owns the claim. | Verdict only; no spec. |

A `harness` or `duplicate` verdict producing no spec is correct. Do not override it to force a backlog item.

For `code`, `doc-gap`, or `doc-rewrite`, inspect the new `work_organisation/probe/*.md` file. It must retain brief ID, claim ID or `null`, rate, control rate, commit, source journal entry, preserved artifact path, and the sections Overview, Functional Requirements, and Verification & Acceptance Criteria.

Stop after a spec is emitted. Present it and its evidence to a human for a promotion decision.

### 4. Run checks against an existing Agent-Tabs run

Use the run that produced the evidence; do not invent or infer a runtime/run pair.

```bash
$PY "$PROBE" checks --runtime <agent-tabs-runtime-root> --run <run-id>
```

This reads direct run evidence and appends an `explore` journal record containing check and fluency results. It reports clean, violation, suspected, or inconclusive evidence. Treat `suspected` and `inconclusive` as reasons for more evidence, not defects.

### 5. Record manual exploration

Use `explore` only for an investigation that is not already a scheduled brief or check:

```bash
$PY "$PROBE" explore \
  --cell '["C004","dirty-composer","real-haiku","claude",1]' \
  --tried 'specific approach taken' \
  --ruled-out 'artifact-backed conclusion' \
  --outcome inconclusive \
  --fault-proof 'evidence that the injected state occurred'
```

A fresh or proven dead-end cell requires a concrete override:

```bash
--new-information 'specific source, runtime, or evidence change'
```

The override reason is permanent evidence. `dead-end` requires fault proof; absent proof means use `inconclusive` and keep the cell open.

### 6. Close the cycle

```bash
$PY "$PROBE" coverage --write
```

Report all of the following:

1. commands run and exit status;
2. ledger and journal entry IDs;
3. observed control and target rates;
4. preserved artifact paths;
5. oracle verdicts and emitted quarantined spec paths, if any;
6. updated covered/stale/unvisited cells;
7. the next recommended cell or the human decision required.

## Human promotion boundary

The loop ends at evidence or a quarantined spec. A human decides whether to:

1. promote the spec into an active ticket;
2. reject it with rationale; or
3. obtain further evidence.

Only a promoted human ticket authorizes a source change. After such a change, regenerate coverage and re-run the affected brief; changed protocol source should make prior claim evidence stale rather than silently current.
