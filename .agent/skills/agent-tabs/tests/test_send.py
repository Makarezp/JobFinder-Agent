"""Messaging: the doorbell, the readiness gates and `read`.

The composer fixtures below are literal captures from a live Claude Code
v2.1.223 session in tmux, not an approximation. Asserting against invented
output is how the argparse defect in Ticket 3 slipped past 63 green tests.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import agentctl
import pytest

HAS_TMUX = shutil.which("tmux") is not None
needs_tmux = pytest.mark.skipif(not HAS_TMUX, reason="requires a local tmux binary")

RULE = "─" * 80

# Captured from a real session: the marker is followed by U+00A0.
EMPTY_COMPOSER = "\n".join(
    [
        "                                                             ◐ medium · /effort",
        RULE,
        "❯\xa0",
        RULE,
        "  branch:main | !1 ?2 ⇡7",
        "  [OMC#4.15.7L] | Model: Sonnet 5 | 5h:[######--]81%(2h22m)",
        "  session:0m | ctx:[----------]0%",
        "  ⏵⏵ accept edits on (shift+tab to cycle) · ← 1 agent",
    ]
)

TYPED_COMPOSER = EMPTY_COMPOSER.replace("❯\xa0", "❯\xa0half typed by a human")


def _make_agent(
    tmp_path: Path,
    *,
    events: Sequence[agentctl.EventType] = (agentctl.EventType.SPAWNED,),
    screen: str = EMPTY_COMPOSER,
    in_mode: bool = False,
) -> tuple[agentctl.RunPaths, agentctl.FakeBackend, str]:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    handle = backend.open("cvv", "critic", ["claude"], str(tmp_path))
    backend.windows[handle].screen = screen.splitlines()
    backend.windows[handle].in_mode = in_mode
    paths.ensure_agent("critic")
    meta = agentctl.AgentMeta(
        name="critic",
        role=str(tmp_path / "ROLE.md"),
        handle=handle,
        cwd=str(tmp_path),
        permission_mode="acceptEdits",
        created_at=agentctl.utc_now(),
    )
    paths.meta("critic").write_text(meta.to_json(), encoding="utf-8")
    for event in events:
        agentctl.append_event(paths, "critic", event)
    return paths, backend, handle


# ---------------------------------------------------------------------------
# The composer heuristic
# ---------------------------------------------------------------------------


def test_empty_composer_is_not_busy() -> None:
    assert agentctl._input_row_looks_busy(EMPTY_COMPOSER) is False


def test_composer_with_pending_text_is_busy() -> None:
    assert agentctl._input_row_looks_busy(TYPED_COMPOSER) is True


def test_missing_marker_fails_open() -> None:
    """A TUI redesign must degrade the framework, not deadlock it."""
    assert agentctl._input_row_looks_busy("some future layout\nwith no composer\n") is False


def test_only_the_lowest_composer_row_counts() -> None:
    scrollback = f"❯\xa0an old submitted prompt\nsome output\n{EMPTY_COMPOSER}"
    assert agentctl._input_row_looks_busy(scrollback) is False


# ---------------------------------------------------------------------------
# Readiness gates
# ---------------------------------------------------------------------------


def test_busy_agent_is_not_ready(tmp_path: Path) -> None:
    paths, backend, _ = _make_agent(tmp_path, events=(agentctl.EventType.SPAWNED, agentctl.EventType.TURN_START))

    readiness = agentctl.is_ready(paths, backend, "critic")

    assert readiness.ready is False
    assert readiness.reason == "busy"


def test_dead_agent_is_not_ready(tmp_path: Path) -> None:
    paths, backend, _ = _make_agent(tmp_path, events=(agentctl.EventType.SPAWNED, agentctl.EventType.EXIT))
    assert agentctl.is_ready(paths, backend, "critic").reason == "dead"


def test_copy_mode_refuses_and_leaves_the_scroll_alone(tmp_path: Path) -> None:
    paths, backend, handle = _make_agent(tmp_path, in_mode=True)

    readiness = agentctl.is_ready(paths, backend, "critic")

    assert readiness.ready is False
    assert readiness.reason == "copy_mode"
    assert backend.windows[handle].in_mode is True  # never cancelled on the human's behalf


def test_pending_human_text_refuses(tmp_path: Path) -> None:
    paths, backend, _ = _make_agent(tmp_path, screen=TYPED_COMPOSER)

    readiness = agentctl.is_ready(paths, backend, "critic")

    assert readiness.ready is False
    assert readiness.reason == "human_typing"


def test_idle_agent_with_a_clean_composer_is_ready(tmp_path: Path) -> None:
    paths, backend, _ = _make_agent(tmp_path)
    assert agentctl.is_ready(paths, backend, "critic").ready is True


def test_awaiting_human_is_still_sendable(tmp_path: Path) -> None:
    """An agent that asked a question must remain reachable by the orchestrator."""
    paths, backend, _ = _make_agent(tmp_path, events=(agentctl.EventType.SPAWNED, agentctl.EventType.TURN_START))
    agentctl.write_reply(paths, "critic", agentctl.OutboxStatus.QUESTION, "which policy?")
    agentctl.append_event(paths, "critic", agentctl.EventType.TURN_END)

    readiness = agentctl.is_ready(paths, backend, "critic")

    assert readiness.ready is True
    assert readiness.reason == "awaiting_human"


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


def test_doorbell_is_a_pointer_however_large_the_payload(tmp_path: Path) -> None:
    paths, backend, _ = _make_agent(tmp_path)
    payload = "\n\n".join(f"Paragraph {index}. " + "word " * 60 for index in range(20))
    assert len(payload) > 5000

    inbox_path, readiness = agentctl.send_message(paths, backend, "critic", payload)

    assert readiness.ready is True
    _, text, _ = backend.sends[0]
    assert "\n" not in text
    assert len(text) < 300
    assert inbox_path.read_text(encoding="utf-8") == payload


def test_inbox_survives_a_backend_failure(tmp_path: Path) -> None:
    """The payload must outlive the terminal: that is what makes a lost keystroke cosmetic."""
    paths, backend, _ = _make_agent(tmp_path)

    def explode(handle: str, text: str, enter: bool = True) -> None:
        raise agentctl.BackendError("window vanished")

    backend.send = explode  # type: ignore[method-assign]

    with pytest.raises(agentctl.BackendError):
        agentctl.send_message(paths, backend, "critic", "review ticket 6")

    inbox = sorted(paths.inbox("critic").glob("*.md"))
    assert [path.read_text(encoding="utf-8") for path in inbox] == ["review ticket 6"]
    assert agentctl.read_events(paths, "critic")[-1].type is agentctl.EventType.ERROR


def test_queue_returns_immediately_without_typing(tmp_path: Path) -> None:
    paths, backend, _ = _make_agent(tmp_path, events=(agentctl.EventType.SPAWNED, agentctl.EventType.TURN_START))

    inbox_path, readiness = agentctl.send_message(paths, backend, "critic", "later", queue=True)

    assert readiness.ready is False
    assert backend.sends == []
    assert inbox_path.exists()
    assert agentctl.EventType.MESSAGE_SENT not in [event.type for event in agentctl.read_events(paths, "critic")]


def test_force_bypasses_every_gate(tmp_path: Path) -> None:
    paths, backend, _ = _make_agent(tmp_path, events=(agentctl.EventType.SPAWNED, agentctl.EventType.TURN_START), screen=TYPED_COMPOSER, in_mode=True)

    _, readiness = agentctl.send_message(paths, backend, "critic", "now", force=True)

    assert readiness.reason == "forced"
    assert len(backend.sends) == 1


def test_no_enter_types_without_submitting(tmp_path: Path) -> None:
    paths, backend, _ = _make_agent(tmp_path)

    agentctl.send_message(paths, backend, "critic", "for your review", enter=False)

    assert backend.sends[0][2] is False


def test_wait_idle_times_out_and_queues(tmp_path: Path) -> None:
    paths, backend, _ = _make_agent(tmp_path, events=(agentctl.EventType.SPAWNED, agentctl.EventType.TURN_START))

    _, readiness = agentctl.send_message(paths, backend, "critic", "later", wait_idle=0.3)

    assert readiness.ready is False
    assert backend.sends == []


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_send_cli_reports_queued_with_exit_three(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, _, _ = _make_agent(tmp_path, events=(agentctl.EventType.SPAWNED, agentctl.EventType.TURN_START))
    argv = ["--runtime", str(paths.runtime_root), "--run", "cvv", "--backend", "fake", "send", "critic", "hi", "--queue"]

    assert agentctl.main(argv) == agentctl.EXIT_QUEUED
    assert "queued" in capsys.readouterr().out


def test_read_outbox_filters_by_since_and_flags_malformed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, _, _ = _make_agent(tmp_path)
    agentctl.write_reply(paths, "critic", agentctl.OutboxStatus.REPLY, "first")
    agentctl.write_reply(paths, "critic", agentctl.OutboxStatus.QUESTION, "second")
    (paths.outbox("critic") / "0003.md").write_text("no frontmatter\n", encoding="utf-8")

    argv = ["--runtime", str(paths.runtime_root), "--run", "cvv", "read", "critic", "--since", "1", "--json"]
    assert agentctl.main(argv) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [message["index"] for message in payload["messages"]] == [2, 3]
    assert payload["messages"][0]["status"] == "question"
    assert payload["messages"][1]["malformed"] is True


def test_read_screen_returns_the_raw_window(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """--screen is how the orchestrator sees what the human said in that pane."""
    paths, backend, _ = _make_agent(tmp_path, screen=TYPED_COMPOSER)
    monkeypatch.setattr(agentctl, "get_backend", lambda *_args, **_kwargs: backend)

    argv = ["--runtime", str(paths.runtime_root), "--run", "cvv", "read", "critic", "--screen", "8"]
    assert agentctl.main(argv) == 0

    assert "half typed by a human" in capsys.readouterr().out


def test_send_cli_requires_a_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, _, _ = _make_agent(tmp_path)
    argv = ["--runtime", str(paths.runtime_root), "--run", "cvv", "--backend", "fake", "send", "critic"]

    assert agentctl.main(argv) == 1
    assert "no message given" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# capture() line accounting
# ---------------------------------------------------------------------------


@needs_tmux
def test_capture_returns_at_most_the_requested_lines(tmp_path: Path) -> None:
    """-S -N returns N + pane_height lines; the parameter must mean what it says."""
    backend = agentctl.TmuxBackend()
    run = f"agenttabs-cap-{uuid4().hex[:6]}"
    try:
        handle = backend.open(run, "noisy", ["sh", "-c", "for i in $(seq 1 200); do echo line-$i; done; sleep 30"], str(tmp_path))
        subprocess.run(["tmux", "set-option", "-t", run, "status", "off"], check=False, capture_output=True)
        deadline_text = ""
        for _ in range(100):
            deadline_text = backend.capture(handle, 12)
            if "line-200" in deadline_text:
                break
        assert len(deadline_text.splitlines()) <= 12
        assert len(backend.capture(handle, 3).splitlines()) <= 3
    finally:
        backend.kill_run(run)
