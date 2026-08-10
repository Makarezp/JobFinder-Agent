# TICKET-007 Handoff

Worktree: `.../ticket-impl/worktrees/impl-007` (detached HEAD off `main`, currently at `9cd30c6`).
Ticket: `work_organisation/tickets/TICKET-007-lost-doorbell-message-dropped.md` (post defensive-architect review version; review at `TICKET-007-review.md`, both in the main working copy, not in this worktree's git history).

## 1. Done and committed (in order, on top of `main`@`e8ec234`)

1. `2ad370f` -- **Step 0**: committed `work_organisation/probe/explore-lostdoorbell-c014/` and `explore-20260808T170211424180Z-c002/`, copied byte-for-byte from the main working copy (they were untracked there; worktrees don't inherit untracked files). Excludes `.omc/` session-noise files.
2. `ae66c41` -- **Unplanned prerequisite fix**: `.gitignore:14` had a bare `lib/` entry (Python-venv boilerplate) that was unintentionally also matching `.agent/skills/agent-tabs/probe/lib/` -- not build output, the harness's actual source package (`runner.py`, `sut.py`, `oracle.py`, etc., ~2,369 lines). It had **never been in git history** despite `ledger.jsonl`/`journal.jsonl` recording commit provenance for every measurement made with it. Removed the redundant line (`.venv/` on line 25 and `frontend/.gitignore`'s `/node_modules` already cover the real cases) and committed the pre-existing `lib/` contents as a baseline, plus 4 mechanical `isinstance(x, (int, float))` -> `isinstance(x, int | float)` rewrites in `journal.py`/`oracle.py` needed to pass this repo's ruff gate (which had never run against this code before). Human sign-off obtained before doing this (touches a shared `.gitignore` and adds a large untracked tree to history for the first time) -- see reply/question history.
3. `07754b9` -- **Step 1**: corrected `explore-lostdoorbell-c014/README.md`. Struck the false "the final turn completed normally, not truncated" claim; a turn completes on `turn_end` (the `Stop` hook), not on `reply` (a `PostToolUse` side effect) -- `turn_end` never fired for the losing turn, and the SUT was killed 0.822s after the reply, faster than the 1.7-3.7s post-reply windows in the same transcript's two completed turns. Reclassified `Target` as three candidates in descending likelihood (harness teardown race / worker behavior / methodology) and updated front-matter status to "inconclusive."
4. `9cd30c6` -- **Step 2**: the harness fix. Added `_wait_for_turn_end` to `.agent/skills/agent-tabs/probe/lib/runner.py`, mirroring the existing `_wait_for_bootstrap`/`_wait_for_reply` pattern (same `agentctl wait --until` predicate, bounded by `brief.wait_timeout`), and call it once after the shared third-message `_wait_for_reply` in `_lost_doorbell`. That code path is common to both `B002` (target) and `B002-control`, so one call fixes both. Confirmed in practice: the preserved bus.jsonl from one of the failed retries below shows a `reply` -> `turn_end` pair completing cleanly for a mid-scenario message under the new code.

Trial budget was pre-registered with the human at **10 trials** (not the statistically tighter 30), accepting the wider ~25.9% one-sided 95% CI on a clean 0-failure run. This must be recorded honestly in `README.md`/`COVERAGE.md` per step 4/6 of the ticket -- not as a bare "covered."

## 2. What's left

1. **Get one clean `probe.py run B002` invocation** (see open problem below -- this is currently blocked by a harness-reliability issue, not by anything wrong with the code).
2. **Step 6**: branch on the measured rate against the pre-registered rule (0/10 -> record "drop rate <=25.9% at 95% CI," not "covered"; >=1 failure -> confirmed gap, proceed to step 7 -- compare `doorbell_text` backlog-count lever vs. `probe-worker.md` wording per step 3, prefer the code lever per the ticket's own reasoning).
3. **Step 8** (only if step 7 fires): re-measure once at the same trial count.
4. **Step 9**: `python3 .agent/skills/agent-tabs/probe/probe.py coverage --write`, regardless of branch, so `COVERAGE.md`'s `C014` entry reflects the corrected-harness measurement.
5. Manual acceptance criteria: confirm `explore-lostdoorbell-c014/README.md`'s status/front-matter reflects the final outcome (bounded-clean / reproduced-and-fixed / reproduced-and-documented-as-limit) -- currently set to "inconclusive... pending re-measurement," needs updating once step 6 resolves.
6. Phase-gate: per the sprint framework, a Hard Blocker sign-off is owed at the end of Phase 2 (implementation complete, before Review) and again at Phase 3 sign-off. Neither has happened yet.
7. **Merge**: once the above is done and signed off, merge this worktree's commits into `main` the same way impl-006's `TICKET-006` work was merged (ask the orchestrator/human for the exact mechanism used there if not obvious from `main`'s reflog/log).

Run command (from this worktree's root, no `.venv` needed -- confirmed plain system `python3` works, `agentctl`/`probe.lib` have no third-party deps):
```
python3 .agent/skills/agent-tabs/probe/probe.py run B002
```

## 3. Open problem: measurement harness reliability (separate from the ticket's own fix)

`probe.py run B002` has aborted **6 times in a row** (attempts exhausted per the human's "stop at ~4-6" instruction) before ever producing a ledger/journal entry. 5 aborted on the **control brief** (`B002-control`); the 6th finally cleared the control brief (10/10) for the first time, then aborted on **target trial 5**. Every abort raised `HarnessError` from inside `run_trials`/`_run_trial`, and none of the 6 produced a ledger/journal entry (confirmed empty diff each time), so per the ticket's own guidance none count against the "run B002 at most twice" cap -- but each attempt burns several real minutes of real-Haiku API cost with zero data produced.

The 6 failures, in order:
1. Control trial 7: worker's third reply didn't land inside the 10s `wait_timeout` (but its second message's turn completed cleanly `reply`->`turn_end`, confirming the new wait works correctly when given the chance).
2. Control trial 4: no reply at all to the bootstrap message within the 120s `READY_TIMEOUT`.
3. Control trial 1: bootstrap `turn_end` fired cleanly ~13s in, but the worker never called `agentctl reply` that turn at all -- outbox stayed empty, forced-killed ~108s later when `_wait_for_bootstrap`'s 120s timeout expired.
4. Control trial 2: bootstrap `turn_start` fires, then nothing -- no reply, no `turn_end` -- forced-killed at the 120s mark.
5. Control trial 2 (again, different run): identical symptom to #4.
6. **Target trial 5** (control brief passed 10/10 this time): identical symptom to #3/#4/#5 -- bootstrap `turn_end` fired ~14s in with no `agentctl reply` ever called, forced-killed ~106s later at the 120s `READY_TIMEOUT` mark.

**Refined diagnosis**: 4 of the 6 failures (and both distinct recurring symptoms across all 6) trace to the same place -- the worker's very first turn (bootstrap: "Open your inbox, then reply exactly HANDSHAKE_READY... and wait") sometimes ends (`Stop` hook fires, i.e. the model genuinely stopped generating) **without the model ever invoking `agentctl reply`**, despite that being the bootstrap's one explicit instruction. This is upstream of any B002-specific content -- it happens before message A is ever sent, and happened once on the *target* brief's trial 5 too, so it isn't specific to the control path. This looks like a real Haiku-model instruction-following/reliability gap on the bootstrap turn specifically (rate roughly 1-in-6 sequential-run attempts hit it at least once across ~10-20 SUT spawns per attempt), not a harness code defect and not machine contention (ruled out by the human -- all other agent-tabs agents were idle when the failures happened).

I initially hypothesized machine-level contention (this box had ~19 tmux sessions from other concurrent agent-tabs work at the time of the first failures). The human checked and **ruled this out**. Root cause is therefore the bootstrap-non-reply pattern above; still unconfirmed *why* the model sometimes stops without replying on that specific turn (candidates: something about the bootstrap prompt/role text, an occasional hook-wiring race that swallows the `agentctl reply` invocation, or genuine haiku-model flakiness independent of this harness).

Retry logs, each one `harness error: B002[-control] trial N did not execute: <artifact temp dir>`:
- `/tmp/ticket007_b002_run1.log` (control trial 7)
- `/tmp/ticket007_b002_run1_retry.log` (control trial 4)
- `/tmp/ticket007_b002_run1_retry2.log` (control trial 1)
- `/tmp/ticket007_b002_run1_retry3.log` (control trial 2)
- `/tmp/ticket007_b002_run1_retry4.log` (control trial 2)
- `/tmp/ticket007_b002_run1_retry5.log` (**control passed 10/10**, then target trial 5)

Each preserved artifact's temp directory (path is in the corresponding log line) has a full `bus.jsonl` plus `agents/worker/{inbox,outbox,meta.json,settings.json}` -- these are ephemeral `/private/var/folders/.../T/...` temp dirs and will be cleaned up by the OS eventually; if this needs deeper investigation later, pull the paths from the logs above before they age out.

This is worth its own follow-up (possibly its own ticket) regardless of how TICKET-007 resolves: **B002-control's own `expect_rate: 1.0` combined with `run_brief` raising `HarnessError` before any target trial runs makes the harness very fragile to exactly this kind of flake** -- a point the ticket's own review (F6) already flagged as a risk, now observed in practice at a much higher rate than "control flakiness is not hypothetical" implied. Worse, the same bootstrap-non-reply flake also hit the *target* brief on the one attempt that got that far, so a future re-run attempting all 10 target trials is likely to hit it again partway through, not just on the control side.

## 4. Follow-up finding: `work_organisation/probe/haiku-bootstrap-reply-gap.md`

Per the human's decision (investigate before spending more B002 budget), this is now written up as its own standalone finding doc, following the `send-enter-not-submitted-bug.md` template: **`work_organisation/probe/haiku-bootstrap-reply-gap.md`** (commit `77e5f8b`).

Summary of what it found: a cheap, isolated bootstrap-only exploratory probe (8 sequential spawns, no B002 content at all -- same role/model/task as `runner._spawn_worker`, same 120s timeout) reproduced the exact symptom seen in 4 of the 6 full `probe.py run B002` attempts: the worker's bootstrap turn starts (and often ends, `Stop` hook fires) without the model ever calling `agentctl reply`. Rate observed: **2/8 (25%)** in the isolated probe, roughly consistent with 4/6 full-run attempts hitting it at least once across ~10-20 sequential spawns per run. This is upstream of any B002-specific content and unrelated to this ticket's `turn_end` fix -- it happens during the bootstrap turn, before any brief-specific message is ever sent. Root cause not yet confirmed; candidate hypotheses and suggested fix directions are in that doc.

## 5. Status as of this writing -- step 5 measurement paused pending this finding

The 6th attempt (started 13:09 local) completed: control brief passed 10/10 for the first time, then target trial 5 hit the bootstrap-non-reply flake described above and aborted with `HarnessError`. No ledger entry was produced. Per the human's explicit instruction ("if it also failed, stop retrying and report the failure pattern instead of trying a seventh time"), retries were stopped at 6 and the flake was investigated and documented separately (Section 4) rather than attempting a 7th `probe.py run B002`.

Per the human's follow-up instruction, **full B002 measurement runs should not resume** until this has been reported back and reviewed. Step 5 remains incomplete; whoever picks this up next needs a decision from the human on how to proceed given `haiku-bootstrap-reply-gap.md`'s findings (e.g., accept the ~25% per-spawn flake rate and just keep retrying full runs until one clears; fix the flake first; or find a cheaper way to get a trustworthy B002 measurement despite it).
