"""Regression coverage for T5a's bus-only checks and fluency counters."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Literal

from agentctl import Event, EventType, RunPaths
from probe.lib.cmdlog import CommandRecord
from probe.lib.fluency import measure, measure_cmdlog
from probe.lib.ground import events, provider
from probe.lib.orchestrator_checks import (
    ignored_awaiting_human,
    no_teardown,
    polling_wait,
    screen_parsing,
    unwatermarked_send,
)


def _event(seq: int, event_type: EventType, second: float, agent: str = "worker") -> Event:
    return Event(
        ts=f"2026-08-08T12:00:{second:06.3f}Z",
        run="fixture-run",
        agent=agent,
        type=event_type,
        seq=seq,
        data={},
    )


def _command(
    second: float,
    command: str,
    *,
    screen: str | None = None,
    phase: Literal["pre", "post"] = "pre",
    response: str | None = None,
) -> CommandRecord:
    return CommandRecord(
        ts=f"2026-08-08T12:00:{second:06.3f}Z",
        command=command,
        agent="orchestrator",
        run="fixture-run",
        phase=phase,
        screen=screen,
        response=response,
    )


def test_ignored_awaiting_human_detects_a_follow_up_without_human_turn() -> None:
    results = ignored_awaiting_human(
        [_event(1, EventType.QUESTION, 0), _event(2, EventType.MESSAGE_SENT, 1)],
        {"worker": "claude"},
    )

    assert results[0].verdict == "violation"


def test_ignored_awaiting_human_accepts_a_human_turn_before_follow_up() -> None:
    results = ignored_awaiting_human(
        [
            _event(1, EventType.QUESTION, 0),
            _event(2, EventType.TURN_START, 1),
            _event(3, EventType.MESSAGE_SENT, 2),
        ],
        {"worker": "claude"},
    )

    assert results[0].verdict == "clean"


def test_ignored_awaiting_human_handles_the_message_turn_race() -> None:
    results = ignored_awaiting_human(
        [
            _event(1, EventType.BLOCKED, 0),
            _event(2, EventType.TURN_START, 1),
            _event(3, EventType.MESSAGE_SENT, 1.080),
        ],
        {"worker": "claude"},
    )

    assert results[0].verdict == "violation"


def test_ignored_awaiting_human_skips_codex_without_turn_boundaries() -> None:
    results = ignored_awaiting_human(
        [_event(1, EventType.QUESTION, 0), _event(2, EventType.MESSAGE_SENT, 1)],
        {"worker": "codex"},
    )

    assert results[0].verdict == "skipped"


def test_no_teardown_requires_a_live_session_and_missing_exit() -> None:
    stranded = [_event(1, EventType.SPAWNED, 0), _event(2, EventType.TURN_END, 1)]

    assert no_teardown(stranded, session_is_alive=True).verdict == "violation"
    assert no_teardown(stranded, session_is_alive=False).verdict == "inconclusive"
    assert no_teardown([_event(1, EventType.EXIT, 1)], session_is_alive=True).verdict == "clean"


def test_question_rate_counts_question_and_blocked_events() -> None:
    fluency = measure(
        [
            _event(1, EventType.MESSAGE_SENT, 0),
            _event(2, EventType.QUESTION, 1),
            _event(3, EventType.MESSAGE_SENT, 2),
            _event(4, EventType.BLOCKED, 3),
        ]
    )

    assert fluency.question_rate == 1.0


def test_fluency_handles_agents_with_no_messages() -> None:
    assert measure([_event(1, EventType.EXIT, 0)]).turns_per_task == {"worker": ()}


def test_cmdlog_checks_detect_and_reject_near_misses() -> None:
    wait = "python /tool/agentctl.py wait --until agent=worker,type=reply"
    assert polling_wait([_command(0, wait), _command(4.9, wait)]).verdict == "violation"
    assert polling_wait([_command(0, wait), _command(30, wait)]).verdict == "clean"

    read = "python /tool/agentctl.py read worker --screen 8"
    send = "python /tool/agentctl.py send worker 'TOKEN-ABC-123 copied'"
    unrelated = "python /tool/agentctl.py send worker 'begin the next task'"
    assert screen_parsing([_command(0, read, screen="TOKEN-ABC-123"), _command(1, send)]).verdict == "suspected"
    assert screen_parsing([_command(0, read, screen="TOKEN-ABC-123"), _command(1, unrelated)]).verdict == "clean"

    bare_send = "python /tool/agentctl.py send worker message"
    watermark = "python /tool/agentctl.py seq"
    assert unwatermarked_send([_command(0, bare_send)]).verdict == "violation"
    assert unwatermarked_send([_command(0, watermark), _command(1, bare_send)]).verdict == "clean"


def test_cmdlog_fluency_uses_post_tool_send_outcomes() -> None:
    send = "python /tool/agentctl.py send worker message"
    records = [
        _command(0, "python /tool/agentctl.py seq"),
        _command(1, send),
        _command(2, send, phase="post", response='{"stdout":"sent\\t/path"}'),
    ]

    fluency = measure_cmdlog([_event(1, EventType.TURN_START, 0)], records)

    assert fluency.doorbell_efficiency == {"delivered": 1, "queued": 0, "forced": 0}
    assert fluency.orchestrator_overhead == 2.0


def test_ground_reader_parses_bus_without_agentctl_read_path(tmp_path: Path) -> None:
    paths = RunPaths.build(tmp_path, "fixture-run")
    paths.root.mkdir(parents=True)
    paths.bus.write_text(
        json.dumps(
            {
                "ts": "2026-08-08T12:00:00.000Z",
                "run": "fixture-run",
                "agent": "worker",
                "type": "future_event",
                "seq": 1,
                "data": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    paths.meta("worker").parent.mkdir(parents=True)
    paths.meta("worker").write_text('{"provider":"codex"}\n', encoding="utf-8")

    parsed = events(paths)

    assert parsed[0].type is EventType.UNKNOWN
    assert parsed[0].raw_type == "future_event"
    assert provider(paths, "worker") == "codex"


def test_checks_exit_two_without_a_command_log(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "probe" / "probe.py"),
            "checks",
            "--runtime",
            str(tmp_path),
            "--run",
            "fixture-run",
        ],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 2
