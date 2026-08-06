"""Reconciliation and teardown: list, status, close, reap, close-run.

Every test runs against FakeBackend. Git is recorded rather than executed --
these tests assert *that* a worktree removal was attempted and with what
arguments, which is the part the safety guard governs.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import agentctl
import pytest

OUTSIDE = "/tmp/evil"


def _ago(seconds: float) -> str:
    """A wire-format timestamp N seconds in the past."""
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class _GitRecorder:
    """Stands in for git so a test never touches a real repository."""

    def __init__(self, root: Path) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.checkouts = 0
        self.root = root

    def git(self, cwd: Path | str, *args: str) -> str:
        self.calls.append(args)
        return ""

    def main_checkout(self, cwd: Path | None = None) -> Path:
        self.checkouts += 1
        return self.root


@pytest.fixture
def git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _GitRecorder:
    recorder = _GitRecorder(tmp_path)
    monkeypatch.setattr(agentctl, "_git", recorder.git)
    monkeypatch.setattr(agentctl, "main_checkout", recorder.main_checkout)
    return recorder


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[agentctl.RunPaths, agentctl.FakeBackend]]:
    """A run plus the backend the CLI will resolve to.

    get_backend is patched to hand back *this* instance: a freshly constructed
    FakeBackend has no windows, so every agent would reconcile as vanished.
    """
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    monkeypatch.setattr(agentctl, "get_backend", lambda *_args, **_kwargs: backend)
    yield paths, backend


def _agent(
    paths: agentctl.RunPaths,
    backend: agentctl.FakeBackend,
    name: str,
    *,
    events: Sequence[agentctl.EventType] = (agentctl.EventType.SPAWNED,),
    worktree: Path | str | None = None,
    model: str | None = "sonnet",
    created_at: str | None = None,
) -> str:
    handle = backend.open(paths.run, name, ["claude"], "/tmp")
    paths.ensure_agent(name)
    meta = agentctl.AgentMeta(
        name=name,
        role="/tmp/ROLE.md",
        handle=handle,
        cwd="/tmp",
        permission_mode="acceptEdits",
        created_at=created_at or agentctl.utc_now(),
        model=model,
        worktree=str(worktree) if worktree else None,
    )
    paths.meta(name).write_text(meta.to_json(), encoding="utf-8")
    for event in events:
        agentctl.append_event(paths, name, event)
    return handle


def _exits(paths: agentctl.RunPaths, agent: str) -> list[agentctl.Event]:
    return [event for event in agentctl.read_events(paths, agent) if event.type is agentctl.EventType.EXIT]


def _cli(paths: agentctl.RunPaths, *args: str) -> list[str]:
    return ["--runtime", str(paths.runtime_root), "--run", paths.run, *args]


# ---------------------------------------------------------------------------
# The roster
# ---------------------------------------------------------------------------


def test_roster_comes_from_disk_not_from_the_backend(tmp_path: Path) -> None:
    """An agent whose window is gone still has records worth reporting."""
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    handle = _agent(paths, backend, "critic")
    backend.kill(handle)

    assert agentctl.list_agent_names(paths) == ["critic"]


def test_agent_directories_without_meta_are_skipped(tmp_path: Path) -> None:
    """A spawn that died before recording anything is reap's problem, not list's."""
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    _agent(paths, agentctl.FakeBackend(), "critic")
    paths.ensure_agent("stillborn")

    assert agentctl.list_agent_names(paths) == ["critic"]


def test_roster_is_empty_before_any_agent_exists(tmp_path: Path) -> None:
    assert agentctl.list_agent_names(agentctl.RunPaths.build(tmp_path / "rt", "cvv")) == []


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def test_repeated_reconciliation_records_exactly_one_exit(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    handle = _agent(paths, backend, "critic")
    backend.kill(handle)

    assert agentctl.reconcile(paths, backend) == ["critic"]
    assert agentctl.reconcile(paths, backend) == []
    assert agentctl.reconcile(paths, backend) == []

    exits = _exits(paths, "critic")
    assert len(exits) == 1
    assert exits[0].data["reason"] == "window_vanished"


def test_a_live_agent_is_never_marked_exited(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    _agent(paths, backend, "critic")

    assert agentctl.reconcile(paths, backend) == []
    assert _exits(paths, "critic") == []


def test_reconciliation_is_not_gated_on_derived_state(tmp_path: Path) -> None:
    """`error` also derives to `dead`.

    Gating on state would mean one failed keystroke permanently excluded a live
    agent from every future liveness check.
    """
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    handle = _agent(paths, backend, "critic", events=(agentctl.EventType.SPAWNED, agentctl.EventType.ERROR))
    assert agentctl.derive_state(agentctl.read_events(paths, "critic")) is agentctl.AgentState.DEAD

    assert agentctl.reconcile(paths, backend) == []  # window is still there
    backend.kill(handle)
    assert agentctl.reconcile(paths, backend) == ["critic"]  # and it is still checked


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_reconciles_then_reports(env: tuple[agentctl.RunPaths, agentctl.FakeBackend], capsys: pytest.CaptureFixture[str]) -> None:
    paths, backend = env
    _agent(paths, backend, "critic")
    handle = _agent(paths, backend, "writer")
    backend.kill(handle)

    assert agentctl.main(_cli(paths, "list", "--json")) == 0

    payload = json.loads(capsys.readouterr().out)
    states = {agent["name"]: agent["state"] for agent in payload["agents"]}
    assert states == {"critic": "idle", "writer": "dead"}
    assert [agent["alive"] for agent in payload["agents"]] == [True, False]


def test_list_renders_a_table_with_an_empty_run_handled(
    env: tuple[agentctl.RunPaths, agentctl.FakeBackend], capsys: pytest.CaptureFixture[str]
) -> None:
    paths, backend = env
    assert agentctl.main(_cli(paths, "list")) == 0
    assert "no agents" in capsys.readouterr().out

    _agent(paths, backend, "critic")
    assert agentctl.main(_cli(paths, "list")) == 0
    out = capsys.readouterr().out
    assert "NAME" in out
    assert "critic" in out and "idle" in out and "sonnet" in out


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def _busy_events(age: float) -> list[agentctl.Event]:
    return [agentctl.Event(ts=_ago(age), run="cvv", agent="critic", type=agentctl.EventType.TURN_START, seq=1, data={})]


def test_stalled_hint_needs_both_a_busy_state_and_elapsed_time() -> None:
    events = _busy_events(600)

    assert agentctl.stalled_for(events, agentctl.AgentState.BUSY, 300) == pytest.approx(600, abs=5)
    assert agentctl.stalled_for(events, agentctl.AgentState.BUSY, 900) is None
    assert agentctl.stalled_for(events, agentctl.AgentState.IDLE, 300) is None
    assert agentctl.stalled_for([], agentctl.AgentState.BUSY, 300) is None


def test_a_fresh_turn_is_not_stalled() -> None:
    assert agentctl.stalled_for(_busy_events(2), agentctl.AgentState.BUSY, 300) is None


def test_an_unparseable_timestamp_does_not_raise() -> None:
    events = [agentctl.Event(ts="not-a-timestamp", run="cvv", agent="critic", type=agentctl.EventType.TURN_START, seq=1, data={})]
    assert agentctl.stalled_for(events, agentctl.AgentState.BUSY, 300) is None


def test_status_surfaces_the_stalled_hint(env: tuple[agentctl.RunPaths, agentctl.FakeBackend], capsys: pytest.CaptureFixture[str]) -> None:
    """This is what a worker deadlocked on an unattended dialog looks like."""
    paths, backend = env
    _agent(paths, backend, "critic")
    # A scoped context, not monkeypatch.undo(): undo() would also revert the
    # get_backend patch the fixture installed, and every agent would then
    # reconcile as vanished.
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(agentctl, "utc_now", lambda: _ago(600))
        agentctl.append_event(paths, "critic", agentctl.EventType.TURN_START)

    assert agentctl.main(_cli(paths, "status", "critic")) == 0

    out = capsys.readouterr().out
    assert "STALLED" in out
    assert "check this window" in out


def test_status_json_carries_meta_events_and_the_hint(
    env: tuple[agentctl.RunPaths, agentctl.FakeBackend], capsys: pytest.CaptureFixture[str]
) -> None:
    paths, backend = env
    _agent(paths, backend, "critic", events=(agentctl.EventType.SPAWNED, agentctl.EventType.TURN_END))

    assert agentctl.main(_cli(paths, "status", "critic", "--json")) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "idle"
    assert payload["stalled_seconds"] is None
    assert payload["meta"]["name"] == "critic"
    assert [event["type"] for event in payload["events"]] == ["spawned", "turn_end"]


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


def test_close_types_exit_before_killing(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    handle = _agent(paths, backend, "critic")

    assert agentctl.close_agent(paths, backend, "critic", timeout=0.1) == "graceful"

    assert backend.sends == [(handle, "/exit", True)]
    assert backend.alive(handle) is False
    assert _exits(paths, "critic")[0].data["reason"] == "graceful"


def test_force_skips_the_courtesy_and_goes_straight_to_kill(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    handle = _agent(paths, backend, "critic")

    assert agentctl.close_agent(paths, backend, "critic", force=True) == "forced"

    assert backend.sends == []
    assert backend.alive(handle) is False


def test_close_on_a_vanished_window_types_nothing_and_still_records_exit(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    handle = _agent(paths, backend, "critic")
    backend.kill(handle)

    assert agentctl.close_agent(paths, backend, "critic") == "already_gone"

    assert backend.sends == []
    assert _exits(paths, "critic")[0].data["reason"] == "already_gone"


def test_close_does_not_duplicate_an_exit_the_hook_already_wrote(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    _agent(paths, backend, "critic", events=(agentctl.EventType.SPAWNED, agentctl.EventType.EXIT))

    agentctl.close_agent(paths, backend, "critic", force=True)

    assert len(_exits(paths, "critic")) == 1


def test_close_removes_a_recorded_worktree(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    worktree = paths.worktrees / "critic"
    worktree.mkdir(parents=True)
    _agent(paths, backend, "critic", worktree=worktree)

    agentctl.close_agent(paths, backend, "critic", force=True)

    assert git.calls == [("worktree", "remove", "--force", str(worktree))]


def test_close_without_a_worktree_makes_no_git_calls(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    _agent(paths, backend, "critic")

    agentctl.close_agent(paths, backend, "critic", force=True)

    assert git.calls == []
    assert git.checkouts == 0  # the main checkout is resolved lazily, never speculatively


def test_close_cli_reports_the_outcome(
    env: tuple[agentctl.RunPaths, agentctl.FakeBackend], capsys: pytest.CaptureFixture[str], git: _GitRecorder
) -> None:
    paths, backend = env
    _agent(paths, backend, "critic")

    assert agentctl.main(_cli(paths, "close", "critic", "--force")) == 0
    assert "closed\tcritic\tforced" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The worktree guard -- one guard, every call site
# ---------------------------------------------------------------------------


def test_close_refuses_a_worktree_outside_the_runtime_tree(tmp_path: Path, git: _GitRecorder) -> None:
    """A doctored meta.json must not talk git into deleting real work."""
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    handle = _agent(paths, backend, "critic", worktree=OUTSIDE)

    with pytest.raises(agentctl.BusError, match="refusing to remove worktree outside"):
        agentctl.close_agent(paths, backend, "critic", force=True)

    assert git.calls == []
    assert backend.alive(handle) is True  # validated before anything was killed


def test_reap_refuses_a_worktree_outside_the_runtime_tree(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    plan = agentctl.ReapPlan(agents=[], worktrees=[Path(OUTSIDE)], session=False)

    with pytest.raises(agentctl.BusError, match="refusing to remove worktree outside"):
        agentctl.apply_reap(paths, agentctl.FakeBackend(), plan)

    assert git.calls == []


def test_close_run_refuses_before_killing_anything(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    good = _agent(paths, backend, "critic")
    bad = _agent(paths, backend, "writer", worktree=OUTSIDE)

    with pytest.raises(agentctl.BusError, match="refusing to remove worktree outside"):
        agentctl.close_run(paths, backend, force=True)

    assert backend.alive(good) is True
    assert backend.alive(bad) is True
    assert git.calls == []


# ---------------------------------------------------------------------------
# reap
# ---------------------------------------------------------------------------


def test_reap_reports_orphans_without_touching_them(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    worktree = paths.worktrees / "critic"
    worktree.mkdir(parents=True)
    handle = _agent(paths, backend, "critic", worktree=worktree)
    backend.kill(handle)

    plan = agentctl.plan_reap(paths, backend)

    assert plan.agents == ["critic"]
    assert plan.worktrees == [worktree]
    assert worktree.exists()
    assert git.calls == []
    assert _exits(paths, "critic") == []


def test_a_live_agents_worktree_is_never_an_orphan(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    worktree = paths.worktrees / "critic"
    worktree.mkdir(parents=True)
    _agent(paths, backend, "critic", worktree=worktree)

    plan = agentctl.plan_reap(paths, backend)

    assert plan.agents == []
    assert plan.worktrees == []


def test_apply_reap_records_exit_and_removes_the_worktree(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    worktree = paths.worktrees / "critic"
    worktree.mkdir(parents=True)
    handle = _agent(paths, backend, "critic", worktree=worktree)
    backend.kill(handle)

    agentctl.apply_reap(paths, backend, agentctl.plan_reap(paths, backend))

    assert git.calls == [("worktree", "remove", "--force", str(worktree))]
    assert _exits(paths, "critic")[0].data["reason"] == "reaped"


def test_reap_cli_is_read_only_by_default(
    env: tuple[agentctl.RunPaths, agentctl.FakeBackend], capsys: pytest.CaptureFixture[str], git: _GitRecorder
) -> None:
    paths, backend = env
    handle = _agent(paths, backend, "critic")
    backend.kill(handle)

    assert agentctl.main(_cli(paths, "reap")) == 0

    out = capsys.readouterr().out
    assert "would remove agent record: critic" in out
    assert "--apply" in out
    assert _exits(paths, "critic") == []


def test_reap_apply_acts(env: tuple[agentctl.RunPaths, agentctl.FakeBackend], capsys: pytest.CaptureFixture[str], git: _GitRecorder) -> None:
    paths, backend = env
    handle = _agent(paths, backend, "critic")
    backend.kill(handle)

    assert agentctl.main(_cli(paths, "reap", "--apply")) == 0

    assert "removed agent record: critic" in capsys.readouterr().out
    assert len(_exits(paths, "critic")) == 1


def test_dry_run_overrides_apply(env: tuple[agentctl.RunPaths, agentctl.FakeBackend], capsys: pytest.CaptureFixture[str], git: _GitRecorder) -> None:
    """Between "act" and "do not act", the safe reading wins."""
    paths, backend = env
    handle = _agent(paths, backend, "critic")
    backend.kill(handle)

    assert agentctl.main(_cli(paths, "reap", "--apply", "--dry-run")) == 0

    assert "would remove" in capsys.readouterr().out
    assert _exits(paths, "critic") == []


def test_reap_all_kills_the_session_once_it_is_empty(
    env: tuple[agentctl.RunPaths, agentctl.FakeBackend], capsys: pytest.CaptureFixture[str], git: _GitRecorder
) -> None:
    paths, backend = env
    handle = _agent(paths, backend, "critic")
    backend.kill(handle)

    assert agentctl.main(_cli(paths, "reap", "--all")) == 0

    assert "killed empty session" in capsys.readouterr().out


def test_reap_all_leaves_a_session_that_still_has_agents(
    env: tuple[agentctl.RunPaths, agentctl.FakeBackend], capsys: pytest.CaptureFixture[str], git: _GitRecorder
) -> None:
    paths, backend = env
    _agent(paths, backend, "critic")

    assert agentctl.main(_cli(paths, "reap", "--all")) == 0

    out = capsys.readouterr().out
    assert "nothing to reap" in out
    assert backend.list_handles(paths.run) != []


# ---------------------------------------------------------------------------
# close-run
# ---------------------------------------------------------------------------


def test_close_run_closes_every_agent_and_the_session(tmp_path: Path, git: _GitRecorder) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "rt", "cvv")
    backend = agentctl.FakeBackend()
    _agent(paths, backend, "critic")
    _agent(paths, backend, "writer")

    assert agentctl.close_run(paths, backend, force=True) == ["critic", "writer"]

    assert backend.list_handles(paths.run) == []
    assert len(_exits(paths, "critic")) == 1
    assert len(_exits(paths, "writer")) == 1


def test_close_run_on_an_empty_run_is_harmless(
    env: tuple[agentctl.RunPaths, agentctl.FakeBackend], capsys: pytest.CaptureFixture[str], git: _GitRecorder
) -> None:
    paths, _ = env
    assert agentctl.main(_cli(paths, "close-run")) == 0
    assert "no agents" in capsys.readouterr().out
