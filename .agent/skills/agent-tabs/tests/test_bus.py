"""Bus layer tests.

The concurrency test comes first: it is the one that justifies the locking
design, and it is the one whose harness is easiest to get subtly wrong.
"""

from __future__ import annotations

import json
import multiprocessing
import subprocess
import sys
import threading
from pathlib import Path

import agentctl
import pytest

TOOL_DIR = str(Path(agentctl.__file__).resolve().parent)


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def _append_worker(tool_dir: str, runtime: str, run: str, agent: str, count: int) -> None:
    """Append events from a separate process.

    Defined at module level and re-importing the tool itself, because macOS
    defaults to the ``spawn`` start method: each child is a fresh interpreter
    that imports this module by name and unpickles its arguments. Passing a
    module object across that boundary fails at ``Process.start()`` with
    "cannot pickle 'module' object" -- before a single event is written, so the
    locking under test would never be exercised.
    """
    import sys as child_sys

    if tool_dir not in child_sys.path:
        child_sys.path.insert(0, tool_dir)

    import agentctl as mod

    paths = mod.RunPaths.build(runtime, run)
    for _ in range(count):
        mod.append_event(paths, agent, mod.EventType.TURN_END, {})


def test_concurrent_appends_assign_unique_sequences(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime"
    run = "concurrency"
    workers, per_worker = 8, 25

    context = multiprocessing.get_context("spawn")
    processes = [context.Process(target=_append_worker, args=(TOOL_DIR, str(runtime), run, f"agent{index}", per_worker)) for index in range(workers)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=120)

    assert all(process.exitcode == 0 for process in processes), [p.exitcode for p in processes]

    paths = agentctl.RunPaths.build(runtime, run)
    events = agentctl.read_events(paths)
    sequences = [event.seq for event in events]

    assert len(events) == workers * per_worker
    assert sequences == list(range(1, workers * per_worker + 1))
    assert len(set(sequences)) == len(sequences)


def test_concurrent_inbox_writes_are_exclusive_and_complete(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "runtime", "inbox-race")
    count = 20
    results: list[Path] = []
    lock = threading.Lock()

    def write(index: int) -> None:
        path = agentctl.write_inbox(paths, "reviewer", f"body-{index}")
        with lock:
            results.append(path)

    threads = [threading.Thread(target=write, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(results) == count
    assert len({path.name for path in results}) == count
    assert sorted(int(path.stem) for path in results) == list(range(1, count + 1))
    assert {path.read_text(encoding="utf-8") for path in results} == {f"body-{index}" for index in range(count)}


# ---------------------------------------------------------------------------
# Log durability
# ---------------------------------------------------------------------------


def test_truncated_final_line_is_skipped_and_append_still_succeeds(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path, "truncated")
    agentctl.append_event(paths, "a", agentctl.EventType.SPAWNED)
    agentctl.append_event(paths, "a", agentctl.EventType.TURN_START)

    with paths.bus.open("a", encoding="utf-8") as handle:
        handle.write('{"ts":"2026-01-01T00:00:00.000Z","run":"trunc","agent":"a","ty')

    events = agentctl.read_events(paths)
    assert [event.type for event in events] == [agentctl.EventType.SPAWNED, agentctl.EventType.TURN_START]

    appended = agentctl.append_event(paths, "a", agentctl.EventType.TURN_END)
    assert appended.seq == 3
    assert [event.seq for event in agentctl.read_events(paths)] == [1, 2, 3]


def test_unknown_event_type_parses_and_round_trips(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path, "forward-compat")
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.bus.write_text(
        json.dumps({"ts": "2026-01-01T00:00:00.000Z", "run": "forward-compat", "agent": "a", "type": "future_thing", "seq": 1, "data": {}}) + "\n",
        encoding="utf-8",
    )

    events = agentctl.read_events(paths)
    assert len(events) == 1
    assert events[0].type is agentctl.EventType.UNKNOWN
    assert events[0].raw_type == "future_thing"
    assert json.loads(events[0].to_line())["type"] == "future_thing"

    assert agentctl.append_event(paths, "a", agentctl.EventType.TURN_END).seq == 2


def test_max_seq_reports_high_water_mark(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path, "watermark")
    assert agentctl.max_seq(paths) == 0
    agentctl.append_event(paths, "a", agentctl.EventType.SPAWNED)
    agentctl.append_event(paths, "a", agentctl.EventType.TURN_START)
    assert agentctl.max_seq(paths) == 2


# ---------------------------------------------------------------------------
# State derivation
# ---------------------------------------------------------------------------


def _events(run: str, agent: str, *types: agentctl.EventType) -> list[agentctl.Event]:
    return [
        agentctl.Event(ts="2026-01-01T00:00:00.000Z", run=run, agent=agent, type=event_type, seq=index, data={})
        for index, event_type in enumerate(types, start=1)
    ]


def _outbox(status: agentctl.OutboxStatus, index: int = 1) -> agentctl.OutboxMessage:
    return agentctl.OutboxMessage(path=Path(f"{index:04d}.md"), index=index, status=status, body="body", meta={"status": status.value})


def test_derive_state_awaiting_human_when_outbox_asks_a_question() -> None:
    events = _events("r", "a", agentctl.EventType.SPAWNED, agentctl.EventType.TURN_START, agentctl.EventType.TURN_END)
    state = agentctl.derive_state(events, [_outbox(agentctl.OutboxStatus.QUESTION)])
    assert state is agentctl.AgentState.AWAITING_HUMAN


def test_derive_state_idle_when_outbox_is_a_plain_reply() -> None:
    events = _events("r", "a", agentctl.EventType.SPAWNED, agentctl.EventType.TURN_START, agentctl.EventType.TURN_END)
    state = agentctl.derive_state(events, [_outbox(agentctl.OutboxStatus.REPLY)])
    assert state is agentctl.AgentState.IDLE


def test_derive_state_busy_while_turn_is_open() -> None:
    events = _events("r", "a", agentctl.EventType.SPAWNED, agentctl.EventType.TURN_START)
    assert agentctl.derive_state(events) is agentctl.AgentState.BUSY


def test_derive_state_dead_after_exit() -> None:
    events = _events("r", "a", agentctl.EventType.SPAWNED, agentctl.EventType.TURN_START, agentctl.EventType.EXIT)
    assert agentctl.derive_state(events, [_outbox(agentctl.OutboxStatus.QUESTION)]) is agentctl.AgentState.DEAD


def test_question_event_marks_awaiting_human_then_clears_on_next_turn() -> None:
    asked = _events(
        "r",
        "a",
        agentctl.EventType.SPAWNED,
        agentctl.EventType.TURN_START,
        agentctl.EventType.QUESTION,
        agentctl.EventType.TURN_END,
    )
    assert agentctl.derive_state(asked) is agentctl.AgentState.AWAITING_HUMAN

    answered = [*asked, *_events("r", "a", agentctl.EventType.TURN_START, agentctl.EventType.TURN_END)]
    for offset, event in enumerate(answered[4:], start=5):
        answered[offset - 1] = agentctl.Event(ts=event.ts, run=event.run, agent=event.agent, type=event.type, seq=offset, data=event.data)
    assert agentctl.derive_state(answered) is agentctl.AgentState.IDLE


def test_refresh_state_cache_writes_derived_state(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path, "cache")
    agentctl.append_event(paths, "a", agentctl.EventType.SPAWNED)
    agentctl.append_event(paths, "a", agentctl.EventType.TURN_START)

    state = agentctl.refresh_state_cache(paths, "a")

    assert state is agentctl.AgentState.BUSY
    assert json.loads(paths.state("a").read_text(encoding="utf-8"))["state"] == "busy"


# ---------------------------------------------------------------------------
# Inbox / outbox
# ---------------------------------------------------------------------------


def test_next_inbox_path_pads_and_never_overwrites(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path, "inbox")
    assert agentctl.next_inbox_path(paths, "a").name == "0001.md"

    agentctl.write_inbox(paths, "a", "first")
    assert agentctl.next_inbox_path(paths, "a").name == "0002.md"

    for _ in range(8):
        agentctl.write_inbox(paths, "a", "filler")
    assert agentctl.next_inbox_path(paths, "a").name == "0010.md"
    assert agentctl.write_inbox(paths, "a", "tenth").read_text(encoding="utf-8") == "tenth"


def test_malformed_outbox_message_is_flagged_not_dropped(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path, "outbox")
    paths.ensure_agent("a")
    (paths.outbox("a") / "0001.md").write_text("---\nstatus: question\n---\nwhich worktree?\n", encoding="utf-8")
    (paths.outbox("a") / "0002.md").write_text("no frontmatter at all\n", encoding="utf-8")
    (paths.outbox("a") / "0003.md").write_text("---\nstatus: nonsense\n---\nbody\n", encoding="utf-8")

    messages = agentctl.read_outbox(paths, "a")

    assert [message.index for message in messages] == [1, 2, 3]
    assert messages[0].status is agentctl.OutboxStatus.QUESTION
    assert messages[0].malformed is False
    assert messages[0].body.strip() == "which worktree?"
    assert messages[1].malformed is True
    assert messages[1].status is agentctl.OutboxStatus.REPLY
    assert messages[2].malformed is True


def test_read_outbox_since_filters_by_index(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path, "since")
    paths.ensure_agent("a")
    for index in range(1, 4):
        (paths.outbox("a") / f"{index:04d}.md").write_text("---\nstatus: reply\n---\nbody\n", encoding="utf-8")

    assert [message.index for message in agentctl.read_outbox(paths, "a", since=1)] == [2, 3]


# ---------------------------------------------------------------------------
# Runtime root resolution
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=test", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "commit", "--allow-empty", "-m", "init")
    return repo


def test_cli_runtime_beats_environment(tmp_path: Path) -> None:
    config = agentctl.Config.from_env({agentctl.ENV_RUNTIME: str(tmp_path / "from-env")})
    resolved = agentctl.resolve_runtime_root(str(tmp_path / "from-cli"), config)
    assert resolved == (tmp_path / "from-cli").resolve()


def test_environment_beats_default(tmp_path: Path, git_repo: Path) -> None:
    config = agentctl.Config.from_env({agentctl.ENV_RUNTIME: str(tmp_path / "from-env")})
    resolved = agentctl.resolve_runtime_root(None, config, cwd=git_repo)
    assert resolved == (tmp_path / "from-env").resolve()


def test_default_runtime_root_lives_outside_the_repository(git_repo: Path) -> None:
    root = agentctl.default_runtime_root(git_repo)

    assert not root.is_relative_to(git_repo)
    assert root.parent == Path(agentctl.DEFAULT_STATE_HOME).expanduser()
    assert root.name.startswith("repo-")


def test_worktree_resolves_the_same_runtime_root_as_the_main_checkout(git_repo: Path, tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    _git(git_repo, "worktree", "add", "--detach", str(worktree), "HEAD")

    assert agentctl.default_runtime_root(worktree) == agentctl.default_runtime_root(git_repo)


def test_resolve_runtime_root_outside_a_repository_is_an_error(tmp_path: Path) -> None:
    config = agentctl.Config.from_env({})
    with pytest.raises(agentctl.BusError):
        agentctl.resolve_runtime_root(None, config, cwd=tmp_path)


# ---------------------------------------------------------------------------
# CLI skeleton
# ---------------------------------------------------------------------------


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        agentctl.main(["--help"])
    assert excinfo.value.code == 0
    assert "agentctl" in capsys.readouterr().out


def test_bare_invocation_prints_help_and_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert agentctl.main([]) == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_seq_command_prints_watermark(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = agentctl.RunPaths.build(tmp_path, "cli")
    agentctl.append_event(paths, "a", agentctl.EventType.SPAWNED)

    assert agentctl.main(["--runtime", str(tmp_path), "--run", "cli", "seq"]) == 0
    assert capsys.readouterr().out.strip() == "1"


def test_seq_without_a_run_id_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert agentctl.main(["--runtime", str(tmp_path), "seq"]) == 1
    assert "run id is required" in capsys.readouterr().err


def test_module_is_executable_as_a_script() -> None:
    completed = subprocess.run([sys.executable, agentctl.__file__, "--version"], capture_output=True, text=True, check=False)
    assert completed.returncode == 0
    assert completed.stdout.startswith("agentctl ")
