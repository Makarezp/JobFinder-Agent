# Review: TICKET-008 — Per-tab tmux current-window pointer for `ItermTabViewer`

**Reviewer:** review-008 (Defensive Architect)
**Verdict:** **The fix direction is correct and the mechanism works — but do not execute the ticket as written.** Step 3 ("no changes to `close_agent`/`close_run`/`kill_run`") rests on a factual claim about tmux that is **false**, and the ticket elevates that false claim into a hard constraint forbidding the only correct cleanup. Implemented as specified, TICKET-008 fixes the input-misdirection bug and simultaneously **breaks run teardown**: `close-run` stops being able to destroy a run, and one of the ticket's own acceptance criteria becomes unsatisfiable.

Everything below was verified against tmux 3.7b (`/opt/homebrew/bin/tmux`, the version this file's docstrings claim verification against) with live sessions and real attached clients, not against the man page alone. Command transcripts are in the appendix.

---

## F1 — BLOCKER: the auto-cleanup premise is false. A grouped session never reaches zero windows.

Step 3 states, as settled fact:

> `kill-window` removes that window from every session in its group, including the grouped viewer session. A tmux session that reaches zero windows is destroyed automatically by tmux itself … So once an agent's window is killed, its grouped viewer session (if any) disappears on its own.

The first sentence is true. The conclusion does not follow, because **a grouped session shares the group's entire window list — not just the one window the viewer selected.**

`TmuxBackend.open` (`agentctl.py:781-791`) creates every run session with a permanent placeholder window:

```python
if not self._session_exists(run):
    self._tmux("new-session", "-d", "-s", run, "-n", ROOT_WINDOW)  # line 783
```

`ROOT_WINDOW` (`__root__`, line 722) is never killed by `close_agent` — it belongs to no agent. It is filtered out of `list_handles` (line 879) precisely because it is not an agent. So the group's window list is always `{__root__} ∪ {agent windows}`, and a viewer session joined to that group holds **all of them**:

```
$ tmux new-session -d -s t008base -n __root__
$ tmux new-window -d -t '=t008base' -n agentA   -> @1329
$ tmux new-window -d -t '=t008base' -n agentB   -> @1330
$ tmux new-session -d -t '=t008base' -s 't008base--viewer--@5'
$ tmux list-windows -t '=t008base--viewer--@5' -F '#{window_id} #{window_name}'
@1328 __root__
@1329 agentA
@1330 agentB
```

Killing the agent's window leaves the viewer session with two windows, and its client still attached:

```
$ tmux kill-window -t @1348          # what close_agent does
$ tmux list-clients -F '#{client_session} #{window_id} #{window_name}'
v4a @1346 __root__                   # client survived, silently moved to __root__
$ tmux list-sessions | grep v4a
v4a: 2 windows (attached)
```

The viewer session would only self-destruct if the *whole run* were emptied — i.e. never, while `__root__` exists.

**Consequence:** the ticket's manual acceptance criterion *"Close the first agent with `agentctl close` … confirm no grouped viewer session for that agent remains"* **will fail**, and step 3's instruction "Trace why before touching them, so this doesn't get 'fixed' a second time" will send the implementer to defend a conclusion that the machine contradicts.

**Required correction:** Strike step 3's claim. Replace it with the measured behaviour: *a grouped viewer session outlives its agent's window and must be destroyed deliberately or by group-scoped teardown (F2).*

---

## F2 — BLOCKER: `close_run` stops working. `kill-session -t <run>` is not group-scoped, and the constraint forbidding a fix is based on F1's false premise.

This is the serious one. `TmuxBackend.kill_run` (`agentctl.py:883-885`) is the **backstop** of the whole teardown story — `close_run` (2013-2032) runs `close_agent` per agent inside `_suppressed()` (2029-2030, every failure swallowed) and then relies on `kill_run` to guarantee the run is actually gone. tmux's own man page says exactly what `kill-session` does *not* do:

> **kill-session** — Destroy the given session, closing any windows linked to it **and no other sessions**, and detaching all clients attached to it.

Windows in a session group are linked to every session in the group. So `kill-session -t '=<run>'` now destroys the base session and **nothing else**. Verified end-to-end, simulating the full `close_run` sequence with a live viewer client attached:

```
$ tmux kill-window -t @1348     # close_agent: agentB
$ tmux kill-window -t @1347     # close_agent: agentA
$ tmux kill-session -t '=t008b4'   # kill_run
$ tmux list-sessions | grep -E 't008b4|v4a'
v4a: 1 windows (attached)          # <-- run "destroyed"; viewer session and __root__ still alive
$ tmux list-clients | grep v4a
v4a @1346 __root__                 # <-- human's tab still attached, forever
```

And when the per-agent kills *don't* all succeed — the case `kill_run` exists to cover — the agent windows themselves survive too, still running their workers:

```
$ tmux kill-session -t '=t008base'          # base session killed
$ tmux list-windows -t '=t008base--viewer--@5' -F '#{window_id} #{window_name}'
@1328 __root__
@1330 agentB                                # live agent window, orphaned into the viewer session
```

So the ticket's final acceptance criterion — *"Run `agentctl close-run` … confirm both grouped viewer sessions and the run's base session are all gone"* — is **unsatisfiable by construction** under the specified implementation. And `apply_reap` (2009-2010), which calls the same `kill_run`, inherits the identical hole: `reap` can no longer clean a run either.

**The fix is one flag**, and it is already in tmux:

> **kill-session** `[-aCg]` — *If `-g` is given and the session is in a session group, all sessions in the group are killed.*

Verified, including the no-group case so it is safe unconditionally:

```
$ tmux kill-session -g -t '=t008b6'    # base + 2 grouped viewer sessions
$ tmux list-sessions | grep t008b6     -> (all gone)
$ tmux list-windows -a | grep @1400    -> (agent window gone too)
$ tmux kill-session -g -t '=t008solo'  # ungrouped session
                                       -> OK, no error
```

```python
def kill_run(self, run: str) -> None:
    if self._session_exists(run):
        # -g kills every session in the run's session group. Viewer clients
        # attach via grouped sessions, and kill-session without -g destroys
        # "any windows linked to it and no other sessions" -- the group's
        # windows (including __root__) survive in the grouped sessions and
        # the run is not actually torn down.
        self._tmux("kill-session", "-g", "-t", self._target(run))
```

**This requires amending the ticket's own constraint**, which currently reads:

> **Do not change `TmuxBackend.open`, `.kill`, `.alive`, `.list_handles`, or `.kill_run`.** … `Backend` must stay ignorant of viewers.

The constraint's *rationale* survives; its *conclusion* does not. `-g` does not teach `Backend` anything about viewers: a session group is a tmux concept, and "tear down the run's session group" is a strictly more correct definition of `kill_run` than "tear down one session that happens to be named after the run." It stays true even if the grouped session was created by a human running `tmux new-session -t` by hand — which is more than can be said for any viewer-aware cleanup. **`Backend` remains viewer-ignorant; it merely stops being group-ignorant.**

**Required correction:** Add a step: *change `TmuxBackend.kill_run` to `kill-session -g`.* Amend the "do not change" constraint to exempt `kill_run`, and record why (F1 + the man-page semantics above). Add a unit test against the tmux fake/`FakeBackend` asserting the `-g` argv, and the live test in F5.

---

## F3 — MAJOR: after `agentctl close`, the human's tab silently jumps to a different window and stays there

Verified twice (F1 transcript): when the agent's window is killed, the viewer client does not exit — tmux moves it to the session's *last-window* pointer, observed as `__root__`:

```
before: v4a @1348 agentB
after kill-window @1348:  v4a @1346 __root__
```

Two things follow.

1. **This is not the "tab closes itself" behaviour the ticket implies.** The tab stays open showing a bare shell in the run's placeholder window, indefinitely, and the session leaks until the human closes the tab (`destroy-unattached` then collects it — that part does work, see "What holds up"). The ticket has no acceptance criterion for what the human's tab shows after a close; it should.

2. **The fallback target is not guaranteed to be harmless.** It is the viewer session's last-window pointer, which is `__root__` only because nothing else ever selects a window in that session. The moment the human navigates inside their own tab (`C-b n`, `C-b w`) — which is a perfectly ordinary thing to do in an attached tmux client — the last-window pointer becomes some other agent's window, and closing their agent drops them onto **a live sibling agent's composer with no visual signal**. That is the *same failure class* TICKET-008 exists to eliminate, narrowed to a smaller window of opportunity rather than removed.

**Required correction (choose one, explicitly, in the ticket):**

- **(a) Preferred — give the viewer the other half of its own lifecycle.** Add `conceal(run, handle)` to the `Viewer` protocol (`agentctl.py:611-622`), no-op on `NullViewer`, and call it from `close_agent` next to `backend.kill(meta.handle)` (1943/1951). This respects the stated boundary exactly: the viewer, not the backend, knows viewer sessions exist. It introduces **no second source of truth** — the session is found from tmux's own group listing (see F6 for why *reconstructing* the name is the wrong way to find it):
  ```
  tmux list-sessions -F '#{session_name}\t#{session_group}'   # filter group == run, name endswith handle
  tmux kill-session -t '=<that name>'                         # client detaches; tab returns to a shell
  ```
  The ticket's blanket ban ("Do not solve this by tracking grouped session names in `agentctl`'s own state") is aimed at *stored* state and is right about that. Deriving the target from live `tmux list-sessions` output is not stored state and does not drift.
- **(b) Accept and document it.** If (a) is out of scope, the ticket must say so plainly: *"After `agentctl close`, the agent's tab remains attached and shows `__root__`; its viewer session persists until the human closes the tab or `close-run` runs."* Then delete the acceptance criterion that says the grouped session is gone after a graceful close, and add one asserting the tab lands on `__root__` and never on another agent's window.

Silently shipping (b) while the ticket promises (a) is the outcome to avoid.

---

## F4 — MAJOR: `set-option` scoping is correct today, but the failure mode is the destruction of the entire run — assert it properly

Step 1 flags this as undecided ("check whether it needs `-t <viewer-session-name>` explicitly"). Measured answer on 3.7b: **the un-targeted form is correctly scoped to the newly created session.**

```
$ tmux show-options -t t008b2       destroy-unattached   ->            (unset)
$ tmux show-options -t 'vw--@1333'  destroy-unattached   -> destroy-unattached on
$ tmux show-options -t 'vw--@1334'  destroy-unattached   -> destroy-unattached on
```

So the ticket's sketch works. That is not a reason to ship it un-targeted, because of the asymmetry of the failure:

- If it lands on the viewer session (today's behaviour): correct.
- If it ever lands on the **base run session** — a tmux version change, a reordering of the `\;` chain, someone inserting a command before it — then `destroy-unattached on` is set on the run itself, and **the entire run with every agent in it is destroyed the moment the last human tab detaches.** Silent, total, unrecoverable work loss, triggered by closing a terminal tab.

A one-token defence exists and is verified working:

```
$ tmux set-option -t 'My "Run"\Two--viewer--@5' destroy-unattached on   -> OK
```

**Required correction:** Pass `-t <viewer-session-name>` (shell-quoted, like every other embedded value) explicitly. Then the ticket's proposed test *"asserting the emitted command contains `set-option destroy-unattached on` scoped to the grouped session, not the base run session"* becomes an assertion that can actually fail — as written against the un-targeted form, that test asserts a substring and verifies nothing about scoping, since the string is identical in the correct and catastrophic cases. Add: `assert argv[argv.index("set-option") + 2] == <viewer session name>` and `assert tmux_target(run) not in argv[i:i+3]`.

Also add a **live** assertion to step 5's manual protocol: `tmux show-options -t '=<run>' destroy-unattached` must print nothing. No string test can cover this.

---

## F5 — MAJOR: the test plan is 100% string assertions and cannot observe a single finding above

Step 4 rewrites the command-string tests and adds two more string tests. Every defect in F1, F2, F3 — teardown leaking the run, the tab jumping to another window, `close-run` no longer destroying anything — is invisible to all of them, because `test_viewer.py` never touches tmux by design (module docstring, lines 1-9). The ticket's only real coverage for those is step 5's manual repro, which is the one thing that does not run in CI.

Note the shape of the existing suite's own hard-won lesson: the round-trip test exists because *"a broken separator can slip past a test that 'looks right'"*, and the `\;` bug and the `=cvv` zsh bug were both **caught by live spawns, not by string tests** (`agentctl.py:659-673`, `679-689`; `test_viewer.py:66-75`). TICKET-008 changes tmux *semantics*, not just a string — the string tests are even less load-bearing here than they were for the escaping bugs.

There is live-tmux test infrastructure in this repo already (the `sut-*` sessions from `tests/`), so this is not a new capability.

**Required correction — add these to step 4:**

1. **Live teardown test** (no iTerm needed; the grouped session is created directly, exactly as the emitted command would):
   ```
   create run session + 2 agent windows -> create 2 grouped sessions joined to it
   -> close_run(...) -> assert no session has session_group == run, and neither agent window survives
   ```
   This fails today against the ticket's implementation and passes with F2's `-g`.
2. **Live "does the fix actually fix it" test:** two grouped sessions, `select-window` in one, assert the other's `#{session_name}:#{window_id}` is unchanged and the base session's current window is still `__root__`. This is the only automated proof that the bug is gone; the ticket currently has none.
3. **Base-session option test:** after building a grouped session, assert `show-options -t '=<run>' destroy-unattached` is empty (F4).
4. **`kill_run` argv test** against the existing backend fake, asserting `-g` is present (F2).

The ticket's claim that `test_reveal_raises_viewer_error_on_nonzero_exit_carrying_stderr`, `test_null_viewer_*`, `test_get_viewer_*` and `test_both_viewers_satisfy_the_protocol` need no changes is **correct** — none of them inspect the command string. (If F3(a) is taken, `test_both_viewers_satisfy_the_protocol` and `NullViewer` do change: the protocol grows `conceal`.)

---

## F6 — MODERATE: tmux mangles backslashes in session names, so the derived name is not a reliable *target*. Use the group, not the name.

Step 2 proposes deriving `f"{run}--viewer--{handle}"`. The derivation is fine for *creation*. It is not safe as a way to *find* the session later — which matters for F3(a) and for any manual cleanup. tmux 3.7b stores a backslash in a session name doubled, and the original string then cannot address it:

```
$ tmux new-session -d -s 'a\b' -n w1
$ tmux list-sessions -F '[#{session_name}]'   ->  [a\\b]
$ tmux has-session -t '=a\b'    ->  can't find session: a\b
$ tmux has-session -t '=a\\b'   ->  FOUND
```

Names containing `:` or `.` are accepted at creation on 3.7b (`a.b`, `a:b` both created fine) but `-t 'a:b'` parses as *session `a`, window `b`* — so those are unaddressable by name too. Demonstrated while cleaning up after this review: both scratch sessions had to be killed by `#{session_id}` (`$672`, `$673`), because `tmux kill-session -t 'a.b'` answers `can't find window: a` and `-t 'a:b'` answers `can't find session: a`. So a name-reconstruction cleanup silently no-ops on exactly the run ids the suite's hostile test is meant to model.

**Required correction:** wherever a viewer session must be located after the fact, enumerate `tmux list-sessions -F '#{session_name}\t#{session_group}'` and match on `session_group == run`, never rebuild the name and target it. F2's `kill-session -g` is immune by construction — another reason to prefer it.

**Out-of-scope finding worth recording separately (pre-existing, not caused by this ticket):** the same mangling already breaks `TmuxBackend` for such a run *today*:

```
$ tmux new-session -d -s 'My "Run"\Two' -n __root__          -> OK
$ tmux new-window -d -t '=My "Run"\Two' -n agentA            -> can't find window: My "Run"\Two
```

So a run whose id contains a backslash cannot have a second agent opened into it, `_session_exists` returns False for it forever, and `kill_run` never kills it. `test_reveal_round_trips_a_hostile_run_id_through_both_escaping_layers` uses `'My "Run"\\Two'` and certifies the shell/AppleScript layers for an input that **tmux itself rejects one layer deeper** — the test is passing on a run that cannot exist. That is a false sense of safety in the suite's flagship test, and no run-id validation exists in `agentctl.py` (the only validators are `validated_worktree`, 1148, and `_validate_initial_task`, 1253). File it as its own ticket: either validate run ids at entry or fix targeting; do not fold it into 008.

---

## F7 — MODERATE: `reveal()` cannot detect that the tmux command inside the tab failed, and the new command has more ways to fail

`reveal()` returns success whenever **osascript** exits 0 (`agentctl.py:703-705`). Everything after that — whether tmux attached, whether the window was found — happens inside the human's tab, invisible to `agentctl`, and the spawn path deliberately swallows even real exceptions (`1512-1519`). This is pre-existing, but TICKET-008 widens the failure surface from one subcommand to three:

- `new-session -s <name>` **fails outright if that session name already exists** (`duplicate session: …`), leaving the tab at a shell prompt with an error and no attachment. Reachable whenever `reveal` runs twice for the same handle — not on today's single call site (1512), but it is a live trap for any future `agentctl reveal`/`show` subcommand, which F9 argues is needed.
- `select-window -t <handle>` fails if the agent died between `backend.open` and `reveal`; the client then sits on `__root__`.

Do **not** "fix" the first with `new-session -A`: `-A` makes it attach to the existing session instead, which puts two tabs back on one shared current-window pointer — the original bug, reintroduced on the retry path.

**Required correction:** state in the ticket that a failed tmux command inside the tab is undetectable by `reveal`, and pick the collision policy deliberately (recommended: no `-A`; let the duplicate error surface in the tab). If a `reveal` subcommand is added later, it must kill any existing viewer session for that handle first.

*(Trivial, for completeness: `f"{run}--viewer--{handle}"` is ambiguous if a run is literally named `x--viewer--@1`. Not worth defending against; noted so nobody re-derives it as a finding.)*

---

## F8 — MODERATE: the documented workaround in the probe write-up is wrong, and humans are relying on it right now

`iterm-viewer-shared-window-bug.md` §5 tells the reader:

> Each such invocation [`tmux attach -t <run>:<window>`] creates its own client cleanly targeted at that window **and is not retargeted by subsequent spawns in the same run**.

Measured — it is retargeted, because that client is still attached to the base session and therefore still shares its current-window pointer:

```
$ TMUX= tmux attach -t 't008c2:1'     # manual "workaround" client -> agentA
   t008c2|@1411|agentA
$ tmux select-window -t @1412         # a later spawn's reveal(), today's code
   t008c2|@1412|agentB                # <-- retargeted anyway
```

`--viewer none` **plus a manual attach is not a safe workaround while any `iterm-tab` reveal can still fire in that run.** The only genuinely immune workaround today is the one TICKET-008 is about to implement.

**Required correction:** fix §5 of the probe document as part of this ticket (it is the document the ticket cites as its evidence base, and the claim is actively misleading). Verified-safe replacement: attach with your own grouped session — `TMUX= tmux new-session -t '=<run>' -s "$(whoami)-manual-$$" \; select-window -t <window>`.

---

## F9 — MINOR: `destroy-unattached on` makes an accidental detach unrecoverable, and there is no way to re-open a tab

With `destroy-unattached on`, a stray `C-b d` in a viewer tab destroys that session immediately. The human's only route back is a manual `tmux new-session -t …` typed by hand (correctly — see F8), because `reveal()` is reachable only from the spawn path (`agentctl.py:1512`) and there is no `agentctl reveal`/`show` subcommand. Today, an accidental detach is recovered with `tmux attach`.

This is an acceptable trade for the leak protection, but it should be a stated consequence rather than a discovery. Consider `destroy-unattached keep-last` if the tradeoff is judged wrong (man page: *"destroy the session only if it is in a group and has other sessions in that group"*) — though `on` is the right choice for a per-tab session, so the better follow-up is a small `agentctl reveal <agent>` subcommand. Out of scope for 008; worth a line in the ticket's follow-ups.

---

## What holds up

Verified against live tmux 3.7b, so the implementer does not re-litigate these:

- **The core mechanism is real and it fixes the bug.** Two grouped sessions, two clients, two independent pointers, base session untouched:
  ```
  /dev/ttys047 session=vw--@1333 window=@1333 agentA
  /dev/ttys048 session=vw--@1334 window=@1334 agentB
  base session current window -> @1332 __root__     # never retargeted
  ```
- **`new-session -t` is the group flag, and it accepts the `=` exact-match target.** Man page: *"If `-t` is given, it specifies a session group."* `tmux new-session -d -t '=t008base' -s <name>` works, and the resulting `#{session_group}` is the base session's name. The ticket was right to flag this as needing verification and right about which flag it is; `-s` for the new name is correct.
- **tmux session names may contain `@`.** `vw--@1333` created and targeted fine, so no stripping/replacement of the handle's leading `@` is needed (contrary to step 2's hedge).
- **`set-option destroy-unattached on` chained after `new-session` scopes to the new session, not the base** (see F4 — ship it with `-t` anyway).
- **`destroy-unattached on` genuinely collects the session when the tab closes:**
  ```
  $ tmux detach-client -s 'vw--@1333'
  $ tmux list-sessions   ->  vw--@1333 gone
  ```
  This half of the cleanup story works exactly as the ticket claims. It is only the *agent-killed* path (F1) and the *run-killed* path (F2) that do not.
- **Handle uniqueness is sound.** Window ids are unique server-wide and monotonic within a server lifetime; `reveal` is called once per spawn (1512). Two concurrent reveals in one run cannot collide.
- **`capture()`'s attached-detection does not regress** — I checked this specifically, because a false "unattached" reading would make `_force_repaint` (831-857) resize a window a human is actively watching. Window→session resolution follows the attached grouped session, so the reading is unchanged:
  ```
  plain attach:  session_attached for @1390 = 1  [session=t008b5]
  grouped:       session_attached for @1390 = 1  [session=v5]
  ```
- **The `Viewer`/`Backend` boundary argument is sound**, and the ticket is right to refuse a `backend.reveal`. F2's `-g` and F3(a)'s `conceal` both respect it.
- **The escaping guidance is right.** Adding a second and third `\;` introduces no new class of the three previously-fixed bugs: `_shell_quote`'s single-quoting is unconditional, `_applescript_escape` is applied once over the whole line, and `" ; " not in command` still holds across N separators. **One thing the ticket does not say and must:** the new **session name is a third embedded value and must go through `_shell_quote` too** — it carries the run id, i.e. the same hostile input the target does. So does `set-option`'s `-t` argument (F4).

---

## Required changes before this ticket can be executed

1. **Strike step 3 entirely.** Replace with the measured behaviour: a grouped viewer session shares `__root__` and survives its agent's window; nothing auto-cleans it. [F1]
2. **Add a step changing `TmuxBackend.kill_run` to `kill-session -g -t <target>`**, and amend the "do not change `.kill_run`" constraint with the reason. Without this, `close-run` and `reap` no longer destroy a run and the ticket's last acceptance criterion cannot pass. [F2]
3. **Decide the post-`close_agent` tab behaviour explicitly** — either add `Viewer.conceal(run, handle)` called from `close_agent`, or document that the tab stays attached on `__root__` and drop the acceptance criterion that says otherwise. Do not ship the ticket's current wording, which promises cleanup that will not happen. [F3]
4. **Pass `-t <viewer-session-name>` to `set-option`**, shell-quoted, and make the new test assert the target token rather than a substring. Add `tmux show-options -t '=<run>' destroy-unattached` (must be empty) to the manual protocol. [F4]
5. **Shell-quote the derived session name** wherever it is embedded — it carries the run id. [F5/"what holds up"]
6. **Add live tmux tests**: teardown-leaves-nothing-in-the-group; select-window-does-not-cross-sessions; base session has no `destroy-unattached`; `kill_run` argv contains `-g`. String tests alone cannot see any finding in this review. [F5]
7. **Locate viewer sessions by `#{session_group}`, never by rebuilding the name** — tmux mangles backslashes and re-parses `:` in names. [F6]
8. **Fix §5 of `work_organisation/probe/iterm-viewer-shared-window-bug.md`** — the manual-attach workaround it recommends is not immune, and people are using it today. [F8]
9. **File separately (do not fold in):** run ids containing a backslash are already broken at the `TmuxBackend` layer, and the hostile-run-id test certifies a run that tmux cannot host. [F6]

---

The diagnosis in this ticket is excellent — the root cause is correct, the mechanism chosen is the right one, and the author was right to flag `new-session -t`'s flag semantics as needing verification rather than assuming the write-up's sketch. The failure is one of scope: the ticket verified the half of the lifecycle that tmux does give you for free (`destroy-unattached` on detach) and asserted the other half by analogy. Grouped sessions change what "the run's session" *means*, and `kill_run` — the one function the ticket forbids touching — is written against the old meaning.

---

## Appendix: verification environment

- `tmux 3.7b`, `/opt/homebrew/bin/tmux`, macOS (Darwin 24.6.0) — the version `TmuxBackend`'s docstring claims verification against.
- All findings reproduced with live sessions and **real attached clients** (driver session + `send-keys`), not dry command construction. Scratch sessions `t008b2`–`t008c2`, `t008drv`, `v4a`, `v5`, `vw--*`, `a\b`, `a.b`, `a:b`, `My "Run"\Two*` were all created and destroyed during this review; `tmux list-sessions` was left as found. No file under review was modified — `TICKET-008-*.md` (other than this review) and `agentctl.py` are untouched.
