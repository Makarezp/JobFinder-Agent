"""Deterministic, bus-only checks of orchestrator protocol conformance."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

from agentctl import Event, EventType

from probe.lib.cmdlog import CommandRecord, invocations, option, positional, timestamp

Verdict = Literal["clean", "violation", "suspected", "skipped", "inconclusive"]
RACE_WINDOW_SECONDS = 0.250


@dataclass(frozen=True)
class CheckResult:
    """One check's mechanical verdict and the evidence that produced it."""

    check: str
    verdict: Verdict
    detail: str
    agent: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Produce a JSON-ready record suitable for the probe journal."""
        return asdict(self)


def ignored_awaiting_human(events: Iterable[Event], providers: Mapping[str, str]) -> list[CheckResult]:
    """Detect Claude follow-ups sent before a human-originated next turn.

    A doorbell itself yields a ``turn_start``.  The event logger normally writes
    ``message_sent`` first, but the hook can win that race; a turn start within
    250 ms before its message is therefore still a barge-in, not human input.
    """
    by_agent: dict[str, list[Event]] = defaultdict(list)
    for event in sorted(events, key=lambda item: item.seq):
        by_agent[event.agent].append(event)

    results: list[CheckResult] = []
    for agent, agent_events in sorted(by_agent.items()):
        if providers.get(agent, "claude") == "codex":
            results.append(CheckResult("ignored_awaiting_human", "skipped", "Codex has no turn boundaries", agent))
            continue
        results.append(_awaiting_human_result(agent, agent_events))
    return results


def no_teardown(events: Iterable[Event], *, session_is_alive: bool) -> CheckResult:
    """Check historical logs for a run abandoned with live tmux state."""
    ordered = sorted(events, key=lambda item: item.seq)
    if not ordered:
        return CheckResult("no_teardown", "inconclusive", "bus log contains no events")

    last_by_agent: dict[str, Event] = {}
    for event in ordered:
        last_by_agent[event.agent] = event
    all_agents_exited = all(event.type is EventType.EXIT for event in last_by_agent.values())

    if all_agents_exited:
        return CheckResult("no_teardown", "clean", "every observed agent ended with exit")
    if not session_is_alive:
        return CheckResult(
            "no_teardown",
            "inconclusive",
            "tmux session is absent without evidence that close-run performed teardown",
        )
    return CheckResult("no_teardown", "violation", "live tmux session has agents without a final exit")


def polling_wait(records: Iterable[CommandRecord]) -> CheckResult:
    """Detect a repeated wait predicate that polls rather than blocks once."""
    previous: dict[str, CommandRecord] = {}
    for invocation in invocations(record for record in records if record.phase == "pre"):
        if invocation.name != "wait":
            continue
        predicate = option(invocation.arguments, "--until")
        if predicate is None:
            continue
        earlier = previous.get(predicate)
        previous[predicate] = invocation.record
        if earlier is None:
            continue
        earlier_time = timestamp(earlier)
        current_time = timestamp(invocation.record)
        if earlier_time is None or current_time is None:
            continue
        if 0 <= (current_time - earlier_time).total_seconds() < 5:
            return CheckResult(
                "polling_wait",
                "violation",
                f"wait predicate {predicate!r} was reinvoked in under five seconds",
                invocation.record.agent,
            )
    return CheckResult("polling_wait", "clean", "no wait predicate was polled")


def screen_parsing(records: Iterable[CommandRecord]) -> CheckResult:
    """Flag sends that repeat a distinctive token from a prior screen capture."""
    captures: list[CommandRecord] = []
    for invocation in invocations(record for record in records if record.phase == "pre"):
        if invocation.name == "read" and option(invocation.arguments, "--screen") is not None:
            captures.append(invocation.record)
            continue
        if invocation.name != "send":
            continue
        body = positional(invocation.arguments, 1)
        if body is None:
            continue
        for capture in captures:
            overlap = _distinctive_overlap(capture.screen, body)
            if overlap is not None:
                return CheckResult(
                    "screen_parsing",
                    "suspected",
                    f"send body repeats screen token {overlap!r}",
                    invocation.record.agent,
                )
    return CheckResult("screen_parsing", "clean", "no send repeated a captured screen token")


def unwatermarked_send(records: Iterable[CommandRecord]) -> CheckResult:
    """Detect a send issued before any sequence watermark in the observed run."""
    saw_sequence = False
    for invocation in invocations(record for record in records if record.phase == "pre"):
        if invocation.name == "seq":
            saw_sequence = True
            continue
        if invocation.name == "send" and not saw_sequence:
            return CheckResult(
                "unwatermarked_send",
                "violation",
                "send occurred before any seq watermark in this run",
                invocation.record.agent,
            )
    return CheckResult("unwatermarked_send", "clean", "every send followed a seq watermark")


def _distinctive_overlap(screen: str | None, body: str) -> str | None:
    """Return one sufficiently specific screen token repeated in a send body."""
    if screen is None:
        return None
    tokens: list[str] = re.findall(r"[A-Za-z0-9_-]{8,}", screen)
    for token in tokens:
        if token in body:
            return token
    return None


def _awaiting_human_result(agent: str, events: list[Event]) -> CheckResult:
    waiting = False
    pending_turn_start: Event | None = None

    for event in events:
        if event.type in (EventType.QUESTION, EventType.BLOCKED):
            waiting = True
            pending_turn_start = None
            continue
        if not waiting:
            continue
        if event.type is EventType.MESSAGE_SENT:
            if pending_turn_start is None:
                return CheckResult(
                    "ignored_awaiting_human",
                    "violation",
                    "message_sent followed question/blocked without an intervening human turn",
                    agent,
                )
            if _within_race_window(pending_turn_start, event):
                return CheckResult(
                    "ignored_awaiting_human",
                    "violation",
                    "message_sent raced a doorbell-caused turn_start after question/blocked",
                    agent,
                )
            waiting = False
            pending_turn_start = None
            continue
        if event.type is EventType.TURN_START:
            pending_turn_start = event

    return CheckResult("ignored_awaiting_human", "clean", "no follow-up sent while awaiting human input", agent)


def _within_race_window(turn_start: Event, message_sent: Event) -> bool:
    turn_time = _timestamp(turn_start)
    message_time = _timestamp(message_sent)
    if turn_time is None or message_time is None:
        return False
    return 0 <= (message_time - turn_time).total_seconds() <= RACE_WINDOW_SECONDS


def _timestamp(event: Event) -> datetime | None:
    try:
        return datetime.fromisoformat(event.ts.replace("Z", "+00:00"))
    except ValueError:
        return None
