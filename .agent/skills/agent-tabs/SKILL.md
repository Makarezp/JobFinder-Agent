---
name: Agent Tabs
description: Launch, message, observe and tear down agent sessions that run in visible terminal windows, so a human can watch and talk to them directly. Use when an orchestrator needs collaborators the human can see, rather than opaque background tasks.
---

# Agent Tabs

A background task the human cannot see is a task the human cannot correct. This
framework puts each agent in its own terminal window: the orchestrator drives it
over a filesystem bus, and the human watches the same window and can type into
it at any time. Both are first-class participants.

`agentctl` is a single stdlib-only Python file. It has no dependencies, needs no
virtualenv, and runs in any git repository.

---

## Mental model

```
tmux session  =  one run        (a batch of collaborating agents)
tmux window   =  one agent      (addressed by window id: @3)
bus.jsonl     =  what happened  (append-only, the source of truth)
inbox/        =  work sent TO an agent
outbox/       =  reports sent BACK by an agent
```

> **Terminology warning.** A *tmux session* is not a *Claude session*. One tmux
> session holds many windows; each window runs one agent process with its own
> conversation. "Session" in this document always means the tmux one.

Three authorities, and they are not interchangeable:

| Question | Authority |
|---|---|
| Which agents exist? | the runtime tree on disk |
| Which are alive? | the terminal backend |
| What does that mean? | the event log |

Agent state is a **pure function of the event log**. `state.json` is a cache; any
read path that cannot fall back to replaying `bus.jsonl` is a bug.

### States

| State | Meaning |
|---|---|
| `idle` | ready for work |
| `busy` | mid-turn |
| `awaiting_human` | asked a question or reported blocked — **stop and tell the human** |
| `dead` | exited, errored, or its window vanished |

---

## Prerequisites

```bash
brew install tmux      # or your platform's equivalent
tmux -V                # 3.0+
```

Windows are created detached, so nothing appears until you attach:

```bash
tmux attach -t <run>     # attach
Ctrl-b <n>               # switch to window n
Ctrl-b d                 # detach (agents keep running)
```

Two mutually exclusive ways to watch a run, both iTerm2-specific:

- `tmux -CC attach -t <run>` renders every window in the run as a **native
  iTerm tab**, switchable with `Cmd-1` / `Cmd-2` — the whole-session view.
- `agentctl spawn ...` opens one new iTerm tab by default, already attached to
  that one agent's window, the moment `spawn` creates it — the per-agent,
  hands-off view. Use `--viewer none` (or `AGENT_TABS_VIEWER=none`) for a
  headless run.

**Do not mix them within one run.** A plain attach and a control-mode attach
to the same tmux session in the same iTerm window is a real footgun, not a
cosmetic one — pick one style per run.

---

## The verbs

Every command takes `--run <id>`, or reads `$AGENT_TABS_RUN`.

### `spawn` — bring an agent up, and prove what its provider can prove

```bash
agentctl spawn reviewer --role path/to/ROLE.md --run demo [--model sonnet]
agentctl spawn reviewer --provider codex --role path/to/ROLE.md --run demo \
  --sandbox workspace-write --ask-for-approval never \
  --task "Review the current diff for regressions"
agentctl spawn reviewer --role .agent/skills/agent-tabs/examples/reviewer-role.md \
  --task-file brief.md --run demo
```

Claude blocks until its `SessionStart` hook fires and its first turn begins.
Codex has no compatible hook surface, so Agent Tabs proves its tmux window is
alive, records a synthetic `spawned` event, and delivers the durable bootstrap
inbox message; its reply/question/blocked reports are the observable lifecycle.
There is no sleep-and-hope: an unprovable spawn always kills its window and
deletes its undelivered bootstrap; the meta.json/settings.json record stays.

Useful flags: `--worktree` (own git checkout, for agents editing in parallel),
`--permission-mode`, `--isolated-settings`, `--cwd`, `--no-doorbell`. Codex is
explicit (`--provider codex`) and uses `--sandbox` plus `--ask-for-approval`;
it starts the interactive TUI, never `codex exec`. The role defines standing
behavior, the bootstrap's Initial assignment is the first concrete request, and
`agentctl send` delivers subsequent requests.

### `send` — deliver an instruction

```bash
agentctl send reviewer "Review the diff on HEAD and report findings" --run demo
agentctl send reviewer --file brief.md --run demo
```

The payload is written to the agent's inbox **first**, then a single-line pointer
is typed into its window. The keystroke is a doorbell, never the message — so a
lost or mangled keystroke costs nothing, because the worker re-reads its inbox
at the start of every turn.

Three gates must pass before typing: the agent is not `busy` or `dead`, its pane
is not in copy-mode (the human is scrolled back reading it), and the composer
has no half-typed human text. Not ready means the message stays queued in the
inbox — `--queue` to return immediately (exit 3), `--force` to override.

### `wait` — block until something happens

```bash
agentctl wait --until 'agent=reviewer,type=reply|question|blocked' --run demo
```

Exit `0` with the event as JSON, `2` on timeout, `1` on a bad predicate. The
grammar is deliberately tiny: comma-separated `key=value` ANDed, keys `agent` and
`type`, `|` for alternation. A workflow needing more calls `wait` twice.

> **Run `wait` under background Bash. Never poll it in a loop.** It exits the
> moment its event lands and the harness re-invokes you.

`--from-seq` defaults to the live end of the log, so historical events cannot
cause an instant false match.

### `read` — see what came back

```bash
agentctl read reviewer --outbox --run demo      # structured replies (reliable)
agentctl read reviewer --screen 40 --run demo   # raw window (observation only)
```

`--outbox` is the machine channel. `--screen` exists so you can see what the
*human* typed into that window and stay coherent with them — **never parse
replies out of it.**

### `list` / `status` — what is running

```bash
agentctl list --run demo
agentctl status reviewer --run demo
```

Both reconcile against the terminal first: an agent whose window vanished with
no exit hook is recorded as dead exactly once, however often you look.

`status` also flags an agent that has been mid-turn with no `turn_end` for over
five minutes. That is what a worker deadlocked on an unanswered permission
prompt looks like — and it is indistinguishable from hard thinking, so it is a
hint to go look at that window, never a verdict.

### `close` / `reap` / `close-run` — teardown

```bash
agentctl close reviewer --run demo          # /exit, then kill; removes its worktree
agentctl reap --run demo                    # report orphans, change nothing
agentctl reap --all --run demo              # act, and kill the session once empty
agentctl close-run --run demo               # tear the whole run down
```

`reap` is read-only by default; `--apply` acts. The graceful `/exit` in `close`
is best-effort — **the timeout is the real guarantee** — because the text is
typed literally and only lands correctly when the composer is focused and empty.
Do not "fix" this by lengthening the timeout.

### `seq` — a watermark

```bash
WM=$(agentctl seq --run demo)
```

Capture before sending, then `wait --from-seq $WM`, so a fast reply arriving
between the two cannot be missed.

---

## The canonical round trip

```bash
RUN=demo

WM=$(agentctl seq --run $RUN)
agentctl spawn reviewer --role path/to/ROLE.md --run $RUN
agentctl send reviewer --file brief.md --run $RUN

# background — exits the moment the agent reports
agentctl wait --until 'agent=reviewer,type=reply|question|blocked' \
              --from-seq $WM --run $RUN

agentctl read reviewer --outbox --run $RUN
agentctl close reviewer --run $RUN
```

---

## Rules for the orchestrator

1. **`awaiting_human` means stop.** The agent asked *the human* a question. Say
   which window to look at. Do not answer on the human's behalf — the entire
   point of visible windows is that the human is reachable.
2. **`wait` runs in the background.** Polling in a loop burns tokens to learn
   what an exit code already tells you.
3. **The outbox is the only machine-readable channel.** Screens are for
   observation.
4. **Never assume a message was read because it was sent.** Events say what
   happened; keystrokes do not.
5. **Tear runs down.** A detached session outlives your terminal, and an agent
   left in one costs tokens where nobody is looking.

---

## Settings layering

`--settings` is **additive**. A spawned worker also loads user-level settings and
any `.claude/settings*.json` in its working directory, so hooks defined there
fire inside every worker too.

- **Default: inherit.** The human's own configuration keeps working.
- **`--isolated-settings`:** restrict the worker to the generated file only.

## The runtime root

Defaults to `~/.local/state/agent-tabs/<repo>-<hash>/`, **outside the
repository** — deliberately, for two reasons. A high-churn append-only log plus
git worktrees inside a cloud-synced tree is a corruption hazard, and keeping a
tree full of absolute paths out of version control should be true by
construction rather than by discipline.

The tree is **disposable, not portable**: it bakes absolute paths. Delete it and
you lose transcript bookkeeping, nothing else.

Override with `--runtime <abs>` or `$AGENT_TABS_RUNTIME`. Inspect with
`agentctl paths --run <id>`. Workers receive it explicitly and must never
re-derive it.

## Worker identity

Workers learn who they are from the environment (`AGENT_TABS_RUNTIME`, `_RUN`,
`_AGENT`), injected at window creation. Nothing requires an agent to type its
own identity — an agent asked to do that will eventually get it wrong.

---

## Open question

**Where the orchestrator itself runs.** Today it is *outside* tmux, which is what
is built and proven. Moving it to window 0 would make runs survive closing the
terminal and make the protocol symmetric, but `close-run` would then kill the
window it is running in. That guard is deliberately not half-implemented; decide
before relying on it.
