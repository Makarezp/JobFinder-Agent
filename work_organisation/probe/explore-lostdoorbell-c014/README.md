---
status: inconclusive -- turn_end never fired for the losing turn; harness teardown race is the leading explanation, not a confirmed drop. Superseded pending a turn_end-aware B002 re-measurement (see TICKET-007).
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
* **Target:** ambiguous between three candidate causes, in descending order
  of current likelihood: (1) **harness teardown racing the worker's
  turn** -- `turn_end` never fired for this turn (no `Stop` hook event in
  `bus.jsonl`), and the SUT was killed 0.822s after the `reply`, faster than
  the 1.7-3.7s post-reply windows observed in the same transcript's two
  completed turns; the worker may have been about to sweep its inbox and
  reply a second time when it was killed. This is currently the most likely
  explanation and is structurally identical to the `B001`/`B003`
  `harness`-verdict findings this spec originally (and incorrectly) claimed
  not to resemble. (2) the **worker's actual behavior** (a haiku-model
  instruction-following gap under `.agent/skills/agent-tabs/probe/roles/probe-worker.md`
  and `.agent/skills/agent-tabs/WORKER.md`), if a `turn_end`-aware
  re-measurement still shows the miss. (3) the **measurement methodology**
  (a single `--trials 1` run of `B002` is not enough to trust a `1.0` rate
  as durable). Note that `agentctl.py`'s mechanical inbox/bus plumbing
  behaved exactly as documented regardless of which of the three holds:
  `write_lost_doorbell` (`runner.py:89-100`) uses exclusive `"x"` creation
  plus `fsync`, emits no `message_sent` event, and B's token genuinely
  appears in no outbox file -- only the *interpretation* of that absence
  (as a confirmed drop rather than an inconclusive kill) was wrong.
* **Evidence:** one real-haiku trial, preserved in full. Sequence: bootstrap
  (reply `HANDSHAKE_READY`, matching Initial assignment) -> send A, token
  `TOK-7CWQ` (delivered with doorbell) -> reply `TOK-7CWQ` -> write B, token
  `TOK-5WRF`, directly to `inbox/0003.md` via the runner's
  `write_lost_doorbell` helper (no doorbell, no `message_sent` bus event) ->
  send C, token `TOK-GNB9` (delivered with doorbell, landed in `inbox/0004.md`
  since `0003` was already taken) -> single reply, `outbox/0003.md`,
  contains exactly `TOK-GNB9`. `TOK-5WRF` does not appear in any outbox file
  in the preserved run. **The trial is inconclusive, not a confirmed drop:**
  a turn is marked complete by `turn_end` (the `Stop` hook), not by `reply`
  (a `PostToolUse` side effect of `agentctl reply`). Walking `bus.jsonl`,
  turns 1 and 2 both show a `reply` followed by `turn_end` 1.7-3.7s later;
  turn 3 shows `turn_start` (seq 11) -> `reply` (seq 12) -> **no `turn_end`
  ever fires** -- the harness force-killed the SUT (seq 13, `exit`/`forced`)
  0.822s after the reply, shorter than either of the two post-reply windows
  actually observed in this same transcript. The worker may well have gone
  on to read `inbox/0003.md`'s counterpart bookkeeping and reply a second
  time; it was killed inside the window where that would have happened.
  This is indistinguishable from the `B001`/`B003` `harness`-verdict
  findings this spec previously distanced itself from.
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
