"""Ungraded fluency counters derived from bus and Route A command logs."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from agentctl import Event, EventType

from probe.lib.cmdlog import CommandRecord, Invocation, invocations


@dataclass(frozen=True)
class Fluency:
    """Ungraded measures for comparing later orchestrator runs."""

    turns_per_task: dict[str, tuple[int, ...]]
    question_rate: float | None
    time_to_first_action: dict[str, float]
    dead_air: dict[str, float]


@dataclass(frozen=True)
class CmdlogFluency:
    """Ungraded measures that require Route A command observations."""

    doorbell_efficiency: dict[str, int] | None
    orchestrator_overhead: float | None


def measure(events: Iterable[Event]) -> Fluency:
    """Derive the four T5a counters directly from the event stream."""
    ordered = sorted(events, key=lambda event: event.seq)
    return Fluency(
        turns_per_task=_turns_per_task(ordered),
        question_rate=_question_rate(ordered),
        time_to_first_action=_time_to_first_action(ordered),
        dead_air=_dead_air(ordered),
    )


def measure_cmdlog(events: Iterable[Event], records: Iterable[CommandRecord]) -> CmdlogFluency:
    """Derive command-dependent counters without inventing pass/fail thresholds."""
    record_list = list(records)
    responses: dict[str, deque[str | None]] = defaultdict(deque)
    for record in record_list:
        if record.phase == "post":
            responses[record.command].append(record.response)
    sends = [invocation for invocation in invocations(record_list) if invocation.record.phase == "pre" and invocation.name == "send"]
    send_responses = [responses[invocation.record.command].popleft() if responses[invocation.record.command] else None for invocation in sends]
    efficiency = _doorbell_efficiency(sends, send_responses)
    turns = sum(event.type is EventType.TURN_START for event in events)
    calls = len(invocations(record for record in record_list if record.phase == "pre"))
    return CmdlogFluency(
        doorbell_efficiency=efficiency,
        orchestrator_overhead=calls / turns if turns else None,
    )


def _doorbell_efficiency(
    sends: list[Invocation],
    responses: list[str | None],
) -> dict[str, int] | None:
    """Count the exact ``send`` outcomes exposed by PostToolUse stdout."""
    outcomes = [_send_outcome(response) for response in responses]
    if any(outcome is None for outcome in outcomes):
        return None
    return {
        "delivered": sum(outcome == "sent" for outcome in outcomes),
        "queued": sum(outcome == "queued" for outcome in outcomes),
        "forced": sum("--force" in invocation.arguments for invocation in sends),
    }


def _send_outcome(response: str | None) -> str | None:
    """Decode agentctl's mutually exclusive ``sent`` or ``queued`` stdout."""
    if response is None:
        return None
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        return None
    stdout = payload.get("stdout") if isinstance(payload, dict) else None
    if not isinstance(stdout, str):
        return None
    if stdout.startswith("sent\t"):
        return "sent"
    if stdout.startswith("queued\t"):
        return "queued"
    return None


def _turns_per_task(events: list[Event]) -> dict[str, tuple[int, ...]]:
    by_agent: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        by_agent[event.agent].append(event)

    counts: dict[str, tuple[int, ...]] = {}
    for agent, agent_events in by_agent.items():
        task_starts = [index for index, event in enumerate(agent_events) if event.type is EventType.MESSAGE_SENT]
        ends = [*task_starts[1:], len(agent_events)] if task_starts else []
        values = tuple(
            sum(event.type is EventType.TURN_END for event in agent_events[start:next_start])
            for start, next_start in zip(task_starts, ends, strict=True)
        )
        counts[agent] = values
    return counts


def _question_rate(events: list[Event]) -> float | None:
    task_count = sum(event.type is EventType.MESSAGE_SENT for event in events)
    if task_count == 0:
        return None
    human_handoffs = sum(event.type in (EventType.QUESTION, EventType.BLOCKED) for event in events)
    return human_handoffs / task_count


def _time_to_first_action(events: list[Event]) -> dict[str, float]:
    spawned: dict[str, Event] = {}
    values: dict[str, float] = {}
    for event in events:
        if event.type is EventType.SPAWNED and event.agent not in spawned:
            spawned[event.agent] = event
        if event.type is EventType.TURN_START and event.agent in spawned and event.agent not in values:
            duration = _duration(spawned[event.agent], event)
            if duration is not None:
                values[event.agent] = duration
    return values


def _dead_air(events: list[Event]) -> dict[str, float]:
    starts: dict[str, Event] = {}
    values: dict[str, float] = {}
    for event in events:
        if event.type is EventType.TURN_START:
            starts[event.agent] = event
        elif event.type is EventType.TURN_END and event.agent in starts:
            duration = _duration(starts[event.agent], event)
            if duration is not None:
                values[event.agent] = max(values.get(event.agent, 0.0), duration)
            del starts[event.agent]
    return values


def _duration(start: Event, end: Event) -> float | None:
    try:
        start_time = datetime.fromisoformat(start.ts.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(end.ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (end_time - start_time).total_seconds())
