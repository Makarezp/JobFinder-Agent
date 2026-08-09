# Ticket 006: Delete the Undelivered Bootstrap Message on an Unprovable Spawn

## Overview

When `agentctl.py spawn` cannot prove a Claude worker came up (its `SessionStart`
hook never fires within `--spawn-timeout`), `spawn_agent`'s except-block kills
the tmux window but leaves `inbox/0001.md` (the bootstrap message) on disk.
Because `write_inbox`'s numbering (`next_inbox_path`) just scans for the
highest existing `*.md`, and the "already running" duplicate check
(`agentctl.py:1468`) only rejects a name with a **live** tmux window, a second
spawn of the *same agent name* later in the same run writes its bootstrap as
`0002.md` while the dead spawn's `0001.md` is still sitting there. `WORKER.md`
directs every worker to read its inbox "lowest number first" (claim C014), so
the new worker executes the abandoned, stale assignment before it ever sees
its real one. That is the concrete harm this ticket fixes.

`SKILL.md:103-104` currently claims "a spawn that cannot be proven kills its
own window and cleans up" (probe finding C002,
`work_organisation/probe/explore-20260808T170211424180Z-c002/README.md`,
reproduced twice). That claim is presently false for the bootstrap message and
was previously mis-scoped in this ticket's first draft to also cover
`meta.json`/`settings.json`. It does not need to: those two files are the only
diagnostic record a dead spawn leaves behind (see "Rejected alternatives"
below), and deleting them creates more risk than it removes.

## Implementation Steps

### 1. `.agent/skills/agent-tabs/agentctl.py` — track whether the bootstrap could have been read

In `spawn_agent`, add a new local alongside the existing pre-`try` locals at
`agentctl.py:1477-1479`:

```python
    worktree_path: Path | None = None
    handle: str | None = None
    bootstrap_path: Path | None = None
    bootstrap_delivered: bool = False
```

Set it to `True` immediately before the doorbell block that currently starts
at `agentctl.py:1553` (`if doorbell:`), i.e. as the very first line inside
that `if`:

```python
        if doorbell:
            bootstrap_delivered = True
            if worker_provider is WorkerProvider.CODEX:
                ...
```

This must be set **before** calling `_deliver` or `_bootstrap`, not after they
return successfully. Both can raise (a failed `backend.send`, a `_bootstrap`
that exhausts its two retries), and in every one of those cases the doorbell
keystroke may already have reached the pane — the file may already be read.
Treat "we attempted delivery" as the safety boundary, not "delivery
confirmed succeeded." A failure to prove readiness *before* this point
(covers the ticket's original bug report: the `SessionStart`-timeout raise at
`agentctl.py:1548-1551`) leaves `bootstrap_delivered` `False`, because that
raise happens strictly before line 1553.

### 2. `.agent/skills/agent-tabs/agentctl.py` — delete only the undelivered bootstrap

Replace the cleanup guard in the except-block (`agentctl.py:1570-1583`):

```python
        bootstrap_error_path: str | None = None
        if bootstrap_path is not None and bootstrap_path.exists():
            agent_dir = paths.agent_dir(name)
            other_files = [path for path in agent_dir.rglob("*") if path.is_file() and path != bootstrap_path]
            if not other_files:
                with _suppressed():
                    bootstrap_path.unlink()
                    for child in (paths.inbox(name), paths.outbox(name)):
                        if child.exists() and not any(child.iterdir()):
                            child.rmdir()
                    if agent_dir.exists() and not any(agent_dir.iterdir()):
                        agent_dir.rmdir()
            else:
                bootstrap_error_path = str(bootstrap_path)
```

with:

```python
        bootstrap_error_path: str | None = None
        if bootstrap_path is not None and bootstrap_path.exists():
            if not bootstrap_delivered:
                with _suppressed():
                    bootstrap_path.unlink()
            else:
                bootstrap_error_path = str(bootstrap_path)
```

Do **not** touch `meta.json`, `settings.json`, `inbox/`, `outbox/`, or
`agent_dir` itself — leave them exactly as today. This is deliberately not a
zero-footprint fix (see "Rejected alternatives"). Keep
`bootstrap_error_path` populated only in the case the bootstrap file still
exists afterward (unchanged semantics from today), so the existing
`error_data["bootstrap"] = bootstrap_error_path` line below still reports it
when present — it will simply be absent more often now, since the common
`SessionStart`-timeout failure mode deletes the file.

**Do not** attempt to also fix the case where `add_worktree` (or anything
else before `write_inbox` at `agentctl.py:1485`) raises. In that case
`bootstrap_path` is still `None`, so this fix's condition never applies —
that failure mode leaves an `inbox/`/`outbox/` pair with no `meta.json`
behind (created by the unconditional `paths.ensure_agent(name)` at
`agentctl.py:1474`, which runs before the `try`). It is out of scope for this
ticket: there is no bootstrap file to leak in that case, so the stale-read
hazard this ticket targets cannot occur, and widening scope to that path
risks the same live-window/`UnboundLocalError` mistakes rejected below.

### 3. `.agent/skills/agent-tabs/SKILL.md:103-104` — correct the claim

Current text:

```
There is no sleep-and-hope: a spawn that cannot be proven kills its own window
and cleans up rather than leaving a half-live agent behind.
```

Replace with wording whose two load-bearing facts are: (1) the window kill is
unconditional, (2) only the *undelivered bootstrap message* is removed —
`meta.json`/`settings.json` persist as a diagnostic record and are not
touched by `spawn`. For example:

```
There is no sleep-and-hope: a spawn that cannot be proven kills its own
window and deletes its bootstrap message if it was never delivered. Its
meta.json/settings.json diagnostic record is left in place, same as any
other agent directory without a completed lifecycle.
```

Adjust exact phrasing to fit the surrounding paragraph, but preserve both
facts above. **Before finalizing, count the line span of your replacement in
the actual file** (not this ticket's rendering) — this matters for Step 4.

### 4. `.agent/skills/agent-tabs/probe/claims.jsonl` — recompute C002's hash, and re-`src` anything the edit shifted

`hash_of` (`probe/lib/claims.py:78-84`) hashes the **exact source lines named
by `src`**, read from disk — not the claim's `text` field. Recompute it by
hand from the repo root after Step 3 lands:

```bash
python3 - <<'PY'
import hashlib, pathlib
p = pathlib.Path(".agent/skills/agent-tabs/SKILL.md")
first, last = 103, 104          # update to the new inclusive line range from Step 3
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
print(hashlib.sha256("".join(lines[first-1:last]).encode("utf-8")).hexdigest())
PY
```

Update `C002`'s `src` (if the line range changed) and `hash` fields to match.
Also update `C002`'s `text` field to reflect the corrected claim from Step 3.

If your Step 3 replacement is **not** exactly 2 lines (the current span),
every later claim in `claims.jsonl` whose `src` points into `SKILL.md` at a
line number greater than 104 has shifted by the same delta and must have its
`src` and `hash` updated too — check every entry, not just the ones you
expect (`C003` through at least `C010` at time of writing, all `SKILL.md`
line references). Prefer wording that keeps the replacement at exactly 2
lines so no other entry needs touching; if that is not achievable, do the
full re-`src`/re-hash sweep rather than leaving the rest to go stale.

### 5. `.agent/skills/agent-tabs/probe/journal.jsonl` — record a fresh entry for the C002 cell

The journal is append-only (`probe/lib/journal.py:82`, `cell_status`'s own
docstring: "without mutating its append-only evidence"). Editing `claims.jsonl`
alone does **not** clear the `stale` classification for the journal cell
`["C002","hard-kill","real-haiku","claude","1"]` — its existing entry still
carries the old `claim_hash`. After Step 4, append a new entry for that cell
via `probe.py explore` (do not hand-edit `journal.jsonl`) recording the
verification run from Step 6 below. Use an accurate evidence label for
*this* run — the original entry was labeled `real-haiku`/`claude` but its
evidence was actually a `sleep 300` stub; do not propagate that mislabel into
the new entry.

### 6. Reproduce and verify

The role path and run/runtime flags in the ticket's original draft did not
work as written; use this corrected form from the repo root:

```bash
.agent/skills/agent-tabs/agentctl.py spawn worker \
  --role .agent/skills/agent-tabs/probe/roles/probe-worker.md \
  --task "test task" \
  --binary work_organisation/probe/explore-20260808T170211424180Z-c002/evidence/fake_claude.sh \
  --provider claude --spawn-timeout 3 --viewer none \
  --run probe-c002 --runtime <scratch-runtime-root>
```

(`--role probe/roles/...` fails with `role file not found` unless run from
inside `.agent/skills/agent-tabs/`; use the path above, or `cd` there first.
`--run` is mandatory — `_require_run`, `agentctl.py:2159-2163` — and
`--runtime` should point at a scratch directory so this does not touch a real
run.)

1. **Baseline (before the fix)**, or against the preserved evidence: confirm
   exit code 1, `SpawnError: agent 'worker' never reported SessionStart
   within 3s`, and afterward `agents/worker/inbox/0001.md`,
   `agents/worker/meta.json`, and `agents/worker/settings.json` all still
   present.
2. **After the fix**, re-run the identical command against a fresh run
   directory and confirm: exit code 1, same `SpawnError` message,
   `agents/worker/inbox/0001.md` **gone**, but `agents/worker/meta.json` and
   `agents/worker/settings.json` **still present** (this is the deliberate
   difference from the rejected zero-footprint approach — see below).
3. Confirm `bus.jsonl` still contains the `error` event for this spawn, and
   that its `data` no longer has a `bootstrap` field (the file that field
   used to point at was deleted).
4. **Add a second fixture for the delivered-but-unconfirmed case**, so this
   fix is not verified only on its happy path: a small script that sleeps
   past `--spawn-timeout`, then invokes
   `agentctl.py hook --event SessionStart` (with the `AGENT_TABS_RUNTIME`/
   `AGENT_TABS_RUN`/`AGENT_TABS_AGENT` env the real hook wiring injects) but
   never emits `TURN_START`. This exercises the `_bootstrap` retry-then-raise
   path (`agentctl.py:1592-1609`), where `bootstrap_delivered` must already
   be `True` by the time the except-block runs. Confirm
   `agents/worker/inbox/0001.md` is **not** deleted in this case — the
   doorbell was typed, so the file must be presumed possibly-read.
5. Run `probe.py coverage --write` after Step 5 (the new journal entry) so
   C002 shows as current, non-stale evidence against the fixed source.

### 7. Update the probe finding's own status

`work_organisation/probe/explore-20260808T170211424180Z-c002/README.md`'s
front-matter currently reads `status: open`. Move it to `resolved` and add a
one-line disposition note (this fix; the file it deletes; the files it
deliberately leaves and why).

## Explicit Constraints & Warnings

- **This is not a zero-on-disk-footprint fix, on purpose.** `meta.json` and
  `settings.json` are left behind after a failed spawn, unchanged from
  today's behavior. Do not extend Step 2 to also delete them "while you're in
  there" — see "Rejected alternatives" for why that is unsafe as a same-call
  deletion.
- **`bootstrap_delivered` must be set before attempting delivery, not after
  it succeeds.** Setting it only on a *successful* `_deliver`/`_bootstrap`
  return would leave it `False` in exactly the cases where the doorbell may
  already have been typed (a `_bootstrap` that types twice and only then
  raises) — the one case this flag exists to protect against.
- **Do not add an `other_files`/exclusion-set style scan.** The prior draft's
  approach (excluding `meta.json`/`settings.json` from an `rglob` and
  deleting "everything else") depended on both files having been written
  earlier in the same call, which is not guaranteed if `write_settings`
  itself raises — that construction produces an `UnboundLocalError` inside
  the exception handler that destroys the original `SpawnError` before the
  `error` event is ever written to the bus. This ticket's Step 2 avoids the
  whole class of bug by only ever conditionally deleting one specific file
  this call itself wrote, gated on a boolean, not by computing a set
  difference over the directory.
- **Do not gate the bootstrap deletion on `backend.alive(handle)` or
  similar.** It is unnecessary here (unlike a hypothetical `meta.json`
  deletion): the bootstrap file is never read by anything except the worker
  process reading its own inbox on its first turn, and `bootstrap_delivered`
  already captures "could the worker plausibly have started reading it."
  Whether the tmux window technically still exists after a `_suppressed()`
  `backend.kill` failure does not change whether the file is safe to remove.
- **Do not touch the Codex path's behavior beyond what Step 1/2 already
  cover.** Codex spawns skip `settings.json` (`settings_path` is `None` when
  `worker_provider is WorkerProvider.CODEX`, `agentctl.py:1486`) and can
  reach the doorbell block via the `_deliver` branch (`agentctl.py:1554-1557`)
  rather than `_bootstrap`; `bootstrap_delivered = True` at the top of the
  `if doorbell:` block already covers both branches identically, so no
  provider-specific branching is needed in Step 1/2.
- **No automated oracle exists for this finding.** It is an `explore`-track
  probe finding; verification is manual reproduction only (Step 6).

## Rejected alternatives (recorded so this is not re-litigated)

- **Delete `meta.json`/`settings.json` too, whenever nothing else was
  written this call ("Reading A" in the original draft).** Rejected: if
  `backend.kill(handle)` fails silently (it is wrapped in `_suppressed()`),
  the worker process can still be alive while its `meta.json` is deleted.
  Every `agentctl` command that finds agents does so via `list_agent_names`
  (`agentctl.py:1819-1828`), which requires `meta.json` to exist — deleting
  it would make a possibly-still-running worker invisible to `status`,
  `reap`, and `close-run` alike, i.e. produce the exact "half-live agent"
  the except-block's own comment says it exists to prevent. `settings.json`
  is worse to remove: it is the file the worker process was launched
  with `--settings` (`agentctl.py:1500,1411`) and carries its hook wiring;
  deleting it out from under a still-running Claude process is how you get a
  worker that runs but silently stops reporting anything to the bus.
- **Treat a surviving `meta.json` as the intended, documented behavior
  ("Reading B" in the original draft), and only reword `SKILL.md` to match
  today's code.** Rejected: this was based on a misreading of
  `list_agent_names`'s docstring ("directories *without* a meta.json ... are
  left for reap") — that sentence describes the opposite case from the one
  this finding is about (a leftover *with* a `meta.json`), so it is not
  evidence that today's leftover is intended. It is also independently false
  that `reap` handles this: `apply_reap` (`agentctl.py:1996-2010`) never
  deletes an agent directory, ever — it only appends an `exit` event,
  refreshes the state cache, and removes worktrees. Worse, because
  `meta.json` exists, `list_agent_names` **includes** the dead spawn, so
  `plan_reap` (`agentctl.py:1975-1993`) calls `backend.alive` on the
  already-killed window, gets `False`, classifies it an orphan, and
  `apply_reap` appends an `exit` event for an agent that never started a
  turn — a fabricated lifecycle, not a tidy record. Wording `SKILL.md` to
  match this behavior would have meant documenting a bug as a feature while
  leaving the actual stale-bootstrap hazard (this ticket's real motivation)
  completely unaddressed.

## Acceptance Criteria

- **[Manual]** Reproducing the fixture spawn (Step 6.2) against a fresh run
  after the fix exits 1 as before (`SpawnError`, `SessionStart` timeout
  unchanged), but `agents/worker/inbox/0001.md` does not exist afterward,
  while `agents/worker/meta.json` and `agents/worker/settings.json` do.
- **[Manual]** `bus.jsonl` still contains the `error` event for the failed
  spawn, now without a `data.bootstrap` field.
- **[Manual]** The delivered-but-unconfirmed fixture (Step 6.4) confirms
  `inbox/0001.md` is **not** deleted when `bootstrap_delivered` was set
  before the failure.
- **[Manual]** `SKILL.md:103-104` (or wherever the edited lines land) states
  both: the window kill is unconditional, and only the undelivered bootstrap
  is removed while the diagnostic record persists.
- **[Manual]** `claims.jsonl`'s `C002` entry's `hash` matches the actual
  post-edit `SKILL.md` source lines named by its `src` (verified via the
  Step 4 recipe, not by inspection), and every other `SKILL.md`-sourced claim
  entry whose lines shifted has been re-`src`/re-hashed to match.
- **[Manual]** A new `probe.py explore` entry exists for the
  `["C002","hard-kill","real-haiku","claude","1"]` journal cell reflecting
  the post-fix state, and `probe.py coverage --write` shows C002 as current
  rather than stale.
- **[Manual]** `work_organisation/probe/explore-20260808T170211424180Z-c002/README.md`'s
  front-matter status is `resolved` with a one-line disposition note.
