"""Regression coverage for T2 deterministic fault states."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from collections.abc import Generator, Sequence
from pathlib import Path
from uuid import uuid4

import pytest
from agentctl import EventType
from probe import puppet
from probe.lib import sut as sut_module
from probe.lib.assertions import assert_event_absent, assert_inbox_contains, assert_screen_lacks
from probe.lib.ground import events, inbox_files, screen, windows
from probe.lib.sut import PuppetState, Sut, SutError, create_sut, destroy_sut, spawn_puppet

HAS_TMUX = shutil.which("tmux") is not None
needs_tmux = pytest.mark.skipif(not HAS_TMUX, reason="requires a local tmux binary")


@pytest.fixture
def sut() -> Generator[Sut, None, None]:
    subject = create_sut(f"T2-{uuid4().hex[:8]}", spacey=True)
    try:
        yield subject
    finally:
        destroy_sut(subject, preserve=False)


def _agentctl(sut: Sut, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(sut.agentctl), *arguments, "--runtime", str(sut.runtime), "--run", sut.run],
        env=sut.env,
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )


@needs_tmux
@pytest.mark.parametrize(
    ("state", "duration"),
    [("busy", 10.0), ("deaf", 10.0), ("dirty-composer", 10.0)],
)
def test_live_puppets_report_spawned_and_remain_live(sut: Sut, state: PuppetState, duration: float) -> None:
    spawn_puppet(sut, state, state, duration)

    assert any(event.type is EventType.SPAWNED and event.agent == state for event in events(sut))
    assert windows(sut)


@needs_tmux
def test_busy_puppet_queues_without_typing_the_doorbell(sut: Sut) -> None:
    payload = "T2_BUSY_PAYLOAD_MUST_NOT_BE_TYPED"
    spawn_puppet(sut, "busy", "busy", 20.0)
    turn = _agentctl(sut, ["wait", "--until", "agent=busy,type=turn_start", "--from-seq", "0", "--timeout", "5"])
    assert turn.returncode == 0

    queued = _agentctl(sut, ["send", "busy", payload, "--queue"])

    assert queued.returncode == 3
    assert_inbox_contains("T2", [path.read_text(encoding="utf-8") for path in inbox_files(sut, "busy")], payload)
    assert_screen_lacks("T2", screen(sut, "busy", 8), payload, landmark="puppet busy")


@needs_tmux
def test_dirty_composer_requires_force(sut: Sut) -> None:
    spawn_puppet(sut, "dirty", "dirty-composer", 10.0)
    time.sleep(0.1)

    queued = _agentctl(sut, ["send", "dirty", "queued", "--queue"])
    forced = _agentctl(sut, ["send", "dirty", "forced", "--force"])

    assert queued.returncode == 3
    assert forced.returncode == 0


@needs_tmux
def test_hard_kill_reconciles_to_one_window_vanished_exit(sut: Sut) -> None:
    spawn_puppet(sut, "killed", "hard-kill", 1.0)
    assert any(event.type is EventType.SPAWNED for event in events(sut, "killed"))

    time.sleep(puppet.HARD_KILL_DELAY + 0.5)
    assert _agentctl(sut, ["list", "--json"]).returncode == 0
    assert _agentctl(sut, ["list", "--json"]).returncode == 0

    lifecycle = events(sut, "killed")
    exits = [event for event in lifecycle if event.type is EventType.EXIT]
    assert len(exits) == 1
    assert exits[0].data == {"reason": "window_vanished"}
    assert_event_absent("T2", lifecycle, EventType.ERROR, agent="killed")


def test_spawn_puppet_rejects_provider_named_wrapper_before_spawn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sut = Sut(runtime=tmp_path, run="fixture-run", agentctl=tmp_path / "agentctl.py", env={})
    monkeypatch.setattr(sut_module, "_puppet_wrapper_path", lambda _sut, _state, _duration: tmp_path / "claude-wrapper")

    with pytest.raises(SutError, match="selects a worker provider"):
        spawn_puppet(sut, "worker", "busy")

    assert not (tmp_path / "fixture-run").exists()


def test_puppet_cli_rejects_states_outside_the_four_fault_models() -> None:
    parser = puppet.build_parser()
    assert parser.parse_args(["--state", "busy", "--for", "1"]).state == "busy"

    with pytest.raises(SystemExit):
        parser.parse_args(["--state", "fifth-state", "--for", "1"])
