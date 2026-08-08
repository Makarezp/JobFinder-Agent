"""Regression coverage for the isolated probe substrate."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from agentctl import Event, EventType, RunPaths
from probe.lib import sut as sut_module
from probe.lib.assertions import (
    HarnessError,
    ProbeFailure,
    assert_event_absent,
    assert_event_count,
    assert_exit,
    assert_inbox_contains,
    assert_no_windows,
    assert_screen_lacks,
    assert_tokens,
)
from probe.lib.ground import events, inbox_files, outbox_messages, windows
from probe.lib.nonce import mint, tokens_in
from probe.lib.sut import Sut, create_sut, destroy_sut, spawn_command

HAS_TMUX = shutil.which("tmux") is not None
needs_tmux = pytest.mark.skipif(not HAS_TMUX, reason="requires a local tmux binary")


def _sut(tmp_path: Path) -> Sut:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    return Sut(runtime=runtime, run="fixture-run", agentctl=Path(__file__).resolve().parents[1] / "agentctl.py", env={})


def _event(sequence: int, event_type: EventType, *, agent: str = "worker") -> Event:
    return Event(ts="2026-08-08T00:00:00.000Z", run="fixture-run", agent=agent, type=event_type, seq=sequence, data={})


def test_create_sut_uses_spacey_trusted_isolated_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "claude.json"
    config_path.write_text('{"projects": {}}\n', encoding="utf-8")
    monkeypatch.setattr(sut_module, "CLAUDE_CONFIG_PATH", config_path)

    sut = create_sut("B001", spacey=True)

    assert re.search(r"[ ].*@|@.*[ ]", str(sut.runtime))
    assert sut.runtime != Path.home() / ".local" / "state" / "agent-tabs"
    assert sut.env["AGENT_TABS_RUNTIME"] == str(sut.runtime)
    assert sut.env["AGENT_TABS_RUN"] == sut.run
    assert sut.env["AGENT_TABS_VIEWER"] == "none"
    assert json.loads(config_path.read_text(encoding="utf-8"))["projects"][str(sut.runtime)]["hasTrustDialogAccepted"] is True

    assert destroy_sut(sut, preserve=False) is None
    assert not sut.runtime.exists()
    assert str(sut.runtime) not in json.loads(config_path.read_text(encoding="utf-8"))["projects"]


def test_destroy_sut_preserves_then_removes_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "claude.json"
    monkeypatch.setattr(sut_module, "CLAUDE_CONFIG_PATH", config_path)
    sut = create_sut("B002")

    assert destroy_sut(sut, preserve=True) == sut.runtime
    assert sut.runtime.is_dir()
    assert destroy_sut(sut, preserve=False) is None
    assert not sut.runtime.exists()


def test_spawn_command_enforces_probe_safety_flags(tmp_path: Path) -> None:
    sut = _sut(tmp_path)
    command = spawn_command(sut, "worker", tmp_path / "role.md", "do work", model="haiku")

    assert command[2:5] == ["spawn", "worker", "--role"]
    assert command[command.index("--runtime") + 1] == str(sut.runtime)
    assert command[command.index("--run") + 1] == sut.run
    assert command[command.index("--cwd") + 1] == str(sut.runtime)
    assert command[command.index("--permission-mode") + 1] == "bypassPermissions"
    assert command[command.index("--viewer") + 1] == "none"


def test_ground_events_preserve_unknown_types_and_filter(tmp_path: Path) -> None:
    sut = _sut(tmp_path)
    paths = RunPaths.build(sut.runtime, sut.run)
    paths.root.mkdir()
    paths.bus.write_text(
        "\n".join(
            [
                json.dumps({"ts": "x", "run": sut.run, "agent": "worker", "type": "spawned", "seq": 1, "data": {}}),
                json.dumps({"ts": "x", "run": sut.run, "agent": "worker", "type": "future_event_from_a_newer_version", "seq": 2, "data": {}}),
            ]
        ),
        encoding="utf-8",
    )

    parsed = events(sut)

    assert parsed[1].type is EventType.UNKNOWN
    assert parsed[1].raw_type == "future_event_from_a_newer_version"
    assert events(sut, type=EventType.SPAWNED) == [parsed[0]]


def test_ground_reads_inboxes_and_outboxes_directly(tmp_path: Path) -> None:
    sut = _sut(tmp_path)
    paths = RunPaths.build(sut.runtime, sut.run)
    paths.inbox("worker").mkdir(parents=True)
    paths.outbox("worker").mkdir(parents=True)
    (paths.inbox("worker") / "0001.md").write_text("payload", encoding="utf-8")
    (paths.outbox("worker") / "0001.md").write_text("---\nstatus: question\n---\nneed input\n", encoding="utf-8")

    assert [path.name for path in inbox_files(sut, "worker")] == ["0001.md"]
    message = outbox_messages(sut, "worker")[0]
    assert message.status.value == "question"
    assert message.body == "need input"


@needs_tmux
def test_ground_windows_returns_empty_for_absent_session(tmp_path: Path) -> None:
    assert windows(_sut(tmp_path)) == []


def test_tokens_ignore_unprefixed_uppercase_words() -> None:
    text = "TODO: check the JSON payload over HTTP, then mark it DONE"
    assert tokens_in(text) == set()


def test_tokens_round_trip_surrounding_prose() -> None:
    tokens = {mint() for _ in range(100)}
    assert tokens_in("surrounding prose " + " ".join(tokens)) == tokens


def test_assert_tokens_allows_non_token_text_and_rejects_foreign_tokens() -> None:
    expected = {"TOK-ABCD"}
    assert_tokens("B002", expected | {"DONE"}, expected, {"TOK-ABCD", "TOK-EFGH"})

    with pytest.raises(ProbeFailure):
        assert_tokens("B002", {"TOK-ABCD", "TOK-EFGH"}, expected, {"TOK-ABCD", "TOK-EFGH"})


def test_probe_failure_serializes_exactly_its_oracle_fields() -> None:
    failure = ProbeFailure("B002", "expected", "observed")
    assert failure.to_dict() == {"brief_id": "B002", "expected": "expected", "observed": "observed"}


def test_event_inbox_screen_and_window_assertions() -> None:
    lifecycle = [_event(1, EventType.SPAWNED), _event(2, EventType.EXIT)]
    assert_exit("B002", lifecycle, "worker")
    assert_event_absent("B002", lifecycle, EventType.ERROR)
    assert_event_count("B002", lifecycle, EventType.EXIT, 1)
    assert_inbox_contains("B002", ["a payload"], "payload")
    assert_screen_lacks("B002", "composer marker", "forbidden", landmark="marker")
    assert_no_windows("B002", [])

    with pytest.raises(HarnessError):
        assert_screen_lacks("B002", "", "forbidden", landmark="marker")
    with pytest.raises(ProbeFailure):
        assert_event_count("B002", lifecycle, EventType.EXIT, 2)
