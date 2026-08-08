# Agent-Tabs — Deterministic Puppet Fault States (T2)

**Sprint:** `sprint_v3_agent_tabs_hardening.md`
**Status:** **DONE — HUMAN-SIGNED-OFF (2026-08-08)**

## Delivered

- `probe/puppet.py` implements exactly four terminal fault states: `busy`, `deaf`, `dirty-composer`, and `hard-kill`.
- Every state emits `spawned` first. `busy` emits a bounded turn; `deaf` never consumes stdin; `dirty-composer` holds plain text after the `❯` composer marker; `hard-kill` waits three seconds then sends itself `SIGKILL` without emitting exit.
- `probe/lib/sut.py` creates a state-encoded, absolute, quoted, executable `pupp-*` wrapper per probe. `spawn_puppet` uses the isolated SUT environment, explicit `bypassPermissions`, Haiku, `--viewer none`, and mandatory `--no-doorbell`.
- Wrapper-name validation prevents accidental Claude, Codex, or AGY provider inference before attempting spawn.
- The T2 Step 0 live-spike findings are preserved in the SUT module docstring: bootstrap lifecycle requirements, the absent caller argv/environment channel, and the observed Claude-shaped wrapper argv.

## Critical implementation detail

`agentctl` scans the final eight terminal lines for Claude's composer. The puppet must therefore place its synthetic `❯` line at the pane bottom; top-row terminal text fails open and incorrectly permits delivery. The dirty-composer state is a fault injector, not a fake worker: it reads no inbox and sends no reply.

## Acceptance evidence

- `tests/test_probe_puppet.py` covers live tmux liveness for `busy`, `deaf`, and `dirty-composer`; hard-kill spawn/reconciliation; busy queueing with a non-empty screen control; dirty-composer force override; provider-name rejection; and four-state CLI bounds.
- Focused gate: **8 passed**.
- Full required gate: ruff, formatting, mypy strict, and **226 passed, 3 opt-in E2E checks skipped**.
- A separate live isolated busy-puppet smoke run observed `spawned` plus a non-empty direct screen capture, then force-tore-down and removed its SUT.
