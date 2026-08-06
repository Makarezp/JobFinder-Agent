"""Codex provider launch and no-hook lifecycle coverage."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

import agentctl
import pytest


@pytest.fixture
def role(tmp_path: Path) -> Path:
    path = tmp_path / "ROLE.md"
    path.write_text("# Codex reviewer\nInspect carefully.\n", encoding="utf-8")
    return path


def _spawn_codex(tmp_path: Path, role: Path, model: str | None = None) -> tuple[agentctl.RunPaths, agentctl.FakeBackend, agentctl.AgentMeta]:
    paths = agentctl.RunPaths.build(tmp_path / "runtime", "codex-run")
    backend = agentctl.FakeBackend()
    meta = agentctl.spawn_agent(
        paths,
        backend,
        "reviewer",
        role,
        provider="codex",
        claude_binary="/opt/tools/codex",
        model=model,
        cwd=tmp_path,
    )
    return paths, backend, meta


def test_codex_spawn_uses_interactive_codex_argv_and_synthetic_lifecycle(tmp_path: Path, role: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def no_claude_wait(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Codex must not wait for Claude hook events")

    monkeypatch.setattr(agentctl, "wait_for_event", no_claude_wait)
    paths, backend, meta = _spawn_codex(tmp_path, role, model="gpt-5.3-codex")

    argv = backend.windows[meta.handle].cmd
    assert argv[:-1] == [
        "/opt/tools/codex",
        "--cd",
        str(tmp_path.resolve()),
        "--sandbox",
        "workspace-write",
        "--ask-for-approval",
        "never",
        "--model",
        "gpt-5.3-codex",
    ]
    assert argv[-1].startswith("You are an Agent Tabs worker.")
    assert str(paths.inbox("reviewer") / "0001.md") in argv[-1]
    assert "--settings" not in argv
    assert "--setting-sources" not in argv
    assert "--permission-mode" not in argv
    assert not paths.settings("reviewer").exists()
    assert meta.provider == "codex"
    assert json.loads(paths.meta("reviewer").read_text(encoding="utf-8"))["provider"] == "codex"
    assert [event.type for event in agentctl.read_events(paths, "reviewer")] == [agentctl.EventType.SPAWNED, agentctl.EventType.MESSAGE_SENT]
    assert agentctl.read_events(paths, "reviewer")[0].data == {"provider": "codex", "source": "agentctl"}
    assert len(backend.sends) == 1
    assert (paths.inbox("reviewer") / "0001.md").is_file()


def test_codex_rejects_claude_only_options(tmp_path: Path, role: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "runtime", "codex-run")

    with pytest.raises(agentctl.SpawnError, match="permission-mode"):
        agentctl.spawn_agent(
            paths,
            agentctl.FakeBackend(),
            "reviewer",
            role,
            provider="codex",
            claude_binary="/opt/tools/codex",
            permission_mode="bypassPermissions",
        )


def test_explicit_provider_rejects_a_conflicting_binary_before_open(tmp_path: Path, role: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "runtime", "codex-run")
    backend = agentctl.FakeBackend()

    with pytest.raises(agentctl.SpawnError, match="not requested provider codex"):
        agentctl.spawn_agent(paths, backend, "reviewer", role, provider="codex", claude_binary="/opt/tools/claude")

    assert backend.windows == {}


def test_legacy_metadata_without_provider_loads_as_claude(tmp_path: Path) -> None:
    path = tmp_path / "meta.json"
    path.write_text(
        json.dumps(
            {
                "name": "reviewer",
                "role": "/tmp/ROLE.md",
                "handle": "@1",
                "cwd": "/tmp",
                "permission_mode": "acceptEdits",
                "created_at": agentctl.utc_now(),
                "binary": "/opt/bin/claude",
            }
        ),
        encoding="utf-8",
    )

    assert agentctl.AgentMeta.load(path).provider == "claude"


def test_dead_codex_window_is_cleaned_up_and_recorded(tmp_path: Path, role: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "runtime", "codex-run")
    backend = agentctl.FakeBackend()
    monkeypatch.setattr(backend, "alive", lambda _handle: False)

    with pytest.raises(agentctl.SpawnError, match="codex exited before bootstrap"):
        agentctl.spawn_agent(paths, backend, "reviewer", role, provider="codex", claude_binary="/opt/tools/codex")

    assert all(window.alive is False for window in backend.windows.values())
    assert agentctl.read_events(paths, "reviewer")[-1].type is agentctl.EventType.ERROR


def test_codex_composer_fallback_is_fail_open_but_copy_mode_is_not(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "runtime", "codex-run")
    backend = agentctl.FakeBackend()
    handle = backend.open(paths.run, "reviewer", ["codex"], str(tmp_path))
    backend.windows[handle].screen = ["❯ half typed text"]
    paths.ensure_agent("reviewer")
    paths.meta("reviewer").write_text(
        agentctl.AgentMeta(
            name="reviewer",
            role=str(tmp_path / "ROLE.md"),
            handle=handle,
            cwd=str(tmp_path),
            permission_mode="acceptEdits",
            created_at=agentctl.utc_now(),
            binary="codex",
            provider="codex",
        ).to_json(),
        encoding="utf-8",
    )
    agentctl.append_event(paths, "reviewer", agentctl.EventType.SPAWNED)

    assert agentctl.is_ready(paths, backend, "reviewer").ready is True
    backend.windows[handle].in_mode = True
    assert agentctl.is_ready(paths, backend, "reviewer").reason == "copy_mode"


E2E = os.environ.get("AGENT_TABS_E2E") == "1"
needs_codex_e2e = pytest.mark.skipif(
    not (E2E and shutil.which("tmux") and shutil.which("codex")),
    reason="set AGENT_TABS_E2E=1 with tmux and codex present",
)


@needs_codex_e2e
def test_end_to_end_codex_spawn_stays_alive_through_bootstrap(tmp_path: Path, role: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path / "runtime", f"agenttabs-codex-{uuid4().hex[:6]}")
    backend = agentctl.TmuxBackend()
    try:
        meta = agentctl.spawn_agent(paths, backend, "probe", role, provider="codex", cwd=tmp_path)
        assert backend.alive(meta.handle)
        assert (paths.inbox("probe") / "0001.md").is_file()
    finally:
        backend.kill_run(paths.run)
