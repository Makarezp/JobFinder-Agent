---
status: open
component: agent-tabs / probe harness (runner.py _wait_for_bootstrap) / real-Haiku worker bootstrap turn
discovered: 2026-08-10
discovered_via: TICKET-007 measurement (probe.py run B002) -- 6 consecutive full-run attempts, 4 of which aborted on this exact symptom; confirmed and characterized with a dedicated bootstrap-only exploratory probe
severity: high -- makes any real-Haiku probe brief with expect_rate 1.0 across a run of 10+ sequential SUTs fragile to a flake unrelated to what the brief is actually measuring
root_cause: not established -- reproduced and characterized, candidate hypotheses only (Section 5)
---

# A real Haiku worker's bootstrap turn sometimes ends without ever calling `agentctl reply`

## 1. Summary

Every probe brief run (`agentctl.py`'s `spawn` -> `runner.py`'s `_spawn_worker`/`_wait_for_bootstrap`) starts the same way: spawn a worker, give it a bootstrap task ("Open your inbox, then reply exactly HANDSHAKE_READY via agentctl reply and wait."), and wait up to 120s (`READY_TIMEOUT`) for a `type=reply` bus event before doing anything brief-specific.

At a rate of roughly **1 in 4** in a dedicated isolated test (2/8, Section 4) and observed in **4 of 6** full `probe.py run B002` attempts (Section 3), the worker's bootstrap turn **starts normally** (`turn_start` fires, proving the doorbell keystroke landed and the model began a turn) and even **ends normally** in most of the observed cases (`turn_end`/the `Stop` hook fires, meaning the model genuinely finished generating and stopped) -- but the model **never called `agentctl reply`** during that turn. The outbox stays empty. Nothing in the harness detects this as an error until the outer 120s timeout expires and the SUT is force-killed.

This is not the harness swallowing a reply that was actually sent -- outbox directories were empty in every case checked, and `bus.jsonl` has no `reply` event at all between `turn_start` and `turn_end`/`exit`.

## 2. Why this matters beyond TICKET-007

This gap sits upstream of every single probe brief -- `B001`, `B002`, `B002-control`, `B003`, all of them spawn a worker with this exact bootstrap task before any brief-specific content is sent. A brief with `expect_rate: 1.0` run across `trials: 10` sequential SUTs (20 for `run_brief`'s control+target pair) has, at a naive independent-trials estimate from the ~25% single-trial rate observed here, a non-trivial chance of hitting this at least once per full run -- consistent with what was actually observed (4/6 full-run attempts aborted, all but one of those specifically on this symptom). Any future measurement using this harness inherits this fragility until it's fixed, not just `B002`.

## 3. Evidence from TICKET-007's `probe.py run B002` attempts

Of 6 consecutive attempts (see `work_organisation/tickets/TICKET-007-handoff.md` Section 3 for the full list and log paths), 4 aborted with exactly this symptom -- `turn_start` (and in 2 of 4, also `turn_end`) with zero `reply` events, followed by a forced exit once `_wait_for_bootstrap`'s 120s timeout expired:

| attempt | trial | bus.jsonl sequence | outcome |
|---|---|---|---|
| 2 | control trial 4 | `spawned` -> `message_sent` -> `turn_start` -> *(nothing for 120s)* -> `exit forced` | no `turn_end`, no `reply` |
| 3 | control trial 1 | `spawned` -> `message_sent` -> *(90s later)* `message_sent` (2nd doorbell attempt) -> `turn_start` -> `turn_end` (~13s later) -> *(108s later)* `exit forced` | `turn_end` fired, no `reply` |
| 4 | control trial 2 | `spawned` -> `message_sent` -> `turn_start` -> *(nothing for 120s)* -> `exit forced` | no `turn_end`, no `reply` |
| 5 | control trial 2 | identical to attempt 4 | no `turn_end`, no `reply` |
| 6 | target trial 5 (control had passed 10/10 for the first time) | `spawned` -> `message_sent` -> `turn_start` -> `turn_end` (~14s later) -> *(106s later)* `exit forced` | `turn_end` fired, no `reply` |

(Attempt 1's single flake -- control trial 7's *third* message reply missing its 10s `wait_timeout` -- is a different symptom, mid-scenario rather than bootstrap, and is not counted above.)

Attempt 3 additionally shows `agentctl.py`'s own `_bootstrap` retry logic (`agentctl.py:1586-1602`) firing: it re-rings the doorbell after its own 90s `bootstrap_timeout` if `turn_start` hasn't appeared yet. Note that `_bootstrap` only waits for `turn_start` as proof the doorbell "landed" -- **it does not wait for or care about `reply`**. So a worker whose doorbell keystroke registered but which then never calls `reply` looks identical to `_bootstrap` as full success; the actual reply-timeout enforcement happens one layer up, in `runner.py`'s `_wait_for_bootstrap` (120s), which is what actually times out and forces the kill in all cases above.

## 4. Reproduction: isolated bootstrap-only exploratory probe

To characterize this cheaply (without spawning full 20-SUT `B002` runs), a standalone script mirroring `runner._spawn_worker`/`_wait_for_bootstrap` exactly -- same role (`probe/roles/probe-worker.md`), same model (`haiku`), same bootstrap task text, same 120s timeout -- but sending **no B002 content at all** (no A/B/C messages) was run for 8 sequential repeats:

```
1: replied, spawn 1.75s, wait 20.37s
2: replied, spawn 2.00s, wait 14.05s
3: replied, spawn 4.04s, wait 20.60s
4: replied, spawn 3.15s, wait 42.18s
5: replied, spawn 2.92s, wait 11.77s
6: replied, spawn 2.97s, wait 32.31s
7: NO REPLY, spawn 1.72s, wait timed out at 120.24s
8: NO REPLY, spawn 1.93s, wait timed out at 120.24s

SUMMARY: 6/8 replied
```

**6/8 (75%) replied; 2/8 (25%) hit exactly the same symptom.** Both failures (`bus.jsonl`, preserved artifacts) show `turn_start` -> `turn_end` (11-20s later) -> forced exit ~110s after that, with zero `reply` events -- an exact match for attempts 3 and 6 above. This confirms the gap is real, reproducible in isolation (no B002-specific content required), and roughly consistent in rate with what the full runs showed.

Notably, the two failures were the *last two* of 8 sequential repeats (indices 7 and 8), which is circumstantial and not statistically meaningful at n=8, but worth flagging as a candidate pattern (see Section 5) rather than dismissing.

Script and raw preserved artifacts are not part of this repo (scratch/temp-dir based); the artifact temp dirs are noted in this doc's discovery session and are ephemeral (`/private/var/folders/.../T/agent-tabs probe@...`) -- pull them promptly if deeper inspection is needed later.

## 5. Candidate hypotheses (none confirmed)

- **Genuine Haiku instruction-following gap on a bare single-instruction first turn.** The bootstrap task is unusually terse and imperative ("...and wait") with no other content in that turn. It's possible the model occasionally treats "wait" as license to simply stop without an explicit tool call, especially under `haiku`'s smaller-model behavior. This wouldn't require any code defect anywhere in the harness.
- **A hook-wiring race that swallows the `agentctl reply` invocation itself**, distinct from the model not attempting it. Not distinguished from the model simply not calling it -- would require an interaction/tool-use transcript (not currently captured for probe trials; `configure_cmdlog`'s Bash-only cmdlog is never wired into `runner.py`'s trial path per the existing `explore-lostdoorbell-c014` finding, so nothing here confirms which is happening).
- **The order effect suggested by Section 4's last-two-of-eight clustering** -- possibly per-process, per-tmux-server, or per-API-session state degrading slightly over several sequential spawns in one Python process invocation. Not confirmed at this sample size; worth re-testing with a larger N and checking whether failures cluster late in a run or are uniformly distributed.
- **Possible link to the known `send-enter-not-submitted-bug.md` finding** (`work_organisation/probe/send-enter-not-submitted-bug.md`): that bug documents the Enter keystroke sometimes not registering as submit after a `send-keys` pair. Attempt 3 above shows `_bootstrap`'s doorbell retry firing after 90s with no `turn_start` -- consistent with (but not proof of) the first Enter not landing. However, that doesn't explain the *other* 3 occurrences (attempts 2, 4, 5, and both exploratory-probe failures), all of which show `turn_start` firing promptly on the *first* doorbell attempt -- so even if the Enter-not-submitted bug contributes to some fraction of these, it clearly isn't the whole story: most observed instances have the doorbell landing and a turn actually starting, with the failure being the model's non-reply within that turn, not a delivery failure.

## 6. Practical impact

- Any probe brief run (not just `B002`) can lose a control or target trial to this, burning real-Haiku time and cost for zero data.
- `B002-control`'s `expect_rate: 1.0` combined with `run_brief` raising `HarnessError` on any control trial failure means **the entire run aborts before the target brief ever executes** if this flake hits even once among the control's `trials` count -- a point `TICKET-007`'s own review (F6) flagged as a risk in the abstract; this finding shows it happening in practice at a materially higher rate than "not hypothetical" implied.
- The failure is silent from the ledger's perspective: `HarnessError` from `_run_trial`/`run_brief` propagates before any `append_ledger`/`append_journal` call, so there is no persistent record of how often this has happened historically -- only the console output and preserved artifact (if `preserve=failed` kept it) show it at all.

## 7. Suggested fix directions (not decided -- for human review)

1. **Retry the bootstrap wait, not just the doorbell.** `_bootstrap` (agentctl.py) already retries the *doorbell* once if `turn_start` doesn't appear. Consider an analogous retry at the `runner.py` level (or inside `agentctl` itself) if `turn_start`/`turn_end` fire but no `reply` follows within some shorter grace window -- e.g., send a nudge message or simply re-ring/re-prompt once before giving up at the full 120s.
2. **Capture the transcript on bootstrap failure**, not just the bus/inbox/outbox, so a future investigator can see what (if anything) the model was doing instead of calling `reply` -- currently nothing captures this for the probe harness's trial path.
3. **Track this as its own metric** in `journal.jsonl`/ledger even when it causes a full-run abort, so its rate is visible over time instead of only showing up as console noise whoever happens to be watching a particular run.

## 8. Constraints for whoever picks this up

- No changes have been made to `agentctl.py` or `runner.py` beyond TICKET-007's own unrelated `turn_end`-wait fix (which is not implicated in this finding -- every occurrence here happens during the bootstrap turn, before any B002-specific `_wait_for_turn_end` code ever runs).
- This finding does not block TICKET-007's own fix from being correct; it blocks *measuring* TICKET-007's fix cleanly, since `probe.py run B002` can't currently be trusted to complete without hitting this unrelated flake.
