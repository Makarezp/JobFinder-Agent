---
status: open
brief: explore
claim: C014
rate: n/a
control_rate: n/a
commit: e8ec234
journal_entry: explore-20260808T172101019039Z
triage: manual (no automated oracle path -- oracle wiring in probe/lib/oracle.py only accepts T4 brief findings, not `explore` findings)
---

# Specification: Probe finding explore-20260808T172101019039Z

## 1. Overview

* **Summary:** A real Haiku worker, given two unread inbox messages in the
  same turn -- one delivered normally (with a doorbell keystroke) and one
  written directly to its inbox with the doorbell deliberately skipped
  (simulating a lost/garbled notification) -- replied with only the
  doorbelled message's token. It never reported the lost-doorbell message's
  token anywhere, contradicting both the probe-worker role's explicit
  instruction ("list on their own line the TOK-XXXX token from every inbox
  file you consumed this turn") and the resilience guarantee `C014` and
  `WORKER.md` describe: a lost keystroke should cost nothing because the
  instruction is still in the inbox, discoverable by re-reading at the start
  of every turn.
* **Context:** `C014` is currently marked **covered / no-finding** in
  `COVERAGE.md`, based on brief `B002`'s last logged single-trial run
  (`rate: 1.0`). This is a *different* real trial of the identical scenario
  `B002` automates (send A, silently write B without a doorbell, send C),
  run via a standalone script (not `probe.py run`) so the SUT could be
  preserved unconditionally for multi-claim inspection regardless of
  pass/fail. It happened to also expose the underlying flakiness that a
  single `--trials 1` run can miss. This finding was never routed through
  the T7 oracle (`explore` findings have no automated oracle path -- see the
  equivalent caveat on the `C002` spec in this same directory), so this spec
  is hand-authored, following the oracle's own template, and carries no
  oracle verdict.
* **Target:** ambiguous between the **worker's actual behavior** (an
  haiku-model instruction-following gap under `.agent/skills/agent-tabs/probe/roles/probe-worker.md`
  and `.agent/skills/agent-tabs/WORKER.md`, which may or may not generalize
  beyond the probe-worker role's wording) and the **measurement
  methodology** (a single `--trials 1` run of `B002` is not enough to trust
  a `1.0` rate as durable; `B002`'s own default is 10 trials, and this gap
  might already show up at that sample size). Neither `agentctl.py` (the
  mechanical inbox/bus plumbing worked exactly as documented: the message
  really was written without a `message_sent` event, and it really was
  still sitting in the inbox for the worker to find) nor `SKILL.md`/`WORKER.md`
  text appear to be at fault here -- this looks like real worker behavior
  under-delivering on the protocol's guarantee, which is a harder thing to
  "fix" than a code bug.
* **Evidence:** one real-haiku trial, preserved in full. Sequence: bootstrap
  (reply `HANDSHAKE_READY`, matching Initial assignment) -> send A, token
  `TOK-7CWQ` (delivered with doorbell) -> reply `TOK-7CWQ` -> write B, token
  `TOK-5WRF`, directly to `inbox/0003.md` via the runner's
  `write_lost_doorbell` helper (no doorbell, no `message_sent` bus event) ->
  send C, token `TOK-GNB9` (delivered with doorbell, landed in `inbox/0004.md`
  since `0003` was already taken) -> single reply, `outbox/0003.md`,
  contains exactly `TOK-GNB9`. `TOK-5WRF` does not appear in any outbox file
  in the preserved run. `bus.jsonl` shows the final turn completed normally
  (`turn_start` seq 11 -> `reply` seq 12) before the harness force-closed the
  SUT (seq 13) -- i.e. this is not a truncated-turn artifact like the prior
  `B001`/`B003` `harness`-verdict findings; the worker had a complete turn
  and simply didn't report the earlier message.
* **Preserved artifacts:**
  * `evidence/run/` (full preserved SUT: `bus.jsonl`, `commands.jsonl` cmdlog, `agents/worker/{meta.json,settings.json,inbox/*,outbox/*}`)

## 2. Functional Requirements

* [ ] Re-run `B002` at its default `--trials 10` (not `--trials 1`) to
      establish whether this is a rare miss or a frequent one; a `rate` well
      below `1.0` at 10 trials would confirm this is not a one-off fluke.
* [ ] If the miss reproduces at meaningful frequency, decide whether it's
      addressable at the protocol level (e.g. `WORKER.md` or the
      probe-worker role wording could be more forceful about sweeping *all*
      unread inbox files lowest-number-first before replying) or is an
      inherent haiku-model reliability limit worth documenting rather than
      "fixing".
* [ ] If protocol wording is judged the lever, reword the relevant
      `WORKER.md` section and/or `probe/roles/probe-worker.md` to make the
      lowest-number-first sweep and per-file reporting requirement more
      explicit/harder to skip, then re-measure.

## 3. Verification & Acceptance Criteria

* [ ] Reproduce via `probe.py run B002 --trials 10` and inspect the
      resulting `rate` in `ledger.jsonl`; a rate meaningfully below `1.0`
      confirms this finding at scale rather than as an isolated miss.
* [ ] After whichever mitigation is chosen, re-run and confirm the rate
      recovers to at or near `1.0` across 10 trials, not just 1.
* [ ] Regenerate coverage (`probe.py coverage --write`) once resolved so
      `C014` evidence is not silently treated as settled against a rate
      measured from a single trial.
