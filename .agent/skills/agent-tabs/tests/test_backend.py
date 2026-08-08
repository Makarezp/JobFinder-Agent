"""Backend adapter tests.

Everything that does not need a terminal runs against FakeBackend or a recorded
TmuxBackend. The tests that genuinely exercise tmux are skipped when the binary
is absent, rather than hidden behind a marker the project must register -- the
tool has to stay independent of any one repository's pytest configuration.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import agentctl
import pytest

HAS_TMUX = shutil.which("tmux") is not None
needs_tmux = pytest.mark.skipif(not HAS_TMUX, reason="requires a local tmux binary")


# ---------------------------------------------------------------------------
# Protocol conformance and the registry
# ---------------------------------------------------------------------------


def test_both_backends_satisfy_the_protocol() -> None:
    assert isinstance(agentctl.FakeBackend(), agentctl.Backend)
    assert isinstance(agentctl.TmuxBackend(), agentctl.Backend)


def test_get_backend_resolves_by_name_and_environment() -> None:
    assert isinstance(agentctl.get_backend("fake"), agentctl.FakeBackend)
    config = agentctl.Config.from_env({agentctl.ENV_BACKEND: "fake"})
    assert isinstance(agentctl.get_backend(None, config), agentctl.FakeBackend)
    assert isinstance(agentctl.get_backend(None, agentctl.Config.from_env({})), agentctl.TmuxBackend)


def test_get_backend_rejects_an_unknown_name() -> None:
    with pytest.raises(agentctl.BackendError, match="unknown backend"):
        agentctl.get_backend("kitty")


# ---------------------------------------------------------------------------
# FakeBackend behaviour
# ---------------------------------------------------------------------------


def test_fake_backend_records_sends_and_enter_flag() -> None:
    backend = agentctl.FakeBackend()
    handle = backend.open("run", "critic", ["claude"], "/tmp")

    backend.send(handle, "with enter")
    backend.send(handle, "without enter", enter=False)

    assert backend.sends == [(handle, "with enter", True), (handle, "without enter", False)]


def test_fake_backend_preserves_hostile_text_byte_for_byte() -> None:
    backend = agentctl.FakeBackend()
    handle = backend.open("run", "critic", ["claude"], "/tmp")
    hostile = '"; rm -rf / #  `whoami`  $(id)  $HOME  \\n  --flag'

    backend.send(handle, hostile)

    assert backend.sends[0][1] == hostile
    assert backend.capture(handle) == hostile


def test_fake_backend_lifecycle_and_listing() -> None:
    backend = agentctl.FakeBackend()
    first = backend.open("run-a", "critic", ["claude"], "/tmp")
    second = backend.open("run-a", "writer", ["claude"], "/tmp")
    backend.open("run-b", "other", ["claude"], "/tmp")

    assert {window.name for window in backend.list_handles("run-a")} == {"critic", "writer"}
    assert backend.alive(first) is True

    backend.kill(first)
    assert backend.alive(first) is False
    assert {window.name for window in backend.list_handles("run-a")} == {"writer"}

    backend.kill_run("run-a")
    assert backend.alive(second) is False
    assert backend.list_handles("run-a") == []


def test_fake_backend_reports_unknown_handles() -> None:
    backend = agentctl.FakeBackend()
    with pytest.raises(agentctl.BackendError, match="no such window"):
        backend.send("@99", "hello")


# ---------------------------------------------------------------------------
# TmuxBackend argument construction (recorded, no tmux needed)
# ---------------------------------------------------------------------------


class _Recorder:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.calls: list[tuple[str, ...]] = []
        self._stdout = stdout
        self._returncode = returncode
        self._stderr = stderr

    def __call__(self, *args: str) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        return subprocess.CompletedProcess(args=list(args), returncode=self._returncode, stdout=self._stdout, stderr=self._stderr)


def _recorded(stdout: str = "", returncode: int = 0, stderr: str = "") -> tuple[agentctl.TmuxBackend, _Recorder]:
    backend = agentctl.TmuxBackend()
    recorder = _Recorder(stdout=stdout, returncode=returncode, stderr=stderr)
    backend._run = recorder  # type: ignore[method-assign]
    return backend, recorder


def test_send_is_always_two_calls_with_literal_text() -> None:
    backend, recorder = _recorded()

    backend.send("@3", "hello world")

    assert len(recorder.calls) == 2
    assert recorder.calls[0] == ("send-keys", "-t", "@3", "-l", "--", "hello world")
    assert recorder.calls[1] == ("send-keys", "-t", "@3", "Enter")


def test_send_without_enter_omits_the_submit_call() -> None:
    backend, recorder = _recorded()

    backend.send("@3", "hello", enter=False)

    assert len(recorder.calls) == 1
    assert "-l" in recorder.calls[0]


def test_open_builds_an_exec_vector_with_env_and_captures_the_window_id() -> None:
    backend, recorder = _recorded(stdout="@7\n")

    handle = backend.open("cvv", "critic", ["claude", "--model", "opus"], "/work", {"AGENT_TABS_RUN": "cvv"})

    assert handle == "@7"
    create = recorder.calls[-1]
    assert create[0] == "new-window"
    assert "-P" in create and "#{window_id}" in create
    assert ("-n", "critic") == create[create.index("-n") : create.index("-n") + 2]
    assert ("-e", "AGENT_TABS_RUN=cvv") == create[create.index("-e") : create.index("-e") + 2]
    # everything after the terminator is the command, untouched
    assert list(create[create.index("--") + 1 :]) == ["claude", "--model", "opus"]


def test_open_targets_the_session_exactly() -> None:
    backend, recorder = _recorded(stdout="@7\n")

    backend.open("cvv", "critic", ["claude"], "/work")

    assert recorder.calls[0] == ("has-session", "-t", "=cvv")


def test_tmux_failure_raises_with_stderr_attached() -> None:
    backend, _ = _recorded(returncode=1, stderr="can't find window: @9")

    with pytest.raises(agentctl.BackendError, match="can't find window"):
        backend.kill("@9")


def test_missing_binary_reports_unavailable() -> None:
    backend = agentctl.TmuxBackend(binary="tmux-does-not-exist")
    with pytest.raises(agentctl.BackendUnavailable):
        backend.capture("@1")


# ---------------------------------------------------------------------------
# Real tmux
# ---------------------------------------------------------------------------


@pytest.fixture
def tmux_run() -> Iterator[tuple[agentctl.TmuxBackend, str]]:
    backend = agentctl.TmuxBackend()
    run = f"agenttabs-test-{os.getpid()}-{uuid4().hex[:6]}"
    try:
        yield backend, run
    finally:
        backend.kill_run(run)


def _wait_for(path: Path, timeout: float = 20.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if text:
                return text
        time.sleep(0.05)
    raise AssertionError(f"{path} was never written")


@needs_tmux
def test_open_capture_kill_lifecycle(tmux_run: tuple[agentctl.TmuxBackend, str], tmp_path: Path) -> None:
    backend, run = tmux_run

    handle = backend.open(run, "critic", ["sh", "-c", "echo AGENT-TABS-MARKER; sleep 30"], str(tmp_path))

    assert handle.startswith("@")
    assert backend.alive(handle) is True

    # Capture the whole pane: -S -N returns only the visible pane when there
    # is no scrollback, and a pane can be far taller than the default 50 lines
    # (the tmux server inherits the size of the terminal that created it).
    deadline = time.monotonic() + 10
    while "AGENT-TABS-MARKER" not in backend.capture(handle, 200) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert "AGENT-TABS-MARKER" in backend.capture(handle, 200)

    backend.kill(handle)
    assert backend.alive(handle) is False


@needs_tmux
def test_new_window_passes_argv_as_a_true_exec_vector(tmux_run: tuple[agentctl.TmuxBackend, str], tmp_path: Path) -> None:
    """A space must not split, $VAR must not expand, a leading dash must not be eaten."""
    backend, run = tmux_run
    target = tmp_path / "argv.json"
    script = f"import sys, json, time; open({str(target)!r}, 'w').write(json.dumps(sys.argv)); time.sleep(30)"

    backend.open(run, "probe", [sys.executable, "-c", script, "a b", "c$dNOTSET", "-dashy"], str(tmp_path))

    assert json.loads(_wait_for(target)) == ["-c", "a b", "c$dNOTSET", "-dashy"]


@needs_tmux
def test_send_delivers_hostile_text_literally(tmux_run: tuple[agentctl.TmuxBackend, str], tmp_path: Path) -> None:
    backend, run = tmux_run
    target = tmp_path / "line.txt"
    script = f'IFS= read -r line; printf "%s" "$line" > {shlex.quote(str(target))}; sleep 30'
    handle = backend.open(run, "reader", ["sh", "-c", script], str(tmp_path))
    time.sleep(1.0)
    hostile = '-n --literal $HOME `whoami` $(id) "quoted"'

    backend.send(handle, hostile)

    assert _wait_for(target) == hostile


@needs_tmux
def test_copy_mode_is_detected(tmux_run: tuple[agentctl.TmuxBackend, str], tmp_path: Path) -> None:
    backend, run = tmux_run
    handle = backend.open(run, "scroller", ["sh", "-c", "echo hello; sleep 30"], str(tmp_path))
    time.sleep(0.5)

    assert backend.in_mode(handle) is False

    subprocess.run(["tmux", "copy-mode", "-t", handle], check=True, capture_output=True)
    assert backend.in_mode(handle) is True


@needs_tmux
def test_list_handles_reports_names_and_hides_the_root_window(tmux_run: tuple[agentctl.TmuxBackend, str], tmp_path: Path) -> None:
    backend, run = tmux_run
    backend.open(run, "critic", ["sleep", "30"], str(tmp_path))
    backend.open(run, "writer", ["sleep", "30"], str(tmp_path))

    windows = backend.list_handles(run)

    assert {window.name for window in windows} == {"critic", "writer"}
    assert all(window.handle.startswith("@") for window in windows)


@needs_tmux
def test_duplicate_names_keep_distinct_handles(tmux_run: tuple[agentctl.TmuxBackend, str], tmp_path: Path) -> None:
    """Why handles are window ids: tmux resolves a duplicated name silently."""
    backend, run = tmux_run

    first = backend.open(run, "dupe", ["sleep", "30"], str(tmp_path))
    second = backend.open(run, "dupe", ["sleep", "30"], str(tmp_path))

    assert first != second
    backend.kill(first)
    assert backend.alive(first) is False
    assert backend.alive(second) is True


@needs_tmux
def test_kill_run_tears_down_the_whole_session(tmux_run: tuple[agentctl.TmuxBackend, str], tmp_path: Path) -> None:
    backend, run = tmux_run
    handle = backend.open(run, "critic", ["sleep", "30"], str(tmp_path))

    backend.kill_run(run)

    assert backend.alive(handle) is False
    assert backend.list_handles(run) == []
    backend.kill_run(run)  # idempotent -- must not raise when the session is gone


@needs_tmux
def test_exact_session_targeting_does_not_match_a_prefix(tmux_run: tuple[agentctl.TmuxBackend, str], tmp_path: Path) -> None:
    backend, run = tmux_run
    backend.open(run, "critic", ["sleep", "30"], str(tmp_path))
    sibling = f"{run}-hotfix"
    try:
        backend.open(sibling, "other", ["sleep", "30"], str(tmp_path))
        assert {window.name for window in backend.list_handles(run)} == {"critic"}
        assert {window.name for window in backend.list_handles(sibling)} == {"other"}
    finally:
        backend.kill_run(sibling)


def test_capture_throttles_repaints_per_unattached_pane() -> None:
    """One dark pane must not suppress another pane's first repaint."""
    backend = agentctl.TmuxBackend()
    calls: list[tuple[str, ...]] = []

    def tmux(*args: str) -> str:
        calls.append(args)
        if args[0] == "display-message":
            return "0\n" if args[-1] == "#{session_attached}" else "80\n"
        if args[0] == "capture-pane":
            return "composer\n"
        return ""

    backend._tmux = tmux  # type: ignore[method-assign]
    backend.capture("@first")
    backend.capture("@second")

    resized_handles = [call[2] for call in calls if call[0] == "resize-window"]
    assert resized_handles == ["@first", "@first", "@second", "@second"]


@needs_tmux
def test_capture_forces_a_repaint_on_an_unattached_pane(tmux_run: tuple[agentctl.TmuxBackend, str], tmp_path: Path) -> None:
    """D2 regression: a detached pane defers redrawing until resize.

    Claude Code renders nothing while its session is unattached, so tmux's
    server-side copy of the pane stays blank; capture() must force a repaint
    (resize round-trip, SIGWINCH) or every screen assertion built on it passes
    vacuously. The program below draws ONLY on SIGWINCH, so a plain
    capture-pane would stay empty forever.
    """
    backend, run = tmux_run
    script = (
        "import signal, sys, time\n"
        "def draw(sig, frame):\n"
        "    print('FRAME-REPAINTED', flush=True)\n"
        "signal.signal(signal.SIGWINCH, draw)\n"
        "while True: time.sleep(1)\n"
    )
    handle = backend.open(run, "dark", [sys.executable, "-c", script], str(tmp_path))

    # 200 lines: a pane can be taller than the default 50, and the repainted
    # frame lands at its top.
    deadline = time.monotonic() + 5.0
    screen = ""
    while time.monotonic() < deadline:
        screen = backend.capture(handle, 200)
        if "FRAME-REPAINTED" in screen:
            break
        time.sleep(0.2)
    assert "FRAME-REPAINTED" in screen
