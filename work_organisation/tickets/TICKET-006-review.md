# Review: TICKET-006 — Resolve the Unreachable Cleanup Branch on an Unprovable Spawn

Reviewer: defensive-architect (review-006). Source read at commit `e8ec234` + working tree.
Everything below was verified against the current files, not against the ticket's own prose.

## Verdict

**Do not execute this ticket as written.** The underlying probe finding is real and
correctly observed, and — unusually — every line number it cites is accurate. But the
ticket's central structure is wrong in three ways, each independently blocking:

1. **The "Reading A vs Reading B" fork is false.** Reading B rests on a misreading of
   `list_agent_names`'s docstring, and its proposed replacement wording states something
   that is itself untrue about `reap`. Reading B cannot be chosen as written.
2. **Reading A's patch, exactly as specified, introduces a reachable `UnboundLocalError`
   in the except-block** that would swallow the original spawn error, plus two ways to
   delete files out from under a still-live worker.
3. **Step 3's claims.jsonl instruction is factually wrong** about how the hashes are
   computed, and its acceptance criterion is unachievable under Reading B for a reason
   the ticket never mentions (the journal is append-only).

There is also a **third reading the ticket misses**, which is both the real harm and the
smallest correct fix. See §3.

---

## 1. Line-number audit — all citations verified correct

Ticket line numbers usually rot. These did not. Verified against the working tree:

| Ticket citation | Actual | OK |
|---|---|---|
| `agentctl.py:1561-1589` (except-block) | `except Exception as exc:` @1561 … `raise` @1589 | ✓ |
| `agentctl.py:1819-1828` (`list_agent_names`) | `def list_agent_names` @1819, closes @1828 | ✓ |
| `agentctl.py:1486` (`settings_path` is `None` for Codex) | exact line | ✓ |
| `agentctl.py:1544-1547` (Codex synthetic `SPAWNED`) | exact lines | ✓ |
| `agentctl.py:1485-1542` ("wrote both files earlier this call") | `write_inbox` @1485, `write_settings` @1486, `meta().write_text` @1542 | ✓ |
| `SKILL.md:103-104` | the sleep-and-hope sentence | ✓ (proved by hash, below) |
| `claims.jsonl:2` is `C002` | ✓ | ✓ |
| Quoted `other_files` code block | matches `agentctl.py:1570-1576` verbatim | ✓ |

The quoted guard is byte-accurate. No corrections needed in this section.

## 2. Reading B is not a live option — it is disproved by three separate facts

The ticket (and the probe README, which the ticket inherits this from) both cite
`list_agent_names`'s docstring as evidence that a surviving `meta.json` is *intended*:

> "Directories without a meta.json are spawns that died before recording anything;
> they are skipped here and left for `reap`."

**2a. The docstring describes the opposite case.** It talks about directories *without*
a `meta.json`. The leftover the probe found *has* a `meta.json` (it is the whole point of
the finding). So the docstring is not evidence about this case at all.

Worse for the ticket: the case the docstring describes is **also real and also
unhandled**, and neither reading covers it. `paths.ensure_agent(name)` runs at
`agentctl.py:1474`, *outside* the `try`. If the spawn fails before `write_inbox`
(`add_worktree` @1482 raising, `_worker_argv`/`backend.open` raising), `bootstrap_path`
is `None`, the outer guard at :1571 is false, **no cleanup runs at all**, and an
`agents/<name>/{inbox,outbox}` pair with no `meta.json` is left behind. That is precisely
the directory the docstring is talking about. Any ticket claiming to establish a
"zero on-disk footprint" contract (Reading A) must cover this too, and this one does not.

**2b. `reap` does not delete agent directories — ever.** `apply_reap`
(`agentctl.py:1996-2010`) does exactly three things: appends an `exit` event for orphan
agents, refreshes the state cache, removes stale *worktrees*, and optionally kills the
tmux session. It never touches `agents/<name>/`. So Reading B's proposed wording —

> "is left in place for `reap` rather than deleted"

— would replace one false claim in `SKILL.md` with a different false claim. Nothing
deletes that record for the life of the run directory. If Reading B were ever chosen,
the wording would have to say the record *persists*, not that `reap` handles it.

**2c. The leftover is not inert; it is an active phantom agent.** Because `meta.json`
exists, `list_agent_names` **includes** the dead spawn. Every command that enumerates
agents therefore sees it: `list`, `status`, `close-run` (:2024), and `plan_reap` (:1979).
`plan_reap` loads its meta, calls `backend.alive(meta.handle)` on the window the
except-block already killed → `False` → classifies it as an **orphan**, and `apply_reap`
appends an `exit` event for an agent that never started a turn. So the current behavior
is not "a tidy reap-able record"; it is a record that manufactures a fake lifecycle.

**Conclusion:** Step 1 must not be presented to a human as a balanced either/or. The
honest framing is: the code is wrong, and the only question is *how much* it should clean
up. Correct the ticket to say so, or the human is being asked to arbitrate on a premise
that does not survive reading the code.

## 3. The missing third reading — and the smallest correct fix

Neither reading names the concrete harm. It is this:

`write_inbox` (:472) numbers messages by scanning existing `*.md` (`next_inbox_path`
:460-469). The failed spawn leaves `inbox/0001.md`. A spawn of the **same agent name**
later in the same run is permitted — the duplicate check at :1468 only rejects names with
a *live tmux window* — so the new bootstrap is written as `0002.md` while the dead
spawn's `0001.md` is still sitting there. `WORKER.md:9-14` (registry claim **C014**,
"the worker re-reads its inbox at the start of every turn, **lowest number first**")
then guarantees the new worker reads the *stale* bootstrap first and executes the
previous, abandoned assignment.

That is a live foot-gun, and it is the thing that actually needs fixing. It also settles
the design question: the file that must not survive is the **bootstrap inbox message**.
`meta.json`/`settings.json` are diagnostic and, per §2c, at worst cosmetic noise.

**Reading C (recommended):** on a failure before the readiness proof, delete the
bootstrap message unconditionally (it is provably this call's own file, and provably
unread — no turn ever started), and leave `meta.json`/`settings.json` as the diagnostic
record. Then `SKILL.md` says: window killed, undelivered bootstrap removed, diagnostic
record persists. That is one small unlink, no exclusion-set machinery, no risk of
deleting a live worker's configuration, and it closes the stale-bootstrap hazard that
Reading A closes only incidentally and Reading B leaves wide open.

If Reading C is adopted, gate it on the failure stage: the `_bootstrap` path (:1592) has
already *typed* the doorbell, so on that path the file may have been read. Condition the
unlink on the failure having occurred before `_bootstrap` was entered (e.g. a flag set
just before the `if doorbell:` block at :1553), not on file contents.

## 4. Reading A's patch as specified — three defects, one of them a crash

### 4a. BLOCKER: `settings_path` can be unbound inside the except-block

The ticket instructs:

```python
{bootstrap_path, paths.meta(name), *([settings_path] if settings_path else [])}
```

`settings_path` is assigned at :1486. `bootstrap_path` is assigned at :1485. If
`write_settings` itself raises — an `OSError` from :1216's `write_text` (permissions,
ENOSPC, a runtime root on a full or read-only volume) — then `bootstrap_path` is set (so
the outer guard at :1571 is **true** and we enter the branch) while `settings_path` was
never bound. Evaluating the ticket's expression raises `UnboundLocalError` **inside the
exception handler**, before `append_event(... EventType.ERROR ...)` at :1588. Net effect:
the original `SpawnError` is replaced by an unrelated `UnboundLocalError`, the tmux
window has already been killed, and **no `error` event is written to the bus at all** —
destroying exactly the failure signal the except-block's own comment (:1562-1563) promises
to preserve.

**Required correction:** hoist the declaration alongside the other pre-`try` locals at
:1477-1479:

```python
    worktree_path: Path | None = None
    handle: str | None = None
    bootstrap_path: Path | None = None
    settings_path: Path | None = None      # must be bound before the try
```

and drop the assignment's `= ` into `settings_path = write_settings(...) if ... else None`
unchanged. The ticket's "this is safe specifically because `spawn_agent` wrote both files
earlier in this same invocation" is the *reason for* the bug: it assumes both writes
completed, which is exactly what is not true on the path that reaches the handler.

### 4b. The cleanup can delete a live worker's `settings.json` and its only record

`backend.kill(handle)` at :1566 is wrapped in `_suppressed()`. If the kill fails
(tmux server hiccup, a window that has already been renamed, an `EPERM`), the worker
process is still running. Today that is survivable: `meta.json` persists, so
`list_agent_names` still sees the agent, and `reap`/`close-run`/`reconcile` can find and
kill the window afterwards. Under Reading A's patch, `meta.json` and `settings.json` are
deleted anyway — the live window becomes invisible to every agentctl command (all of them
enumerate via `list_agent_names`), and `reap --all` will not even kill the session,
because `backend.list_handles(paths.run)` is non-empty (:1993). The patch would create
the precise "half-live agent" the comment at :1562 exists to prevent.

Deleting `settings.json` is independently hostile: it is the `--settings` file the worker
was launched with (:1411) and it carries the hook wiring (:1210-1216). Removing it from
under a running Claude is how you get a worker that runs but reports nothing.

**Required correction:** gate the whole deletion on the window being confirmed gone:

```python
            window_gone = handle is None or not backend.alive(handle)
            if not other_files and window_gone:
```

### 4c. The `other_files` exclusion set is incomplete, and the branch races the hook

`state.json` (`paths.state`, :197) is written by `refresh_state_cache` (:546-554), which
is called by the hook handler at :2225 on **every** hook event — and which also calls
`paths.ensure_agent(agent)`, recreating `inbox/` and `outbox/`.

Two consequences the ticket does not consider:

- **On the `_bootstrap`-failure path** (SessionStart *did* fire, `TURN_START` never did —
  `_bootstrap` raises at :1607), `state.json` already exists. It is not in the ticket's
  exclusion set, so `other_files` is non-empty and no cleanup happens. That is arguably
  the right outcome, but it means the ticket's answer to "does the fix cover a failure
  after the doorbell?" is **no** — silently, by accident, not by design. If that is the
  intent, say so in the ticket; if not, the fix does not do what its Overview claims.
- **A late-firing SessionStart races the cleanup.** If the hook lands just after
  `wait_for_event` times out, it can write `state.json` and re-`mkdir` `inbox`/`outbox`
  *after* the `rglob` snapshot at :1573 and *after* the `rmdir`s at :1577-1581. Result:
  the directory is resurrected containing only `state.json` — no `meta.json`, so
  `list_agent_names` now skips it entirely and it is invisible to `status` and `reap`
  alike, while the worker that wrote it may still be alive (§4b). The `_suppressed()`
  wrapper means every failed `rmdir` in this sequence is silent.

The `backend.alive` gate in §4b narrows this substantially (a worker whose window is
confirmed dead is not going to fire more hooks) but does not close it; the snapshot is
still non-atomic. At minimum the ticket must state this residual race explicitly rather
than assert the fix "is safe".

**Worktree / Codex paths, checked and clear.** `--worktree`: if `remove_worktree` (:1569,
also `_suppressed()`) fails, deleting `meta.json` does *not* orphan the worktree —
`plan_reap` finds stale worktrees by scanning `paths.worktrees` for directories not owned
by a live agent (:1990-1991), not via meta. No defect. Codex: confirmed it cannot reach
the `SessionStart` timeout branch (:1544-1547), and `settings_path is None` makes the
exclusion set degrade correctly. The ticket's constraint here is accurate.

## 5. Step 3 (claims.jsonl) is factually wrong about the hash

The ticket says:

> "the existing entries hash the claim text — follow the same method used for the other
> entries in this file"

They do not. `probe/lib/claims.py:78-84`, `hash_of`, hashes **the exact inclusive source
lines named by `src`**, read from disk:

```python
lines = path.read_text(...).splitlines(keepends=True)
return hashlib.sha256("".join(lines[first - 1 : last]).encode("utf-8")).hexdigest()
```

Verified empirically against C002:

- sha256 of `SKILL.md` lines 103-104 → `577a578919cf…f06b6` — **matches** the stored hash.
- sha256 of the claim `text` string → `403730fff92a…72c886` — does not match anything.

An agent following step 3 literally would write a wrong hash, and `stale()`
(`claims.py:87-99`) would then report C002 as drifted forever. **Required correction —
the exact recipe**, from the repo root:

```bash
python3 - <<'PY'
import hashlib, pathlib
p = pathlib.Path(".agent/skills/agent-tabs/SKILL.md")
first, last = 103, 104          # update to the new inclusive range
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
print(hashlib.sha256("".join(lines[first-1:last]).encode("utf-8")).hexdigest())
PY
```

There is no `--rehash` subcommand; `probe.py` exposes only `coverage`, `checks`, `run`,
`explore`. The edit is by hand.

Three further consequences step 3 misses, **all specific to Reading B**:

- **Editing `SKILL.md` shifts every later claim's line range.** The replacement wording
  proposed in step 2b is 4 lines against the current 2, i.e. **+2**. `src` for C003
  (`SKILL.md:120-123`), C005, C006, C007, C008, C009 and C010 would all then point at the
  wrong lines and every one of them goes stale. The ticket only mentions updating C002's
  `src`. Any Reading-B edit must either be line-count-neutral or re-`src`/re-hash seven
  further entries.
- **`journal.jsonl:17` pins the same hash.** The C002 explore entry carries
  `claim_hash: 577a578919cf…`, and `journal.py:88-92` marks a cell `stale` when the
  latest entry's `claim_hash` differs from the current one. The journal is **append-only**
  by design ("without mutating its append-only evidence", `journal.py:82`). So under
  Reading B the acceptance criterion *"C002 is not shown as stale evidence"* **cannot be
  met by the listed steps** — it requires recording a new `probe.py explore` entry for
  cell `["C002","hard-kill","real-haiku","claude","1"]` after the doc edit. Add that step
  or drop the criterion.
- **Under Reading A that same criterion is a no-op.** The hash covers `SKILL.md`, which
  Reading A does not touch. C002 is *not* stale today (verified above), so
  `probe.py coverage --write` changes nothing about it. The drift detector tracks doc
  drift only and never notices the code fix. Stating that plainly is more honest than an
  acceptance criterion that passes before the work starts.

## 6. Step 4's reproduction command does not run as written

```
agentctl.py spawn worker --role probe/roles/probe-worker.md --task "test task" \
  --binary work_organisation/probe/.../fake_claude.sh --provider claude --spawn-timeout 3 --viewer none
```

- **`--role probe/roles/probe-worker.md` does not exist from the repo root.** The file is
  at `.agent/skills/agent-tabs/probe/roles/probe-worker.md`. `spawn_agent` rejects this at
  :1466 with `role file not found` — before it ever reaches the code under test. (The
  ticket inherited this path from the probe README, where it was relative to the tool
  directory; the ticket adds "From the repo root" and breaks it.)
- **No `--run` and no `--runtime`.** `_require_run` (:2159-2163) raises
  `a run id is required` unless `$AGENT_TABS_RUN` is set, and "against a fresh
  runtime/run" is unachievable without `--runtime`. The preserved evidence used a
  scratchpad runtime root and run `probe-c002`. Both flags must be in the command.
- Verified fine: `--viewer none` is a registered viewer (`VIEWERS`, :708);
  `fake_claude.sh` is `+x`; `shutil.which` accepts the path form; and
  `_known_provider` reads "claude" out of `fake_claude.sh`, so `--provider claude` does
  not trip the drift check at :1361.

**The deeper problem with this verification: the fixture is `sleep 300`.** It never fires
a hook, so it can never exercise the late-hook race in §4c or the live-window case in
§4b — the only two ways the proposed patch does damage. A green run of step 4a proves the
happy path and nothing else. If Reading A or C is chosen, add a second fixture that fires
the SessionStart hook *after* the `--spawn-timeout` window (a shell script that sleeps
4s, then invokes `agentctl.py hook --event SessionStart` with the injected
`AGENT_TABS_*` env, against `--spawn-timeout 3`) and assert that the resulting directory
state is coherent — not a `state.json`-only orphan.

## 7. Smaller corrections

- **Step 4a.3 understates the change.** Under Reading A the `error` event survives, but
  `data.bootstrap` **disappears** (it is only set at :1583 when cleanup is skipped). The
  preserved evidence `bus.jsonl` shows that field, so the criterion should read: the
  `error` event is still present *and* no longer carries `bootstrap`.
- **The probe finding's own front-matter is never updated.** `explore-…-c002/README.md`
  carries `status: open`. Whichever reading lands, that must move to resolved and record
  the disposition; the ticket's acceptance criteria omit it entirely.
- **Evidence-labeling nit.** The C002 journal cell is labeled `real-haiku` / `claude`,
  but the preserved evidence was produced by a `sleep 300` stub, not a real worker. Not
  this ticket's bug, but if a new journal entry is appended (§5), do not repeat the label.

## 8. What must change before this ticket is executable

1. Rewrite Step 1. Reading B is disproved (§2); present Reading A vs **Reading C** (§3),
   with the stale-bootstrap re-spawn hazard as the stated motivation.
2. If Reading A survives that: add the `settings_path: Path | None = None` hoist (§4a) —
   this is a crash, not a style note — the `backend.alive` gate (§4b), an explicit
   statement about `state.json` / the `_bootstrap` path / the residual race (§4c), and a
   decision on the pre-`write_inbox` failure case at :1474 (§2a).
3. Replace Step 3's hash sentence with the source-line recipe (§5), and add the
   line-shift and append-only-journal consequences for Reading B.
4. Fix the Step 4 command (role path, `--run`, `--runtime`) and add the late-hook fixture
   (§6).
5. Drop or reword the `coverage --write` acceptance criterion, which is a no-op under
   Reading A and unachievable under Reading B as specified (§5).
