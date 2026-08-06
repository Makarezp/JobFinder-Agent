"""The predicate tail: BusTail, the grammar, and the `wait` command."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import agentctl
import pytest


def _paths(tmp_path: Path) -> agentctl.RunPaths:
    return agentctl.RunPaths.build(tmp_path / "rt", "cvv")


def _append_later(paths: agentctl.RunPaths, agent: str, event_type: agentctl.EventType, delay: float) -> threading.Thread:
    def run() -> None:
        time.sleep(delay)
        agentctl.append_event(paths, agent, event_type)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# BusTail
# ---------------------------------------------------------------------------


def test_tail_yields_each_event_exactly_once(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    tail = agentctl.BusTail(paths.bus)
    seen: list[int] = []

    for _ in range(50):
        agentctl.append_event(paths, "critic", agentctl.EventType.TURN_END)
        seen.extend(event.seq for event in tail.poll())

    assert seen == list(range(1, 51))
    assert tail.poll() == []


def test_tail_on_a_missing_log_is_empty(tmp_path: Path) -> None:
    assert agentctl.BusTail(_paths(tmp_path).bus).poll() == []


def test_tail_does_not_consume_a_partial_final_line(tmp_path: Path) -> None:
    """A reader can observe the file mid-append; a half-written record must wait."""
    paths = _paths(tmp_path)
    agentctl.append_event(paths, "critic", agentctl.EventType.SPAWNED)
    tail = agentctl.BusTail(paths.bus)
    assert [event.seq for event in tail.poll()] == [1]

    partial = '{"ts":"2026-01-01T00:00:00.000Z","run":"cvv","agent":"critic","type":"turn_st'
    with paths.bus.open("a", encoding="utf-8") as handle:
        handle.write(partial)
    assert tail.poll() == []

    with paths.bus.open("a", encoding="utf-8") as handle:
        handle.write('art","seq":2,"data":{}}\n')
    assert [event.seq for event in tail.poll()] == [2]


def test_tail_resets_when_the_log_is_recreated(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    agentctl.append_event(paths, "critic", agentctl.EventType.SPAWNED)
    agentctl.append_event(paths, "critic", agentctl.EventType.TURN_START)
    tail = agentctl.BusTail(paths.bus)
    assert len(tail.poll()) == 2

    paths.bus.unlink()
    agentctl.append_event(paths, "critic", agentctl.EventType.SPAWNED)

    assert [event.seq for event in tail.poll()] == [1]


# ---------------------------------------------------------------------------
# Predicate grammar
# ---------------------------------------------------------------------------


def _event(agent: str, event_type: agentctl.EventType, seq: int = 1) -> agentctl.Event:
    return agentctl.Event(ts=agentctl.utc_now(), run="cvv", agent=agent, type=event_type, seq=seq, data={})


def test_conjunction_requires_every_clause() -> None:
    predicate = agentctl.parse_predicate("agent=critic,type=reply")

    assert predicate.matches(_event("critic", agentctl.EventType.REPLY)) is True
    assert predicate.matches(_event("writer", agentctl.EventType.REPLY)) is False
    assert predicate.matches(_event("critic", agentctl.EventType.TURN_END)) is False


def test_alternation_matches_any_listed_value() -> None:
    predicate = agentctl.parse_predicate("type=question|blocked")

    assert predicate.matches(_event("critic", agentctl.EventType.QUESTION)) is True
    assert predicate.matches(_event("critic", agentctl.EventType.BLOCKED)) is True
    assert predicate.matches(_event("critic", agentctl.EventType.REPLY)) is False


def test_agent_only_predicate_matches_any_type() -> None:
    predicate = agentctl.parse_predicate("agent=critic")
    assert predicate.matches(_event("critic", agentctl.EventType.TURN_START)) is True


def test_status_key_is_rejected_with_a_pointer_to_type() -> None:
    """Silently matching nothing is the worst outcome for a blocking call."""
    with pytest.raises(agentctl.BusError, match="use type=reply"):
        agentctl.parse_predicate("status=question")


def test_unknown_key_names_the_valid_ones() -> None:
    with pytest.raises(agentctl.BusError, match="valid keys: agent, type"):
        agentctl.parse_predicate("colour=blue")


def test_malformed_and_empty_predicates_are_rejected() -> None:
    with pytest.raises(agentctl.BusError, match="expected key=value"):
        agentctl.parse_predicate("agent")
    with pytest.raises(agentctl.BusError, match="must constrain at least one"):
        agentctl.parse_predicate("")


# ---------------------------------------------------------------------------
# wait
# ---------------------------------------------------------------------------


def test_wait_returns_the_matching_event(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = _paths(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    _append_later(paths, "critic", agentctl.EventType.REPLY, delay=0.3)

    argv = ["--runtime", str(paths.runtime_root), "--run", "cvv", "wait", "--until", "agent=critic,type=reply", "--timeout", "10"]
    assert agentctl.main(argv) == 0

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["agent"] == "critic"
    assert payload["type"] == "reply"


def test_wait_times_out_with_exit_two_and_no_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = _paths(tmp_path)
    argv = ["--runtime", str(paths.runtime_root), "--run", "cvv", "wait", "--until", "type=reply", "--timeout", "0.5"]

    assert agentctl.main(argv) == agentctl.EXIT_TIMEOUT
    assert capsys.readouterr().out == ""


def test_pre_existing_events_do_not_satisfy_a_default_wait(tmp_path: Path) -> None:
    """Matching history would return instantly and look exactly like success."""
    paths = _paths(tmp_path)
    agentctl.append_event(paths, "critic", agentctl.EventType.REPLY)

    argv = ["--runtime", str(paths.runtime_root), "--run", "cvv", "wait", "--until", "type=reply", "--timeout", "0.5"]
    assert agentctl.main(argv) == agentctl.EXIT_TIMEOUT


def test_explicit_from_seq_can_replay_history(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = _paths(tmp_path)
    agentctl.append_event(paths, "critic", agentctl.EventType.REPLY)

    argv = ["--runtime", str(paths.runtime_root), "--run", "cvv", "wait", "--until", "type=reply", "--from-seq", "0", "--timeout", "5"]
    assert agentctl.main(argv) == 0
    assert json.loads(capsys.readouterr().out.strip())["seq"] == 1


def test_wait_rejects_a_bad_predicate_with_exit_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = _paths(tmp_path)
    argv = ["--runtime", str(paths.runtime_root), "--run", "cvv", "wait", "--until", "status=reply", "--timeout", "1"]

    assert agentctl.main(argv) == 1
    assert "use type=reply" in capsys.readouterr().err


def test_watermark_closes_the_gap_between_send_and_wait(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """seq is captured before sending, so a fast reply cannot slip through."""
    paths = _paths(tmp_path)
    agentctl.append_event(paths, "critic", agentctl.EventType.SPAWNED)
    watermark = agentctl.max_seq(paths)
    agentctl.append_event(paths, "critic", agentctl.EventType.REPLY)

    argv = [
        "--runtime",
        str(paths.runtime_root),
        "--run",
        "cvv",
        "wait",
        "--until",
        "type=reply",
        "--from-seq",
        str(watermark),
        "--timeout",
        "5",
    ]
    assert agentctl.main(argv) == 0
    assert json.loads(capsys.readouterr().out.strip())["seq"] == 2


def test_wait_for_event_wrapper_still_works(tmp_path: Path) -> None:
    """spawn depends on this typed wrapper; it now shares the tail implementation."""
    paths = _paths(tmp_path)
    _append_later(paths, "critic", agentctl.EventType.SPAWNED, delay=0.2)

    event = agentctl.wait_for_event(paths, agent="critic", types=[agentctl.EventType.SPAWNED], timeout=10)

    assert event is not None
    assert event.type is agentctl.EventType.SPAWNED


def test_unknown_event_types_are_matchable_by_their_raw_name(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.bus.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00.000Z", "run": "cvv", "agent": "critic", "type": "future_thing", "seq": 1, "data": {}}) + "\n",
        encoding="utf-8",
    )

    event = agentctl.wait_for_match(paths, agentctl.parse_predicate("type=future_thing"), timeout=2)

    assert event is not None
    assert event.raw_type == "future_thing"
