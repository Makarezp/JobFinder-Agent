---
status: open
component: agent-tabs / agentctl.py / TmuxBackend.open (spawn_agent's window creation)
discovered: 2026-08-08
discovered_via: live usage — spawning a second agent into an already-populated run failed
severity: high — spawn can fail outright for reasons unrelated to the requested agent, blocking orchestration
root_cause: not fully established — see Section 4, "what remains unexplained"
---

# TmuxBackend.open: `new-window` without an explicit index can repeatedly collide instead of finding a free slot

## 1. Summary

`spawn_agent` creates each agent's tmux window via `TmuxBackend.open()` (`agentctl.py:781-791`):

```python
args = ["new-window", "-P", "-F", "#{window_id}", "-d", "-t", self._target(run), "-n", name, "-c", cwd]
```

No window index is ever passed — the code relies entirely on tmux to pick one. In one run (`ticket-itermbug`, a fresh session with only the root placeholder window and one agent window already present), spawning a **second** agent failed outright:

```
agentctl: tmux new-window -P -F #{window_id} -d -t =ticket-itermbug -n review-008 ... failed: create window failed: index 1 in use
```

Window index 1 was indeed already occupied by the first agent. The failure itself is tmux behaving as documented — but the *complete absence of any fallback* (retry at the next index, or explicit index computation) means `spawn_agent` has a live path to fail on a perfectly ordinary "spawn a second agent into an existing run" call, for reasons that have nothing to do with that agent's own setup.

## 2. Reproduction

1. Fresh run, `--viewer none` for every spawn in it (no iTerm attach ever happens — this detail turned out to matter, see Section 4).
2. Spawn agent A into the run. Succeeds; ends up at window index 1 (window 0 is the `__root__` placeholder every run starts with).
3. Spawn agent B into the same run. Fails: `create window failed: index 1 in use`.
4. Confirmed independently of `agentctl.py` — running the equivalent raw command reproduces it:
   ```
   tmux new-window -P -F "#{window_id}" -d -t '=<run>' -n probe-test -c /tmp
   ```
   fails identically, while an explicit index succeeds immediately:
   ```
   tmux new-window -P -F "#{window_id}" -d -t '=<run>:2' -n probe-test -c /tmp
   ```

## 3. Why two other runs didn't hit this

Two other runs spawned earlier in the same session (`ticket-review`, two agents; `ticket-impl`, two agents) did **not** hit this — both successfully placed their second agent at window index 2. The one difference: both of those runs used `--viewer iterm-tab` (the default) for every spawn, not `--viewer none`. The iTerm viewer's `reveal()` step runs `tmux attach -t <run> \; select-window -t <handle>` in a new client immediately after each successful spawn — which attaches a real client to the session and changes its current-window. It's plausible that having a live attached client changes how tmux computes the next window index for a subsequent `new-window` call with no explicit index — but this is an inference from the pattern, not confirmed against tmux's source or documentation.

## 4. What remains unexplained

This write-up does **not** have a confirmed root cause, and that should be resolved before a fix is implemented, not guessed at:

- The natural hypothesis — "tmux inserts the new window at (current-window-index + 1) and doesn't search further on collision" — was tested directly: I manually ran `tmux select-window -t <run>:1`, confirmed via `list-windows` that window 1 was now the session's active window, and retried the plain `new-window` call. **It still failed with the identical "index 1 in use" error**, which contradicts the "active + 1" theory as stated (if that were the mechanism, moving active to 1 should have made the next attempt target 2).
- Whether an *attached client* (vs. just the session's current-window pointer) is the real variable was not directly tested — doing so would require attaching a real client without an interactive terminal (e.g. via `tmux -C` control mode in the background) and re-running the collision, which wasn't attempted here.
- Whether this is a tmux 3.7b-specific bug/quirk, a documented-but-nonobvious interaction with `renumber-windows off` (confirmed off, both globally and at session level) and `base-index 0` (confirmed), or something else entirely, is open.

## 5. Practical impact

Any orchestration flow that spawns multiple agents into one run using `--viewer none` (headless, no iTerm tab — the mode used for most of this session's sonnet worker spawns) is at risk of the *second* spawn failing outright, independent of anything about the agent being spawned. The workaround used live in this session was simply to spawn into a fresh run instead of a populated one — which works, but fragments what should be one logical group of agents across multiple runs, and isn't a fix.

## 6. Suggested fix directions (not decided — for human review)

Two independent options, not mutually exclusive:

1. **Compute the index explicitly in `TmuxBackend.open()`** rather than delegating to tmux's default placement: query `list-windows -t <run> -F "#{window_index}"`, compute the lowest free integer, and pass it explicitly as part of `-t <run>:<index>`. This removes the dependency on whatever implicit placement rule tmux is applying, and makes window placement a property this codebase owns and can reason about/test directly.
2. **Retry-on-collision**: catch the specific `"index N in use"` failure and retry the `new-window` call at increasing indices until one succeeds (bounded, to avoid an infinite loop on some unrelated failure mode). Cheaper to implement than option 1, but treats the symptom rather than the mechanism, and would silently mask the fact that the underlying placement logic is not fully understood.

Option 1 is likely the more durable fix since it doesn't depend on correctly guessing tmux's undocumented-here placement behavior at all. Either way, Section 4's open question should be resolved (or at least the attached-client hypothesis tested) before implementation, since it may reveal a simpler true cause than either option above assumes.

## 7. Constraints for whoever picks this up

- No changes have been made to `agentctl.py`. This document is purely descriptive.
- Any fix must not assume `--viewer iterm-tab` is in use — headless (`--viewer none`) spawning is a first-class, frequently used path in this project's own orchestration workflow and must work standalone, without relying on a viewer's side effects to avoid this bug.
- `close_agent`/`close_run`/`reap` were not investigated as part of this write-up; if option 1's explicit-index approach is chosen, confirm it doesn't need to account for indices freed by those paths (e.g. does a killed window's index become reusable, and does that matter for the "lowest free integer" computation).
