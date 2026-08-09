---
status: open
component: agent-tabs / agentctl.py / TmuxBackend.send, send_message, is_ready
discovered: 2026-08-08
discovered_via: live usage — two separate `agentctl send` calls this session left the doorbell pointer typed but unsubmitted
severity: high — silently stalls an agent indefinitely with no error, no bus signal, and no automatic recovery
root_cause: not established — see Section 4, candidate hypotheses only
---

# `send_message`'s text-then-Enter delivery can leave the message typed but unsubmitted, with no signal that it happened

## 1. Summary

Delivering an instruction to an agent (`agentctl send`, and the same primitive used internally by the bootstrap/doorbell path) does two things in sequence via `TmuxBackend.send()` (`agentctl.py:793-798`):

```python
self._tmux("send-keys", "-t", handle, "-l", "--", text)
if enter:
    self._tmux("send-keys", "-t", handle, "Enter")
```

Twice in this session, on two different agents (`impl-006` and `impl-007`, both real Claude Code sonnet workers in run `ticket-impl`), this sequence completed without error — `MESSAGE_SENT` was appended to the bus both times — but the **Enter keystroke did not register as submit** in the worker's TUI. The pointer text (`[orchestrator] new instruction: <inbox path>`) was visibly typed into the composer and sat there, unsubmitted, until a human/orchestrator manually sent an additional `tmux send-keys -t <handle> Enter`.

In the `impl-007` case, the gap between the recorded `message_sent` bus event and the agent's next `turn_start` was **over 10 minutes** — the message sat stuck until discovered and manually fixed, not a fleeting one-frame race that resolved itself.

## 2. Why this is worse than a normal "lost doorbell"

The framework's whole `WORKER.md` design explicitly tolerates a lost/garbled doorbell **keystroke** (that's what `C014`/`TICKET-007` is about): the payload is already durably on disk in the inbox before any terminal interaction happens, so a dropped keystroke is supposed to cost nothing, because the worker re-reads its inbox at the start of every turn regardless.

This bug is a different, worse failure mode: the keystrokes were **not** dropped or garbled — the pointer text landed correctly, character-for-character, and `_deliver()` recorded success (`MESSAGE_SENT`) on the bus. The problem is that Enter specifically failed to trigger the TUI's submit handler, and — critically — because the agent was never told to start a new turn, it also never re-read its inbox on its own; nothing in the protocol causes a self-recovery here the way a genuinely-lost keystroke's "read the inbox next turn anyway" guarantee does. The agent is not idle waiting for something else, and it is not `busy` — it is invisibly stuck, indistinguishable from "still thinking" unless someone actually looks at the pane content, not just the derived bus state.

## 3. Observed pattern both times

Both incidents happened on a `send` that followed shortly after the target agent's *previous* turn had just ended (a fresh `turn_end`/reply had just landed, and the human's next instruction was sent in response). Both times:

1. `send_message`'s `await_ready` correctly waited for `is_ready` to report ready (state in `SENDABLE_STATES`, not in copy-mode, composer not already holding unsent text).
2. `_deliver()` ran, both `send-keys` calls (text, then Enter) succeeded (no exception, no error event).
3. The pane showed the pointer text sitting in the composer with no error, no busy indicator — just idle, unsubmitted.
4. Nothing self-corrected. The agent stayed in this state until manually noticed and fixed with an out-of-band `tmux send-keys ... Enter`.

## 4. Candidate hypotheses (none confirmed — flagged for investigation, not assumed)

- **TUI-side settle delay after a busy→idle transition.** Claude Code's composer may not be immediately ready to treat Enter as "submit" the instant its own state flips from busy to idle (e.g., a final re-render frame after printing its turn summary), even though character insertion into the composer works immediately. `is_ready`'s gates are all event-/render-based snapshots at one instant; there is no settle/debounce delay built into `send_message` between confirming readiness and typing.
- **Two separate `send-keys` subprocess calls, no atomicity.** The text and the Enter are two independent `tmux send-keys` invocations with no guarantee about exact timing or that the TUI treats them as one logical action. If the TUI's input handling has any notion of "coalesce rapid input, don't submit until a brief idle gap" (common in some terminal UI frameworks to distinguish a paste from a real Enter-terminated line), a same-burst Enter sent as a distinct call could be swallowed or reinterpreted as inserting a literal newline into a still-open multi-line compose rather than submitting.
- **`-l` (literal) send bypassing whatever the TUI needs to recognize "this is a real user pressing Enter."** `send-keys -l` sends raw bytes with no bracketed-paste framing. If the TUI infers "human is typing" vs. "this is bulk/pasted input" from framing it doesn't see here, its Enter-handling state machine could end up in a mode where Enter doesn't mean submit at that moment.

None of these is verified against the actual TUI internals; they are offered only as starting points for whoever investigates.

## 5. Practical impact

Any orchestration that sends a follow-up instruction to a headless-managed agent (no human watching the tab in real time) can silently stall indefinitely with zero signal — no error event, no stalled-state bus record (this isn't the same as the existing `STALLED: mid-turn` detection, since that only fires once a turn has actually started; here no turn ever starts). The only way it was caught this session was a human noticing the agent hadn't progressed and asking about it.

## 6. Reproduction

Not yet reliably reproducible on demand — both observed instances happened during real usage, not a constructed test. A next step for whoever investigates: script repeated `agentctl send` calls immediately following a `turn_end` event (racing the send against the TUI's own post-turn settle time) against a real spawned worker, and check whether the composer ends up with unsubmitted text at some rate.

## 7. Suggested fix directions (not decided — for human review)

1. **Verify submission, not just that the keystrokes were sent.** After `_deliver()`'s two `send-keys` calls, capture the pane again and confirm the composer no longer shows the just-typed pointer text (i.e., verify the same way `_composer_looks_busy` already detects unsent text, but as a post-send assertion, not just a pre-send gate). If verification fails, retry the Enter (bounded retries) before giving up and surfacing an error.
2. **Add a short settle delay** between `await_ready` confirming readiness and `_deliver()` typing, specifically to absorb a possible post-turn-end TUI settle window, if hypothesis 1 in Section 4 is confirmed.
3. **Surface a distinct bus/error signal** when delivery cannot be confirmed, rather than only ever recording `MESSAGE_SENT` unconditionally once the two `send-keys` calls return without a subprocess error — right now "the tmux command didn't error" and "the message was actually submitted" are conflated into one event.

Option 1 is the most directly targeted at what was actually observed (text present, not submitted) and doesn't require confirming which of Section 4's hypotheses is correct first.

## 8. Constraints for whoever picks this up

- No changes have been made to `agentctl.py`. This document is purely descriptive.
- Any fix should preserve the existing invariant that the payload is written to the inbox *before* any terminal interaction (`send_message`'s docstring calls this out explicitly) — that part of the design is sound and orthogonal to this bug; the bug is specifically about the keystroke-delivery half, not the disk-write half.
