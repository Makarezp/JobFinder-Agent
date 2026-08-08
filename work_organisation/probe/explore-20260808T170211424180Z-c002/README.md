---
status: open
brief: explore
claim: C002
rate: n/a
control_rate: n/a
commit: e8ec234
journal_entry: explore-20260808T170211424180Z
triage: manual (no automated oracle path -- oracle wiring in probe/lib/oracle.py only accepts T4 brief findings, not `explore` findings)
---

# Specification: Probe finding explore-20260808T170211424180Z

## 1. Overview

* **Summary:** A spawn whose readiness cannot be proven (Claude's `SessionStart`
  hook never fires within `--spawn-timeout`) does kill its own tmux window, but
  does **not** clean up the agent's on-disk footprint. `meta.json` and
  `settings.json` are written before the readiness proof is attempted, so by
  the time `spawn_agent`'s except-block runs, the agent directory always has
  files other than the bootstrap inbox message in it. The
  `if not other_files: ... unlink/rmdir` branch at `agentctl.py` (~1580-1590)
  is therefore effectively unreachable on the default Claude spawn path, and
  the claim at `SKILL.md:103-104` ("a spawn that cannot be proven kills its
  own window and cleans up") only half-holds: window kill, yes; disk cleanup,
  no.
* **Context:** This is an `explore`-track finding, not a `run`/brief finding,
  so it was never routed through the T7 oracle (`probe/lib/oracle.py`
  `triage_finding` requires a brief envelope with `rate`/`control_rate`/
  `artifacts` fields that only a T4 brief produces). This spec was written
  by hand by the probe operator following the same template `emit_spec`
  uses, and carries no oracle verdict. A human (or a manually invoked oracle
  role) should confirm the disposition below.
* **Target:** ambiguous between `.agent/skills/agent-tabs/agentctl.py` (if the
  intent was truly zero footprint on an unprovable spawn) and
  `.agent/skills/agent-tabs/SKILL.md:103-104` (if the intent was always "kill
  the window; leave a `reap`-able record", in which case the claim's wording
  overstates the guarantee). See §2 for the two readings.
* **Evidence:** reproduced twice conceptually (see steps below); one full run
  preserved. Fake worker binary at `evidence/fake_claude.sh` starts a real
  tmux window and sleeps, never invoking any Claude hook. Spawned via:
  `agentctl.py spawn worker --role probe/roles/probe-worker.md --task "test task" --binary evidence/fake_claude.sh --provider claude --spawn-timeout 3 --viewer none`
  against a fresh runtime/run. Command exited 1 with
  `SpawnError: agent 'worker' never reported SessionStart within 3s`.
  `tmux list-windows -a` afterward showed only the run's `__root__` window
  (the `worker` window was killed -- confirms half the claim).
  `find agents/worker` afterward showed `meta.json`, `settings.json`,
  `outbox/` (empty dir), and `inbox/0001.md` all still present (contradicts
  the "cleans up" half). `bus.jsonl` recorded one `error` event with
  `data.bootstrap` set to the inbox path, which is exactly the
  `bootstrap_error_path` set when `spawn_agent`'s except-block finds
  `other_files` non-empty and skips its unlink/rmdir cleanup.
* **Preserved artifacts:**
  * `evidence/runtime/probe-c002/` (fixture run: bus.jsonl + agents/worker/{meta.json,settings.json,inbox/0001.md,outbox/})
  * `evidence/fake_claude.sh` (the fake worker binary used to trigger the unprovable-spawn path)

## 2. Functional Requirements

* [ ] Decide the intended contract for an unprovable spawn once `meta.json`
      has already been written: either (a) `agentctl.py` should also remove
      `meta.json`/`settings.json`/`inbox/*`/`outbox/` (and the agent
      directory) in this case, extending the `other_files` check to exclude
      framework-written files it knows are safe to discard, or (b)
      `SKILL.md:103-104` should be reworded to state precisely what "cleans
      up" covers (window only; the on-disk record intentionally survives for
      `reap`), so the claim matches `list_agent_names`'s own documented
      framing ("Directories without a meta.json are spawns that died before
      recording anything; they are skipped here and left for reap").
* [ ] If (a): update the except-block in `spawn_agent` (`agentctl.py`
      ~1565-1591) so that a spawn failure before the readiness proof also
      removes `meta.json` and `settings.json`, not just the bootstrap inbox
      file, before checking whether the directory is empty.
* [ ] If (b): reword `SKILL.md:103-104` and add/adjust a claim in
      `claims.jsonl` so C002 accurately reflects "kills its own window; a
      `reap`-able on-disk record remains" rather than unconditional cleanup.

## 3. Verification & Acceptance Criteria

* [ ] Reproduce from `evidence/fake_claude.sh` against a fresh runtime/run:
      `agentctl.py spawn worker --role probe/roles/probe-worker.md --task "test task" --binary evidence/fake_claude.sh --provider claude --spawn-timeout 3 --viewer none`,
      confirm exit 1 and that `agents/worker/meta.json` still exists afterward.
* [ ] After whichever fix is chosen, re-run the same reproduction and confirm
      either: (a) `agents/worker/` no longer exists, or (b) `SKILL.md` no
      longer promises unconditional cleanup for this path.
* [ ] Regenerate coverage (`probe.py coverage --write`) once resolved so C002
      evidence is not silently treated as current against the new source.
