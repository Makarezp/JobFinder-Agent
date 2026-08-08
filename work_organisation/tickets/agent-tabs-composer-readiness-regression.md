# Agent-Tabs — Composer Readiness Regression (T0)

**Sprint:** `sprint_v3_agent_tabs_hardening.md`
**Priority:** BLOCKING — `agentctl send` is broken against the installed Claude Code today.
**Found by:** the `probe-spike` investigation, 2026-08-08. Every claim below was verified against source at `1bb37a7` and against a live worker.

## Overview

`agentctl`'s only rendering-dependent code path has drifted out of sync with Claude Code's TUI. Two coupled defects: the composer gate now misreads an **idle** agent as one with pending human text, blocking every `send`; and screen captures of unattached panes come back blank, which both destroys `spawn`'s failure diagnostic and silently masks the first defect. This ticket fixes both and replaces the frozen-string test fixtures with a guard that cannot rot the same way.

## Evidence

**D1 — the gate misfires on idle agents.** `_input_row_looks_busy` (`agentctl.py:1563-1584`) returns `bool(stripped[len(COMPOSER_MARKER):].strip())` — any text after `❯` means "human is typing." Claude Code **2.1.226** renders contextual *placeholders* in that row. Its own docstring reads *"Verified against Claude Code v2.1.223."*

Three-line reproduction — no tmux, no spawn, no model call:

```python
sys.path.insert(0, ".agent/skills/agent-tabs"); import agentctl as m
m._input_row_looks_busy("❯ check your inbox")   # -> True   IDLE agent, placeholder
m._input_row_looks_busy("❯ half a sentence")    # -> True   human genuinely typing
m._input_row_looks_busy("❯ ")                   # -> False
```

The first string was captured verbatim from a healthy idle v2.1.226 worker. The first two are indistinguishable to the gate.

Consequence: `Readiness(False, "human_typing")` → **every `send` exits 3 and never rings the doorbell.** Observed: 19 unheard messages accumulated in one subject's inbox while the agent sat idle. Independently confirmed that the placeholder is not real text — typing `ZZZ` *replaced* it, and 40 BSpace keys did not remove it.

`spawn` is unaffected: `_bootstrap` calls `_deliver` directly (`:1486`), bypassing the readiness gates.

**D2 — captures of unattached panes are blank or stale.** tmux panes in an unattached session repaint only on resize. A real spawn failure produced a `Last screen:` diagnostic of **40 blank lines** — the single diagnostic `agentctl` offers on a failed spawn, useless in the failure it exists for.

**They interact, which is why this is one ticket.** A blank capture finds no `❯` marker, so `_input_row_looks_busy` takes its `log.debug` path and returns `False` — failing open:

| Pane | Capture | `send` |
|---|---|---|
| attached (a human is watching) | placeholder renders | **blocked**, exits 3 |
| detached | blank | succeeds, for the wrong reason |

**`send` behaves differently depending on whether a human is watching the window.** Fixing D2 alone would unmask D1 everywhere; fixing D1 alone leaves the diagnostic blind.

**Why the suite missed it.** `tests/test_send.py:76-90` asserts against hand-written `EMPTY_COMPOSER` / `TYPED_COMPOSER` constants frozen at v2.1.223. The fixtures encode the old TUI, so they pass while reality diverges. **New fixtures are not the fix** — a frozen string cannot detect that the thing it models has changed.

## Implementation Steps

1. **Step 0 — spike: find a discriminator that is not the text itself.** A placeholder and typed text differ in *rendering*, not content, so no string comparison can separate them robustly. Investigate, in order:
   - **`tmux capture-pane -e`** (preserve escape sequences). Placeholders are rendered dim/faint; typed text is not. If the SGR attributes differ reliably, that is the discriminator, and it is content-independent — it survives future placeholder wording changes. **This is the preferred outcome; confirm or refute it before writing code.**
   - **Cursor position.** `tmux display-message -p '#{cursor_x}'` on the composer row: a placeholder does not advance the cursor, typed text does.
   - **Known-placeholder list** — last resort. Brittle, needs updating per Claude Code release, and reintroduces the rot this ticket exists to remove. If it is the only option, say so explicitly in the code comment.

   Record the outcome as a docstring on the repaired function.

2. **Fix D1 in `_input_row_looks_busy` (`agentctl.py:1563-1584`).** Keep the function's existing contract: one place in the tool that reads rendering, failing **open** when uncertain. The existing reasoning still holds and is worth preserving — a missed detection garbles one line the human is typing, and the instruction is already safe in the inbox; failing closed deadlocks every workflow. **The current behaviour is failing closed by accident, which is exactly what the docstring warned against.**

3. **Fix D2 in the backend capture path.** Force a repaint before capturing an unattached pane (`tmux refresh-client`, or a resize round-trip), **or** — if no reliable repaint exists — have `capture()` return a value that marks the content as untrusted, so callers cannot assert on it. A blank string that looks like a valid empty screen is the failure mode to eliminate.

4. **Fix the diagnostic.** `spawn`'s `SpawnError` messages embed `backend.capture(handle, 40)` (`:1478`, `:1475`). When the capture is untrusted or empty, say so — *"screen capture unavailable (unattached pane)"* — rather than printing 40 blank lines under a `Last screen:` header, which reads as "the agent's screen was healthy and empty."

5. **Replace the frozen fixtures with a liveness guard — `tests/test_send.py`.**
   Keep the existing unit cases, and add a test marked with the `needs_tmux` skipif idiom (`tests/test_backend.py:25-26`; **there is no `tmux` pytest marker** — the root `pyproject.toml` registers only `integration`) that:
   - spawns a real worker, waits for idle, captures its **actual** composer row, and asserts the gate reports it as free;
   - types real text into the pane and asserts the gate now reports it as busy.

   This is the only test in the file that cannot silently rot when the TUI changes, and its comment must say so.

## Explicit Constraints & Warnings

- **Do not "fix" this by making the gate stricter.** The cost asymmetry is settled and documented: a false negative garbles one line of human typing and the instruction is still safe in the inbox; a false positive stops all delivery. Fail open.
- **Do not delete the existing string-fixture tests.** They are fast and they pin the parsing logic. They are simply not sufficient, and step 5 is what makes them so.
- **Do not widen `--wait-idle` or add retries to paper over D1.** A gate that is wrong does not become right with more attempts.
- **`spawn` must keep working throughout.** It bypasses these gates via `_bootstrap`; a change that routes bootstrap through the readiness path would convert this bug into a total outage.
- **This is a change to the subject under test.** Land it before T2 — T2's `dirty-composer` acceptance criteria assert against the very gate this repairs, and are unbuildable until it works.
- Validate with `AGENTCTL_PYTHON="$PWD/.venv/bin/python" .agent/skills/agent-tabs/test.sh`. A bare `./test.sh` **silently skips** ruff, mypy and pytest. Baseline at `1bb37a7`: **187 passed, 2 skipped, ruff clean, mypy clean over 11 source files.**

## Acceptance Criteria

- [Automated] `_input_row_looks_busy` (or its replacement) returns `False` for a composer row containing a placeholder captured verbatim from the installed Claude Code, and `True` for the same row containing genuinely typed text. Both strings live in the test, and the test names the version they were captured from.
- [Automated] A `needs_tmux` test spawns a real worker, waits for idle, and asserts `send` **delivers** — exit `0`, a `message_sent` event on the bus, and the doorbell visible on screen. This is the regression guard for the live defect: it fails today.
- [Automated] A test asserts `capture()` on an unattached pane either returns real content or is flagged untrusted — and that a `SpawnError` built from an untrusted capture does **not** render as `Last screen:` followed by blank lines.
- [Automated] The existing `test_send.py` string cases still pass unmodified.
- [Manual] Spawn an agent, let it go idle, and `agentctl send` it a message with no human text in the composer. The message arrives and the agent acts on it. Today this exits `3` and the message sits unread.
- [Manual] Type half a line into that agent's composer and `send` again. It exits `3` and queues — the gate still protects genuine human input.
