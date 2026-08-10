### Ticket 009: Recover from a real-Haiku bootstrap turn that ends without calling `agentctl reply`

#### Overview
`probe/lib/runner.py`'s `_wait_for_bootstrap` (lines 203-219) waits up to 120s (`READY_TIMEOUT`) for the freshly-spawned worker to emit a `type=reply` bus event after its bootstrap turn, and raises `HarnessError` on timeout, aborting the whole trial. `work_organisation/probe/haiku-bootstrap-reply-gap.md` documents that in a dedicated 8-run isolated probe, 2/8 (25%) of bootstrap turns genuinely started (`turn_start` fired) and in both cases genuinely ended (`turn_end` fired, i.e. the model finished generating and stopped) **without the model ever calling `agentctl reply`** — the outbox stayed empty and the only event in `bus.jsonl` between `turn_start` and `turn_end`/`exit` was nothing. `agentctl.py`'s own `_bootstrap` (agentctl.py:1587-1604, verified below) only proves the doorbell keystroke landed by waiting for `turn_start`; it has no knowledge of, and does not wait for, `reply`. The only thing currently enforcing "the worker actually replied" is `runner.py`'s single 120s wait, which just times out and force-kills the SUT — burning real-Haiku spawn time for zero data and, per the finding doc, aborting 4 of 6 recent `probe.py run B002` attempts. This blocks TICKET-007's step 5 (B002 measurement), which needs many consecutive clean bootstrap turns.

**Root cause is not established** (finding doc, `root_cause: not established`, Section 5 lists candidate hypotheses only: a genuine Haiku instruction-following gap on a terse single-instruction first turn; a hook-wiring race distinct from the model simply not calling reply; an order effect suggested by both observed failures being the last two of eight sequential spawns, at n=8 not statistically meaningful; a possible partial link to the known `send-enter-not-submitted-bug.md`, which the doc itself shows does not explain most occurrences since `turn_start` fired promptly in all but one case). This ticket implements the finding doc's Section 7 fix direction #1 — a bounded, verifiable mitigation — not a root-cause fix, because no root cause is confirmed to fix. It also improves the failure's diagnosability per Section 7 #2 in a lightweight way that doesn't require the larger transcript-capture project.

#### Implementation Steps
1. **`probe/lib/runner.py` — verify the code path yourself before changing it.** Confirm live (or by re-reading) that `_bootstrap` in `agentctl.py:1587-1604` returns as soon as `EventType.TURN_START` is observed (line 1599) and never checks for a `reply` event — this is the mechanism the finding doc's Section 3 table describes ("`_bootstrap` only waits for `turn_start`... the actual reply-timeout enforcement happens one layer up, in `runner.py`'s `_wait_for_bootstrap`"). Do not assume the doc is correct without this check, per the doc's own Section 8 constraints and this ticket's assignment.
2. **`probe/lib/runner.py` — split `_wait_for_bootstrap`'s single 120s wait into a grace window plus a conditional nudge-and-retry.** Replace lines 203-219:
   - Add a module constant `BOOTSTRAP_REPLY_GRACE = 60.0` near `READY_TIMEOUT` (line 29).
   - Add a module constant with the nudge body:
     ```python
     _BOOTSTRAP_NUDGE = "Your previous turn ended without calling `agentctl reply`. Call `agentctl reply --status reply` now with any short body."
     ```
   - Rewrite `_wait_for_bootstrap` as:
     ```python
     def _wait_for_bootstrap(sut: Sut, watermark: int) -> None:
         """Wait for the durable bootstrap reply before taking send watermarks.

         A worker's bootstrap turn can start and end without ever calling
         `agentctl reply` (root cause unconfirmed --
         work_organisation/probe/haiku-bootstrap-reply-gap.md). That failure
         is silent: `_bootstrap` (agentctl.py) only confirms the doorbell
         landed via `turn_start`, not that the worker replied. Split the wait
         so a stalled-but-turn-ended worker gets one explicit nudge before the
         trial is aborted, instead of only ever waiting once and giving up.
         """
         first_window = min(BOOTSTRAP_REPLY_GRACE, READY_TIMEOUT)
         completed = _invoke(
             sut,
             ["wait", "--until", f"agent={WORKER_NAME},type=reply", "--from-seq", str(watermark), "--timeout", str(first_window)],
             timeout=first_window + 5,
         )
         if completed.returncode == 0:
             return
         if completed.returncode != 2:  # agentctl's EXIT_TIMEOUT; anything else is a real wait error
             raise HarnessError(f"worker bootstrap did not finish: {completed.stderr.strip()}")

         turn_ended = _invoke(
             sut,
             ["wait", "--until", f"agent={WORKER_NAME},type=turn_end", "--from-seq", str(watermark), "--timeout", "0"],
             timeout=5,
         )
         if turn_ended.returncode == 0:
             _send(sut, _BOOTSTRAP_NUDGE)

         remaining = READY_TIMEOUT - first_window
         completed = _invoke(
             sut,
             ["wait", "--until", f"agent={WORKER_NAME},type=reply", "--from-seq", str(watermark), "--timeout", str(remaining)],
             timeout=remaining + 5,
         )
         if completed.returncode != 0:
             raise HarnessError(
                 f"worker bootstrap did not finish after nudge (turn_end observed before nudge: {turn_ended.returncode == 0}): {completed.stderr.strip()}"
             )
     ```
   - `_send(sut, _BOOTSTRAP_NUDGE)` is called **without** `force=True`, matching the existing `_send` default (runner.py:192-200): if the worker is not yet idle (turn hasn't actually ended despite the zero-timeout `turn_end` check racing it), `_send`'s `--wait-idle READY_TIMEOUT` makes delivery wait for idle rather than clobbering an in-flight turn. This is the same idle-respecting delivery every other instruction in this file already uses (`_inbox_discipline`, `_lost_doorbell`, `_watermark`) — do not special-case the nudge to use `--force`.
   - The `turn_ended` check uses `--timeout 0` (a non-blocking poll of already-emitted events) specifically so it costs no wall-clock time when the turn is still in flight — in that case, skip the nudge and just consume the remaining wait budget normally, since the worker may still be about to reply on its own.
3. **`probe/lib/runner.py` — no change needed to `_run_trial`, `run_trials`, or `run_brief`.** The mitigation is entirely internal to `_wait_for_bootstrap`; a successful nudge-recovered bootstrap looks identical to a first-try success from every caller's perspective (returns normally, no exception). Do not thread new state through `_run_trial`'s `TrialResult` for this — recording *that* a nudge fired is step 4's job, done independently.
4. **`probe/lib/runner.py` — surface the nudge in the raised `HarnessError` message only; do not add journal/ledger tracking in this ticket.** The finding doc's Section 7 #3 suggests tracking this as its own journal metric. Investigated and rejected for this ticket: `probe/lib/journal.py`'s `_validate_trial` (lines ~230-243) requires a `trial` entry to carry `trials`, `passed`, `rate`, `control_rate`, `wall_seconds`, and a resolvable claim `cell` — none of which a single mid-trial bootstrap nudge/timeout naturally has, and `append_ledger`/`append_journal` in `run_brief` (runner.py:84-85) only fire after a full brief's trials complete without exception, which a `HarnessError` from `_wait_for_bootstrap` prevents from ever being reached (this is the exact silent-from-the-ledger gap the finding doc's Section 6 describes). Designing a new journal entry kind for this is a real schema change with its own validation rules and is out of scope here — see Follow-ups. For this ticket, it is enough that the final `HarnessError` message (step 2) states whether `turn_end` was observed before the nudge, since that string reaches the console today (`_spawn_worker`/`_run_trial` already surface `HarnessError.args` on abort) and is the cheapest possible improvement to "was this the reply-gap symptom or something else" without a schema change.
5. **Tests — new file `tests/test_probe_runner.py`** (no such file exists yet; `runner.py` currently has no dedicated unit tests). Import `probe.lib.runner as runner` and `probe.lib.sut.Sut`, monkeypatch `runner._invoke` with a fake that returns scripted `subprocess.CompletedProcess` objects keyed by the `arguments` list passed in (assert on `arguments[1]`/`arguments[3]` — the `--until` value — to distinguish the `type=reply` calls from the `type=turn_end` poll), and monkeypatch `runner._send` to record calls instead of invoking `agentctl`:
   - `test_wait_for_bootstrap_returns_immediately_on_first_window_reply`: first `wait --until type=reply` call returns `returncode=0`; assert `_wait_for_bootstrap` returns without calling `_send` and without a second `wait --until type=reply` call.
   - `test_wait_for_bootstrap_nudges_when_turn_already_ended`: first reply-wait returns `returncode=2` (timeout); the `turn_end` poll returns `returncode=0`; the second reply-wait returns `returncode=0`. Assert `_send` was called exactly once with `_BOOTSTRAP_NUDGE` and no `force` keyword forced to `True`, and that `_wait_for_bootstrap` returns without raising.
   - `test_wait_for_bootstrap_skips_nudge_when_turn_still_running`: first reply-wait returns `returncode=2`; the `turn_end` poll returns `returncode=2` (not yet ended); second reply-wait returns `returncode=0`. Assert `_send` was **not** called.
   - `test_wait_for_bootstrap_raises_with_turn_end_context_after_failed_nudge`: first reply-wait `returncode=2`; `turn_end` poll `returncode=0`; second reply-wait (post-nudge) `returncode=2` again. Assert `HarnessError` is raised and its message contains `"turn_end observed before nudge: True"`.
   - `test_wait_for_bootstrap_raises_immediately_on_non_timeout_error`: first reply-wait returns some other nonzero code (e.g. `1`, simulating a real `agentctl wait` invocation error, not a timeout). Assert `HarnessError` is raised immediately, with **no** `turn_end` poll and no nudge attempted (this preserves today's behavior for genuine errors — only exit code `2`, the documented timeout code per `agentctl.py`'s `_cmd_wait` docstring, triggers the new grace-window path).

#### Explicit Constraints & Warnings
- **Do not modify `agentctl.py`.** This ticket is scoped to the probe harness (`probe/lib/runner.py`) only. `agentctl.py`'s `_bootstrap` doorbell-retry behavior (agentctl.py:1587-1604) is a separate, already-working mechanism (it retries the *doorbell* on missing `turn_start`) and is not implicated in this finding — every occurrence in the finding doc shows `turn_start` firing promptly.
- **Do not claim this fixes the root cause.** The finding doc is explicit that root cause is unconfirmed at n=8. This ticket's mitigation is a bounded recovery (one nudge) that should raise the observed success rate without asserting *why* the model sometimes doesn't reply. Do not edit the finding doc's `root_cause: not established` frontmatter or Section 5 as part of implementing this ticket — closing this ticket does not close that open question.
- **Do not add a full transcript-capture mechanism.** The finding doc's Section 7 #2 and the existing `explore-lostdoorbell-c014` finding both note that no interaction/tool-use transcript is currently captured for probe trials and that `cmdlog_hook.py`/`configure_cmdlog` is Bash-only and not wired into `runner.py`'s trial path. Wiring that up is a materially larger, separate project — do not fold it into this ticket.
- **`BOOTSTRAP_REPLY_GRACE` (60s) plus the nudge's own `_send` wait (up to `READY_TIMEOUT`=120s if the worker is unexpectedly busy) plus the remaining window (60s) can, in the worst case, extend a single trial's bootstrap wait well past the original 120s.** This is an accepted tradeoff (a recovered trial is strictly better than an aborted one) but must not be silently hidden — the docstring added in step 2 must state it, and this ticket does not change `_spawn_worker`'s or `_invoke`'s own subprocess `timeout=` values (which bound the *individual* `agentctl` CLI calls, not the trial as a whole) beyond what's already listed in step 2's code.
- **Do not change the `type=reply` bus predicate or add a new event type.** The nudge relies entirely on existing `agentctl` primitives (`wait --until ...,type=turn_end` with `--timeout 0` as a non-blocking poll, and the existing `send` path). Do not add new instrumentation to `agentctl.py` to make this cheaper — that would violate the "no `agentctl.py` changes" constraint above.

#### Acceptance Criteria
- [Automated] All five new tests in `tests/test_probe_runner.py` (step 5) pass.
- [Automated] Existing `tests/test_probe_*.py` and `tests/test_*.py` suites remain green — this change touches no shared module other than `runner.py`.
- [Manual] Re-run the finding doc's Section 4 style isolated bootstrap-only probe (spawn with the standard `HANDSHAKE_READY` bootstrap task, no brief content) for at least 8 sequential repeats against the patched `_wait_for_bootstrap`. Confirm any run that previously would have hit the 120s force-kill instead either (a) recovers via the nudge and reports success, or (b) still fails but the console `HarnessError` message now states whether `turn_end` was observed before the nudge — either outcome is acceptable evidence the code path is exercised; a 0% recovery rate at small n does not by itself invalidate the change, since root cause is unconfirmed, but should be reported back rather than assumed away.
- [Manual] With the patch applied, attempt `probe.py run B002` (or a smaller `--trials` slice of it) and confirm it no longer aborts specifically on the "no `turn_end`/`turn_start` with zero `reply` events, forced exit" symptom described in the finding doc's Section 3 table. (It may still abort for unrelated reasons — that is out of scope.)

#### Follow-ups (explicitly out of scope for this ticket)
- Designing a journal entry kind (or reusing `explore`/`invalidate`) capable of recording a bootstrap-nudge event even when the enclosing trial aborts, so the finding doc's Section 6 "silent from the ledger" gap is closed for real. Needs its own schema design against `probe/lib/journal.py`'s validation rules — not attempted here (step 4).
- Wiring a transcript/tool-use capture into `runner.py`'s trial path (finding doc Section 7 #2; also blocked on the existing `cmdlog` gap noted in `explore-lostdoorbell-c014`), so a future investigator can see what the model was doing instead of calling `reply` rather than inferring it from bus timestamps alone.
- Re-testing the finding doc's Section 5 "last-two-of-eight" clustering hypothesis at a larger N, and specifically whether failures cluster late in a sequential-spawn run or are uniformly distributed — relevant to whether a future fix should live in `runner.py` (per-trial, as this ticket does) or somewhere that tracks state across trials in one run.
