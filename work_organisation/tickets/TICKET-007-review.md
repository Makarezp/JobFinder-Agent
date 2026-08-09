# Review: TICKET-007 — Lost-Doorbell Message Drops (C014)

**Reviewer:** review-007 (Defensive Architect)
**Verdict:** **Do not execute as written.** The ticket rests on a factual claim that its own preserved evidence contradicts, and its step-1 measurement — the step everything else branches on — is instrumented in a way that cannot distinguish the hypothesis from the harness. Executing steps 1–5 in the given order would spend ~40 minutes of real Haiku time producing a number that means something other than what the ticket will read into it.

Below, every claim is checked against source, not against the ticket's or the spec's description of the source.

---

## F1 — BLOCKER: "the turn completed normally, not truncated" is false

Both the ticket (Overview) and the spec (`explore-lostdoorbell-c014/README.md` §1 Evidence) assert:

> `bus.jsonl` shows the final turn completed normally (`turn_start` seq 11 -> `reply` seq 12) before the harness force-closed the SUT (seq 13) — i.e. this is not a truncated-turn artifact like the prior `B001`/`B003` `harness`-verdict findings; the worker had a complete turn and simply didn't report the earlier message.

This is not what `bus.jsonl` shows. A turn is marked complete by `turn_end`, not by `reply`. From the worker's own `settings.json` (preserved at `evidence/run/agents/worker/settings.json`), the event wiring is:

| bus event | Claude hook |
|---|---|
| `turn_start` | `UserPromptSubmit` |
| `turn_end` | **`Stop`** |

`turn_end` fires when the model *stops*. `reply` is just a `PostToolUse` side effect of the worker running `agentctl reply` — it says nothing about whether the turn was over.

Walking the preserved `bus.jsonl`:

| turn | `turn_start` | `reply` | `turn_end` | reply → turn_end |
|---|---|---|---|---|
| 1 | 17:18:02.827 | 17:18:28.651 | 17:18:32.398 | **3.747 s** |
| 2 | 17:18:32.752 | 17:18:39.845 | 17:18:41.527 | **1.682 s** |
| 3 | 17:18:41.891 | 17:18:48.532 | **— never fired —** | killed at **0.822 s** (`exit`/`forced`, seq 13) |

**Turn 3 has no `turn_end`.** The Stop hook never fired. The harness killed the SUT 0.822 s after the reply — *shorter than either of the two post-reply windows actually observed in this same transcript*. In both completed turns, the worker kept working for 1.7–3.7 s after calling `reply`.

So the preserved run is **exactly** the truncated-turn artifact the spec claims it is not. It is indistinguishable from the `B001`/`B003` `harness`-verdict findings the spec explicitly distances itself from. The worker may well have gone on to read `inbox/0003.md` and emit a second reply to `outbox/0004.md`; it was killed inside the window where that would have happened.

**Required correction:** Strike the "turn completed normally / not truncated" claim from the ticket Overview and from `explore-lostdoorbell-c014/README.md` §1. The preserved trial is **inconclusive**, not a confirmed drop. Downgrade the spec's `Target` from "real worker behavior vs. measurement methodology" to include a third, currently-most-likely target: **harness teardown races the worker's turn.**

**Ruled out, for the record** (I checked the alternative mundane explanations the assignment raised, and these do *not* hold):
- *Race between `write_lost_doorbell` and turn 3 starting:* dead. Per `runner._lost_doorbell` (lines 159–173) the ordering is `_wait_for_reply` → `write_lost_doorbell` → `_seq` → `_send`. B (`inbox/0003.md`) was therefore written between turn 2's `reply` (17:18:39.845) and C's `message_sent` (17:18:41.801). Turn 3 started at 17:18:41.891. B was on disk before turn 3 began. Also note `_send` passes `--wait-idle`, so C's doorbell was typed only after the worker went idle.
- *Context-window exhaustion:* implausible. Three short turns, a 1,306-byte bootstrap, three 72-byte messages.
- *An early-exit heuristic in `probe-worker.md`:* the role file is a single sentence with no exit condition.

---

## F2 — BLOCKER: `B002` is built with the same teardown race, so step 1 cannot disambiguate anything

This is the structural problem. From `runner._run_trial` (lines 103–123) and `_lost_doorbell` (159–173), the target trial ends like this:

```python
_send(sut, _instruction(third))
_wait_for_reply(brief, sut, watermark)      # returns on the FIRST reply after watermark
...
replies = [message.body for message in outbox_messages(sut, WORKER_NAME)]   # read immediately
GRADES[brief.grade](brief.id, replies, expected, expected)
finally:
    artifact = destroy_sut(sut, preserve=failed)   # close-run --force + tmux kill-session
```

`_wait_for_reply` (227–242) waits for `type=reply` `--from-seq <watermark>` — the *first* one. There is **no wait on `turn_end`, no settle, no grace period.** The outbox is read and graded at the instant the first post-C reply lands, and the SUT is force-killed immediately after.

Therefore `B002` does not measure "did the worker drop B." It measures:

> **"Did the worker echo B's token at or before its first reply following C's doorbell?"**

A worker that behaves *exactly as the protocol requires* — replies to the file the doorbell pointed at, then sweeps the rest of the inbox and replies again — is graded **failed**, and its SUT is destroyed before the second reply can be written. That is precisely the shape of the preserved miss (F1).

**Consequence for the ticket:** step 1's rate is confounded. A rate below 1.0 does not confirm the finding, and the ticket's step-2 branch language ("treat this as a confirmed, non-rare gap and proceed to step 3") would fire on an artifact of the runner. Step 3 would then edit `WORKER.md` to fix a bug that lives in `runner.py`.

**Required correction — do this before step 1, not after:** make the trial wait for turn completion before grading. Concretely, in `_lost_doorbell`/`_run_trial`, after the final `_wait_for_reply`, add a wait on `agent=worker,type=turn_end --from-seq <the reply's seq>` bounded by `brief.wait_timeout`, and only then read `outbox_messages`. `agentctl wait --until` already supports the predicate — `_wait_for_bootstrap` and `_wait_for_reply` both use it, so this is a two-line change with an existing primitive, not a new mechanism. Without it the ticket's central number is uninterpretable and step 4's re-measure is uninterpretable too.

---

## F3 — BLOCKER: Step 3's proposed wording makes F2 *worse*, and step 4 will read the damage as a regression

Step 3 proposes strengthening `WORKER.md` so that "a turn with N unread files requires N acknowledgements," and `probe-worker.md` so the worker lists "every unread inbox filename you found, oldest first, then its token — one line per file."

The first of those phrasings ("N acknowledgements") reads naturally as *N separate `reply` calls*. That is the single worst outcome available given F2: the runner returns from `_wait_for_reply` on reply #1 and grades before reply #2 exists. **The wording change would lower the measured rate while improving actual worker behavior**, and step 4 ("confirm the rate recovers to at or near 1.0") would report failure. The ticket would then hit its own guardrail — "do not keep iterating on wording indefinitely… document that this is an inherent haiku-model instruction-following limit" — and file a false conclusion about model reliability caused entirely by a two-line harness omission.

**Required correction:** If step 3 is reached at all, the wording must mandate **one reply enumerating N tokens**, never N replies. Suggested: *"Before you reply, list every unread inbox file, lowest number first. Your single reply must account for all of them."* Fix F2 first regardless — the correct wording is still unmeasurable without it.

Note also that the ticket's step 3 rewrites `WORKER.md`'s *general* worker protocol in order to fix a *probe-role* reporting requirement. The "list every token you consumed" obligation comes from `probe/roles/probe-worker.md`, not from `WORKER.md`. `WORKER.md` only requires reading unread files; it never requires reporting one line per file. Pushing probe-specific reporting mechanics into the protocol every real worker reads is scope leakage. **Prefer editing `probe-worker.md` alone** and leave `WORKER.md` untouched — which also sidesteps F4 entirely.

---

## F4 — MAJOR: Editing `WORKER.md` invalidates C014's claim hash and shifts four other claims' line anchors. The ticket never mentions this, and one acceptance criterion becomes unsatisfiable.

`claims.jsonl` anchors every claim to an exact inclusive line range and a SHA-256 of those lines (`claims.hash_of`, lines 78–84). `claims.stale` (87–99) marks a claim stale when the recomputed hash differs, and `coverage_counts` (108–113) computes:

```python
covered_count = sum(bool(claim.briefs) and claim.id not in stale_ids for claim in registry)
```

Current anchors in `WORKER.md`:

| claim | `src` | briefs |
|---|---|---|
| C014 | `WORKER.md:9-14` | `["B001","B002"]` |
| C015 | `WORKER.md:33-35` | `[]` |
| C016 | `WORKER.md:47-49` | `[]` |
| C017 | `WORKER.md:53-55` | `[]` |
| C018 | `WORKER.md:57-58` | `[]` |

Step 3 edits the "Check your inbox at the start of every turn" section — **that is lines 9–14 verbatim, C014's own anchor.** Two consequences:

1. **C014 goes stale and drops out of "Covered."** Its hash changes, `stale_ids` picks it up, and `covered_count` excludes it. `COVERAGE.md` would then read `Covered (2): C003, C005` / `Stale (1): C014`. The acceptance criterion *"`COVERAGE.md`'s `C014` entry reflects the 10-trial measurement"* is **unsatisfiable on the step-3 branch** as the ticket is written.
2. **C015–C018's line ranges all shift.** Any net line-count change at lines 9–14 moves everything below it. Their stored ranges (33-35, 47-49, 53-55, 57-58) would then hash the *wrong lines*, marking all four stale as well. `Stale (0)` becomes `Stale (5)`.

There is no CLI escape hatch: `probe.py`'s subcommands are `coverage`, `checks`, `run`, `explore` (probe.py:56–67). **No rehash/re-anchor command exists.** `claims.jsonl` must be hand-corrected.

**Required correction:** Add an explicit step between the ticket's steps 3 and 4: *"After editing `WORKER.md`, update `claims.jsonl` — recompute C014's `hash`, and correct the `src` line ranges and hashes for C015, C016, C017, C018 to match the new file. Verify with `probe.py coverage` that `stale: 0` before re-measuring."* Alternatively, per F3, don't touch `WORKER.md` at all.

---

## F5 — MAJOR: 10 trials cannot distinguish "rare fluke" from "durable failure mode." Both branches of step 2 are under-powered, and the branch criterion contradicts the harness.

The assignment asked directly whether 10 trials is meaningful. It is not, in the direction that matters most.

**Branch 2a ("rate at or near 1.0 → rare fluke, stand down").** With 0 failures in 10 trials, the exact (Clopper–Pearson) 95% upper bound on the true drop rate is `1 − 0.05^(1/10) = 25.9%`. A clean 10-trial run is fully consistent with **one message in four being silently dropped.** For a claim whose entire purpose is "a lost keystroke costs nothing," declaring that a fluke is indefensible.

Power to observe *any* failure in 10 trials:

| true drop rate | P(≥1 failure in 10) |
|---|---|
| 5 % | 40 % |
| 10 % | 65 % |
| 20 % | 89 % |

At a 10 % true drop rate the ticket concludes "fluke" **35 % of the time.**

Trials needed for 0 failures to actually rule something out at 95 %:

| rule out drop rate ≥ | trials |
|---|---|
| 10 % | **29** |
| 5 % | **59** |
| 1 % | 299 |

**Branch 2b** is barely better: 1 failure in 10 (rate 0.90) has an exact 95 % CI on the drop rate of roughly **0.3 % – 44.5 %**. That interval spans "irrelevant" to "catastrophic."

**Separate defect — the branch criterion doesn't exist in the tool.** The ticket's prose says "at or near `1.0`" vs. "meaningfully below `1.0`" and never defines either. `runner.run_brief` (line 67) is binary:

```python
outcome = "no-finding" if rate >= brief.expect_rate else "finding"
```

with `expect_rate: 1.0`. **Any** single failure in 10 records `outcome: "finding"`. A rate of 0.9 is "near 1.0" by the ticket's prose and a `finding` by the ledger. Whoever executes this will have to invent the threshold mid-ticket, which is exactly how a measurement gets read to suit the hypothesis.

**Required correction:** Pre-register the decision rule before running anything. Defensible version: *"Fix F2 first. Then run 30 trials. Zero failures ⇒ the true drop rate is below 10 % at 95 % confidence — record that bound explicitly rather than claiming 'covered'. One or more failures ⇒ confirmed, proceed to step 3."* If 30 trials is unaffordable (see F6), then say so and **record the honest bound** — "clean at n=10, drop rate ≤25.9 % at 95 % confidence" — rather than letting `COVERAGE.md` say `Covered`. Do not let branch 2a write a "not reproduced at scale" verdict; n=10 is not scale.

---

## F6 — MAJOR: The cost model is wrong by 2×, and one control flake destroys the entire two-run budget

The ticket says step 1 "costs roughly 10 trials × ~2-3 minutes of real worker time." Both factors are wrong.

`run_brief` (lines 45–66) runs the **control brief at the same trial count first**, then the target:

```python
count = brief.trials if trials is None else trials
control_results = run_trials(control, trials=count, control=True)
control_rate = _rate(control_results)
if control_rate < control.expect_rate:
    raise HarnessError(...)
results = run_trials(brief, trials=count, control=False)
```

So `probe.py run B002` at the default spawns **20 real Haiku SUTs, not 10.** Measured per-trial cost from the existing ledger entry: `trials: 1` → `wall_seconds: 131.923` for 1 control + 1 target ≈ **66 s per SUT**. Twenty SUTs ≈ **22 minutes per run**; the ticket's two runs ≈ **44 minutes**, plus teardown.

**The sharper hazard:** `briefs/B002-control.md` has `expect_rate: 1.0`. If the control — which is the *same* three-message scenario with B delivered normally — flakes even once in 10, `run_brief` raises `HarnessError` **before the target trials run at all**. No ledger entry is appended, no journal entry, ~11 minutes of Haiku burned, nothing measured. Given F2's race applies identically to the control path (`_lost_doorbell(control=True)` also ends in `_wait_for_reply` with no `turn_end` wait), a control flake is not hypothetical.

The ticket's hard cap — *"Do not run `probe.py run B002` more than the two times this ticket calls for"* — combined with that abort path means **a single control flake leaves the ticket with zero data and no budget to retry.** That is a brittle constraint, not a prudent one.

**Required correction:** State the true cost (20 SUTs/run, ~22 min). Replace the hard cap with a budget: *"Up to N total SUT-trials; a run aborted by control `HarnessError` does not count against the measurement cap."* And fix F2 first — it reduces control flakiness as a side effect.

---

## F7 — MAJOR: There *is* a code-level lever, and the ticket forbids looking at it

The assignment asked whether the delivery mechanism itself could do something smarter. It can, and this is likely the highest-leverage fix available. The ticket forecloses it:

> **Do not treat a low rate as an `agentctl.py` bug.** … If step 3 is reached, the fix surface is instructional wording read by the model, not the inbox/bus code path.

That constraint is wrong. Look at what the doorbell actually types (`agentctl.py:1249`):

```python
def doorbell_text(inbox_path: Path) -> str:
    return _one_line(f"[orchestrator] new instruction: {inbox_path}")
```

**The doorbell names one specific file.** In the preserved run the worker was handed `…/inbox/0004.md` and replied with exactly `TOK-GNB9` — the token in that exact file. This is not the model ignoring an instruction; it is the model doing precisely what the pointer told it to do. The prompt engineering in `WORKER.md` ("read any file you have not already handled") is being asked to override a concrete, imperative, single-file pointer delivered in the same turn. Wording will always be fighting the pointer.

Cheaper, more robust alternatives the ticket should have considered:

1. **Make the doorbell state the backlog.** `f"[orchestrator] new instruction: {inbox_path} ({n} unread files in {inbox_dir}, read all lowest-number-first)"`. `_deliver` already has `paths` and `agent`; counting unread files is a directory scan. This puts the fact *in the same sentence as the pointer* instead of relying on the worker recalling `WORKER.md`.
2. **Coalesce.** When more than one message is pending, point at the directory rather than the newest file.
3. **Surface unread count in the worker-facing read path**, so "how many do I owe?" is answerable mechanically rather than by discipline.

Note the irony in `ring_doorbell`'s own docstring (`agentctl.py:1296–1305`):

> *"A mangled or lost keystroke then costs nothing: the instruction is already on disk and the worker reads its inbox at the start of every turn."*

The code asserts the very guarantee under test. That docstring is a design intention, not an observed property — and C014 exists because nobody had checked.

**Required correction:** Delete the "not the inbox/bus code path" constraint. Replace with: *"Evaluate both levers. Compare the wording change against making `doorbell_text` carry the unread-file count, and prefer whichever measures better."* Prompt-engineering a non-deterministic model is the *last* resort, not the mandated one.

---

## F8 — MODERATE: The premise that C010/C015–C018 are "probed clean" is false; there is no regression net for a `WORKER.md` edit

I was asked whether step 3's edit risks regressing other worker-behavior claims already probed clean this session. Checking `claims.jsonl` directly:

```
C010 … "briefs":[]      C015 … "briefs":[]      C016 … "briefs":[]
C017 … "briefs":[]      C018 … "briefs":[]
```

All five have **no brief assigned and have never been run.** `COVERAGE.md` confirms: `Uncovered (12): C001, C002, C004, C006, C007, C008, C009, C010, C015, C016, C017, C018`. Only C003, C005, C014 are covered — and C014's coverage is the single trial this ticket is disputing.

This makes the situation *worse*, not better, than the ticket assumes. There is **no automated regression net at all** for a `WORKER.md` edit — 12 of 15 claims are unmeasured, so a wording change that degrades C015–C018 would be invisible. The manual acceptance criterion ("a reviewer confirms `WORKER.md` … doesn't contradict the rest of the worker protocol") is the *only* guard, and it is doing far more load-bearing work than the ticket implies.

On the specific "Two rules" concern: the risk is real but it's about **dilution, not contradiction**. `WORKER.md` is 59 lines. Step 3 proposes expanding the inbox section into an itemized procedure, pushing "Never assume the orchestrator can see your screen" (C017) and "Do not manage other workers" (C018) further from the top of a document a Haiku worker reads once. Nothing contradicts, but attention is finite and C017/C018 have zero measurement backing them. This reinforces F3's recommendation: **edit `probe-worker.md`, leave `WORKER.md` alone.**

---

## F9 — MODERATE: Re-running B002 yields *weaker* evidence than what already exists, and the grade doesn't check per-turn attribution

Two instrumentation gaps that affect what step 1 can actually tell you:

**No cmdlog in B002 trials.** `probe/lib/sut.py:109` defines `configure_cmdlog(sut)`, which installs the `PreToolUse`/`PostToolUse` hook that produces `commands.jsonl`. Grepping the tree, its only caller is `tests/test_probe_substrate.py:66` — **`runner._run_trial` never calls it.** So `probe.py run B002` produces `bus.jsonl` only. Any failing trial preserved by step 1 will have *less* diagnostic detail than the hand-run evidence already sitting in `explore-lostdoorbell-c014/`. The ticket tells the executor to fall back on the preserved evidence for mechanics — correct advice, but the reason is a wiring gap worth recording, not a design choice.

**The existing cmdlog is Bash-only.** `configure_cmdlog` sets `"matcher": "Bash"` (sut.py:123), and every record in the preserved `commands.jsonl` has `"tool": "Bash"`. `Read`, `Glob`, `Grep`, and `LS` calls are **invisible**. So the preserved transcript — which shows no inbox listing in turn 3 — cannot support any claim about whether the worker looked at its inbox. It only shows the worker didn't use *Bash* to do so. Do not let anyone reason from that silence.

**The grade is a union across all replies.** `grades.grade_tokens` computes `echoed = set().union(*(tokens_in(reply) for reply in replies))` over the whole outbox, and `assert_tokens` requires `expected - echoed` to be empty. So `B002` never checks that B's token was reported *in the right turn* — only that it appeared somewhere before teardown. That is the right leniency, but it means the brief tests strictly less than the C014 claim text ("re-reads its inbox at the start of every turn"). Combined with F2's premature teardown, `B002` is simultaneously **too lenient** (no turn attribution) and **too strict** (no time to emit a second reply). Worth stating plainly in the ticket so the rate isn't over-read.

---

## F10 — MINOR: The "preserve the evidence" constraint is unenforced — the directory is untracked

The ticket's constraint reads:

> **Preserve the existing evidence directory** … it is the only artifact of the original miss and … can't be regenerated by re-running the brief.

Correct on the merits — and I verified the no-oracle-path claim: `probe/lib/oracle.py:77` validates "one **T4 finding record**", and its envelope is built around `brief`/`claim` fields (lines 43–93, 231, 284–303). There is no `explore` intake. The spec is hand-authored and carries no oracle verdict, exactly as it says.

But `git status` reports:

```
?? work_organisation/probe/explore-lostdoorbell-c014/
```

**The directory is untracked.** A single `git clean -fd` destroys the only artifact the ticket declares irreplaceable — and `explore-20260808T170211424180Z-c002/` is in the same state. Meanwhile `README.md`'s front-matter says `commit: e8ec234`, implying a provenance that does not exist in the repository.

Two related hygiene notes: the script that produced this evidence was standalone and is **not in the repo**, so the run cannot be reproduced or its instrumentation audited. And all preserved file mtimes are identical (`19:20:37`) because the tree was copied — **only `bus.jsonl` ordering is usable as timing evidence.** Anyone re-deriving F1 from mtimes will get nothing.

**Required correction:** Make "commit the evidence directory" step 0, ahead of everything else. A constraint that says "preserve this" while the file lives outside version control is a wish, not a control.

---

## What actually holds up

To be fair to the ticket, several things are correct and verified:

- **The single-trial provenance is real.** `ledger.jsonl` has exactly one B002 entry: `{"brief":"B002", …,"trials":1,"passed":1,"rate":1.0,"outcome":"no-finding", …}`. `COVERAGE.md` does mark C014 covered on that basis. The ticket is right that this is thin evidence for a `Covered` verdict.
- **`B002.md` really does default to `trials: 10`**, and `run_brief` honours the brief's default when `--trials` is omitted (`count = brief.trials if trials is None else trials`). The instruction not to pass `--trials 1` is correct.
- **`TOK-5WRF` genuinely appears in no outbox file.** Confirmed by reading all three: `HANDSHAKE_READY`, `TOK-7CWQ`, `TOK-GNB9`. The observation is real; only its *interpretation* is wrong (F1).
- **The mechanical plumbing did behave as documented.** `write_lost_doorbell` (runner.py:89–100) uses exclusive `"x"` creation plus `fsync`, emits no `message_sent` event, and C correctly landed in `0004.md` because `0003` was taken. The bus shows `message_sent` at seq 2, 6, 10 and none for B. That part of the spec is accurate.
- **Insisting on measurement before the wording change is the right instinct.** Step 1-before-step-3 is correct sequencing. The problem is that the instrument is broken, not that the order is wrong.

---

## Required sequence before this ticket can run

1. **Step 0 (new):** `git add` and commit `work_organisation/probe/explore-lostdoorbell-c014/` (and `explore-…-c002/`). [F10]
2. **Correct the record:** strike "the turn completed normally, not truncated" from the ticket Overview and from `explore-lostdoorbell-c014/README.md` §1; reclassify the preserved trial as **inconclusive — teardown raced the turn**. [F1]
3. **Fix the harness:** add a `turn_end` wait after the final `_wait_for_reply` in `runner._lost_doorbell`/`_run_trial`, before `outbox_messages` is read. Two lines, using the existing `agentctl wait --until` predicate. Nothing downstream is interpretable without this. [F2]
4. **Delete the "not an `agentctl.py` bug" constraint** and evaluate the `doorbell_text` unread-count lever alongside the wording lever. [F7]
5. **Pre-register the decision rule and the real budget:** 20 SUTs per run at ~66 s each; 30 trials to rule out a 10 % drop rate; control aborts don't count against the cap. If only 10 trials are affordable, record the 25.9 % upper bound honestly instead of writing `Covered`. [F5, F6]
6. **If a wording change is still indicated:** edit `probe-worker.md` only, mandate **one reply listing N tokens** (never N replies), and leave `WORKER.md` untouched. If `WORKER.md` must change, add the `claims.jsonl` re-anchor step for C014 and the shifted ranges of C015–C018, and verify `stale: 0` before re-measuring. [F3, F4, F8]

The underlying question — *does a real worker honour the lost-doorbell guarantee?* — is a good and important one, and C014 deserves better than a one-trial `Covered`. But on the evidence as it stands, **nobody has yet observed a worker drop a message.** What has been observed is a worker being killed 0.8 seconds after calling `reply`, inside a window where it had twice previously kept working. Fix the instrument, then ask the question.
