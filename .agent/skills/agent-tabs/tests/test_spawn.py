"""Spawn, hook plumbing and the readiness handshake.

The end-to-end test that launches a real `claude` session costs an API call, so
it is opt-in behind AGENT_TABS_E2E=1 rather than part of the default run.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import agentctl
import pytest

TRUE_BINARY = "/usr/bin/true"


@pytest.fixture
def role(tmp_path: Path) -> Path:
    path = tmp_path / "ROLE.md"
    path.write_text("# Reviewer\nBe skeptical.\n", encoding="utf-8")
    return path


def _responder(
    paths: agentctl.RunPaths,
    backend: agentctl.FakeBackend,
    agent: str,
    *,
    acknowledge_bootstrap: bool = True,
) -> threading.Thread:
    """Stand in for the worker's hooks: report SessionStart, then the first turn.

    It waits for the window to exist first. A real SessionStart hook cannot fire
    before the process is launched, and firing early would let the test pass
    against a spawn that never actually waited for anything.
    """

    def run() -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if any(window.name == agent for window in backend.windows.values()):
                break
            time.sleep(0.01)
        agentctl.append_event(paths, agent, agentctl.EventType.SPAWNED)
        if not acknowledge_bootstrap:
            return
        seen = agentctl.wait_for_event(paths, agent=agent, types=[agentctl.EventType.MESSAGE_SENT], timeout=10)
        if seen is not None:
            agentctl.append_event(paths, agent, agentctl.EventType.TURN_START)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# Hook command quoting -- the highest-risk defect in the iteration
# ---------------------------------------------------------------------------


def test_hook_command_survives_paths_with_spaces_and_at_signs(tmp_path: Path) -> None:
    """Verified against a real session: unquoted, the hook silently never fires."""
    runtime = tmp_path / "Google Drive-user@example.com" / "My Drive" / "rt"
    paths = agentctl.RunPaths.build(runtime, "cvv")

    written = agentctl.write_settings(paths, "critic")
    settings = json.loads(written.read_text(encoding="utf-8"))
    command = settings["hooks"]["SessionStart"][0]["hooks"][0]["command"]

    # Asserting the string merely "contains the path" would pass on the broken
    # version; splitting it the way a shell does is what actually proves it.
    assert shlex.split(command) == [
        sys.executable,
        str(Path(agentctl.__file__).resolve()),
        "hook",
        "spawned",
        "--runtime",
        str(paths.runtime_root),
        "--run",
        "cvv",
        "--agent",
        "critic",
    ]


@pytest.mark.parametrize("hook_name", list(agentctl.HOOK_EVENTS))
def test_generated_hook_commands_actually_execute(tmp_path: Path, hook_name: str) -> None:
    """Run the exact string we write into settings.json, through a shell.

    Asserting on the argv we *intended* is not enough: an earlier version put
    the global --runtime/--run options after the subcommand, which argparse
    rejects with exit 2 -- before the exit-0-always handler could run. Every
    unit test passed while every real session logged a SessionStart hook error.
    """
    paths = agentctl.RunPaths.build(tmp_path / "Google Drive-user@example.com" / "My Drive" / "rt", "cvv")
    settings = json.loads(agentctl.write_settings(paths, "critic").read_text(encoding="utf-8"))
    command = settings["hooks"][hook_name][0]["hooks"][0]["command"]

    # shell=True is the point: it is how Claude Code invokes the hook.
    completed = subprocess.run(command, shell=True, input='{"session_id":"abc","cwd":"/tmp"}', capture_output=True, text=True, check=False)

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    events = agentctl.read_events(paths, "critic")
    assert [event.type for event in events] == [agentctl.HOOK_EVENTS[hook_name]]
    assert events[0].data == {"session_id": "abc", "cwd": "/tmp"}


def test_settings_wire_all_four_lifecycle_hooks(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path, "cvv")

    settings = json.loads(agentctl.write_settings(paths, "critic").read_text(encoding="utf-8"))

    assert set(settings["hooks"]) == {"SessionStart", "UserPromptSubmit", "Stop", "SessionEnd"}
    for hook_name, event in agentctl.HOOK_EVENTS.items():
        argv = shlex.split(settings["hooks"][hook_name][0]["hooks"][0]["command"])
        assert argv[argv.index("hook") + 1] == event.value
        assert argv[argv.index("--runtime") + 1] == str(paths.runtime_root)
        assert argv[argv.index("--agent") + 1] == "critic"
        assert Path(argv[1]).is_absolute()


# ---------------------------------------------------------------------------
# spawn
# ---------------------------------------------------------------------------


def test_spawn_reports_identity_through_the_environment(tmp_path: Path, role: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    _responder(paths, backend, "critic")

    meta = agentctl.spawn_agent(paths, backend, "critic", role, claude_binary=TRUE_BINARY, spawn_timeout=10, bootstrap_timeout=10)

    window = backend.windows[meta.handle]
    assert window.env == {
        agentctl.ENV_RUNTIME: str(paths.runtime_root),
        agentctl.ENV_RUN: "cvv",
        agentctl.ENV_AGENT: "critic",
    }
    assert agentctl.AgentMeta.load(paths.meta("critic")).handle == meta.handle
    assert meta.permission_mode == "acceptEdits"


def test_spawn_passes_model_and_isolation_flags(tmp_path: Path, role: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    _responder(paths, backend, "critic")

    meta = agentctl.spawn_agent(
        paths, backend, "critic", role, model="opus", isolated_settings=True, claude_binary=TRUE_BINARY, spawn_timeout=10, bootstrap_timeout=10
    )

    argv = backend.windows[meta.handle].cmd
    assert argv[:2] == [TRUE_BINARY, "--settings"]
    assert argv[argv.index("--model") + 1] == "opus"
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"


def test_bootstrap_doorbell_is_a_pointer_not_the_payload(tmp_path: Path, role: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    _responder(paths, backend, "critic")

    agentctl.spawn_agent(paths, backend, "critic", role, claude_binary=TRUE_BINARY, spawn_timeout=10, bootstrap_timeout=10)

    _, text, enter = backend.sends[0]
    assert "\n" not in text
    assert len(text) < 300
    assert text.startswith("[orchestrator] new instruction:")
    assert enter is True
    assert (paths.inbox("critic") / "0001.md").read_text(encoding="utf-8").startswith("# Bootstrap: critic")


def test_spawn_timeout_leaves_no_window_and_no_worktree(tmp_path: Path, role: Path, git_repo: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()

    with pytest.raises(agentctl.SpawnError, match="never reported SessionStart"):
        agentctl.spawn_agent(paths, backend, "critic", role, worktree=True, cwd=git_repo, claude_binary=TRUE_BINARY, spawn_timeout=0.5)

    assert all(window.alive is False for window in backend.windows.values())
    assert not (paths.worktrees / "critic").exists()
    assert [event.type for event in agentctl.read_events(paths)][-1] is agentctl.EventType.ERROR


def test_unacknowledged_bootstrap_is_retried_exactly_once_then_fails(tmp_path: Path, role: Path) -> None:
    """Turn 1 is the only unrecoverable message: the inbox failsafe needs a turn to run."""
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    _responder(paths, backend, "critic", acknowledge_bootstrap=False)

    with pytest.raises(agentctl.SpawnError, match="never started a turn"):
        agentctl.spawn_agent(paths, backend, "critic", role, claude_binary=TRUE_BINARY, spawn_timeout=10, bootstrap_timeout=0.5)

    assert len(backend.sends) == 2
    assert all(window.alive is False for window in backend.windows.values())


def test_spawn_rejects_a_duplicate_name_before_touching_the_backend(tmp_path: Path, role: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    backend.open("cvv", "critic", ["claude"], str(tmp_path))
    before = len(backend.windows)

    with pytest.raises(agentctl.SpawnError, match="already running"):
        agentctl.spawn_agent(paths, backend, "critic", role, claude_binary=TRUE_BINARY)

    assert len(backend.windows) == before


@pytest.mark.parametrize("name", ["has space", "dot.dot", "slash/slash", ""])
def test_spawn_rejects_unusable_names(tmp_path: Path, role: Path, name: str) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    with pytest.raises(agentctl.SpawnError, match="invalid agent name"):
        agentctl.spawn_agent(paths, agentctl.FakeBackend(), name, role, claude_binary=TRUE_BINARY)


def test_spawn_rejects_a_missing_role(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    with pytest.raises(agentctl.SpawnError, match="role file not found"):
        agentctl.spawn_agent(paths, agentctl.FakeBackend(), "critic", tmp_path / "nope.md", claude_binary=TRUE_BINARY)


# ---------------------------------------------------------------------------
# Worktrees
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=test", *args], cwd=str(repo), check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "commit", "--allow-empty", "-m", "init")
    return repo


def test_spawn_with_worktree_gives_the_agent_its_own_checkout(tmp_path: Path, role: Path, git_repo: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    _responder(paths, backend, "critic")

    meta = agentctl.spawn_agent(
        paths, backend, "critic", role, worktree=True, cwd=git_repo, claude_binary=TRUE_BINARY, spawn_timeout=10, bootstrap_timeout=10
    )

    assert meta.worktree == str(paths.worktrees / "critic")
    assert (paths.worktrees / "critic").is_dir()
    assert backend.windows[meta.handle].cwd == meta.worktree


def test_remove_worktree_refuses_a_path_outside_the_runtime_tree(tmp_path: Path, git_repo: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    victim = tmp_path / "precious"
    victim.mkdir()

    with pytest.raises(agentctl.BusError, match="refusing to remove worktree"):
        agentctl.remove_worktree(paths, victim, git_repo)

    assert victim.exists()


# ---------------------------------------------------------------------------
# hook and reply
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path, env: dict[str, str], stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, agentctl.__file__, *args],
        cwd=str(cwd),
        env={**os.environ, **env},
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def test_hook_exits_zero_and_records_an_error_on_bad_stdin(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    env = {agentctl.ENV_RUNTIME: str(paths.runtime_root), agentctl.ENV_RUN: "cvv", agentctl.ENV_AGENT: "critic"}

    completed = _run_cli("hook", "turn_start", cwd=tmp_path, env=env, stdin="{not json at all")

    assert completed.returncode == 0
    assert completed.stderr == ""
    events = agentctl.read_events(paths, "critic")
    assert [event.type for event in events] == [agentctl.EventType.TURN_START]
    assert events[0].data == {"stdin": "unparseable"}


def test_hook_exits_zero_with_empty_stdin(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    env = {agentctl.ENV_RUNTIME: str(paths.runtime_root), agentctl.ENV_RUN: "cvv", agentctl.ENV_AGENT: "critic"}

    completed = _run_cli("hook", "spawned", cwd=tmp_path, env=env)

    assert completed.returncode == 0
    assert len(agentctl.read_events(paths, "critic")) == 1
    assert json.loads(paths.state("critic").read_text(encoding="utf-8"))["state"] == "idle"


def test_reply_from_a_nested_worktree_lands_in_the_orchestrator_tree(tmp_path: Path, git_repo: Path) -> None:
    """B2: a worker must never resolve a runtime root of its own."""
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    paths.ensure_agent("critic")
    worktree = agentctl.add_worktree(paths, "critic", git_repo)
    env = {agentctl.ENV_RUNTIME: str(paths.runtime_root), agentctl.ENV_RUN: "cvv", agentctl.ENV_AGENT: "critic"}

    completed = _run_cli("reply", "--status", "question", cwd=worktree, env=env, stdin="which worktree policy?")

    assert completed.returncode == 0
    messages = agentctl.read_outbox(paths, "critic")
    assert [message.status for message in messages] == [agentctl.OutboxStatus.QUESTION]
    assert messages[0].body.strip() == "which worktree policy?"
    assert not list(worktree.rglob("bus.jsonl"))


def test_reply_flips_state_to_awaiting_human(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    agentctl.append_event(paths, "critic", agentctl.EventType.SPAWNED)
    agentctl.append_event(paths, "critic", agentctl.EventType.TURN_START)

    agentctl.write_reply(paths, "critic", agentctl.OutboxStatus.QUESTION, "which one?")
    agentctl.append_event(paths, "critic", agentctl.EventType.TURN_END)

    assert agentctl.refresh_state_cache(paths, "critic") is agentctl.AgentState.AWAITING_HUMAN


# ---------------------------------------------------------------------------
# End to end -- opt in, costs an API call
# ---------------------------------------------------------------------------


E2E = os.environ.get("AGENT_TABS_E2E") == "1"
needs_e2e = pytest.mark.skipif(
    not (E2E and shutil.which("tmux") and shutil.which("claude")),
    reason="set AGENT_TABS_E2E=1 with tmux and claude present",
)


@needs_e2e
def test_end_to_end_spawn_completes_the_handshake(tmp_path: Path, role: Path) -> None:
    runtime = tmp_path / "rt"
    run = f"agenttabs-e2e-{uuid4().hex[:6]}"
    paths = agentctl.RunPaths.build(runtime, run)
    backend = agentctl.TmuxBackend()
    try:
        meta = agentctl.spawn_agent(paths, backend, "probe", role, model="sonnet", cwd=Path.cwd(), spawn_timeout=90, bootstrap_timeout=90)
        assert backend.alive(meta.handle)
        types = [event.type for event in agentctl.read_events(paths, "probe")]
        assert agentctl.EventType.SPAWNED in types
        assert agentctl.EventType.TURN_START in types
        deadline = time.monotonic() + 120
        while agentctl.EventType.TURN_END not in [event.type for event in agentctl.read_events(paths, "probe")]:
            assert time.monotonic() < deadline, "agent never finished its first turn"
            time.sleep(1.0)
    finally:
        backend.kill_run(run)
