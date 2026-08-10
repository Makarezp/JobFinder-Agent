"""Isolated system-under-test lifecycle for conformance probes.

T2 live spike, 2026-08-08:

* `spawn` does not return until it sees `spawned`; default bootstrap then waits
  twice for `turn_start` and kills a wrapper that merely blocks. Every puppet
  therefore emits `spawned` first, and `spawn_puppet` passes `--no-doorbell`.
* The spawn API supplies neither caller argv nor custom environment. State and
  duration must be encoded in the generated executable, not passed to `spawn`.
* An unrecognised executable keeps the Claude provider. With `model="haiku"`
  its observed argv was `--settings <generated settings path>
  --permission-mode bypassPermissions --model haiku`; optional
  `--setting-sources ""` appears only with isolated settings. Puppet ignores
  this provider argv entirely.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

RUNTIME_ENV = "AGENT_TABS_RUNTIME"
RUN_ENV = "AGENT_TABS_RUN"
VIEWER_ENV = "AGENT_TABS_VIEWER"
PERMISSION_MODE = "bypassPermissions"
CLAUDE_CONFIG_PATH = Path.home() / ".claude.json"
TOOL_DIR = Path(__file__).resolve().parents[2]

PuppetState = Literal["busy", "deaf", "dirty-composer", "hard-kill"]
PUPPET_STATES = frozenset({"busy", "deaf", "dirty-composer", "hard-kill"})
PUPPET_MODEL = "haiku"
PUPPET_ROLE = TOOL_DIR / "WORKER.md"
PUPPET_PROGRAM = TOOL_DIR / "probe" / "puppet.py"

CMDLOG_HOOK = TOOL_DIR / "probe" / "cmdlog_hook.py"
_PROVIDER_NAME_MARKERS = ("codex", "agy", "claude")


class SutError(RuntimeError):
    """The isolated test environment could not be safely established."""


@dataclass(frozen=True)
class Sut:
    """Paths and environment belonging to one disposable agent-tabs run."""

    runtime: Path
    run: str
    agentctl: Path
    env: dict[str, str]


def create_sut(brief_id: str, *, spacey: bool = False) -> Sut:
    """Create an isolated runtime and mark its workspace as trusted for Claude."""
    prefix = "agent-tabs probe@" if spacey else "agent-tabs-probe-"
    runtime = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
    run = f"sut-{brief_id}-{int(time.time())}"
    try:
        _preseed_workspace_trust(runtime)
    except Exception:
        shutil.rmtree(runtime, ignore_errors=True)
        raise

    env = os.environ.copy()
    env.update({RUNTIME_ENV: str(runtime), RUN_ENV: run, VIEWER_ENV: "none"})
    return Sut(runtime=runtime, run=run, agentctl=TOOL_DIR / "agentctl.py", env=env)


def spawn_command(sut: Sut, name: str, role: Path, task: str, *, model: str | None = None) -> list[str]:
    """Build the only allowed probe spawn invocation.

    The explicit permission mode and trusted, isolated ``cwd`` prevent unseen
    approval and workspace-trust dialogs from invalidating a trial.
    """
    command = [
        sys.executable,
        str(sut.agentctl),
        "spawn",
        name,
        "--role",
        str(role),
        "--task",
        task,
        "--runtime",
        str(sut.runtime),
        "--run",
        sut.run,
        "--cwd",
        str(sut.runtime),
        "--permission-mode",
        PERMISSION_MODE,
        "--viewer",
        "none",
    ]
    if model is not None:
        command.extend(["--model", model])
    return command


def configure_cmdlog(sut: Sut) -> Path:
    """Install the probe-owned Route A hook in this SUT's trusted workspace."""
    command = " ".join(
        shlex.quote(part)
        for part in (
            sys.executable,
            str(CMDLOG_HOOK),
            "--agentctl",
            str(sut.agentctl),
        )
    )
    hooks = {
        hook_name: [
            {
                "matcher": "Bash",
                "hooks": [{"type": "command", "command": f"{command} --phase {phase}"}],
            }
        ]
        for hook_name, phase in (("PreToolUse", "pre"), ("PostToolUse", "post"))
    }
    settings = sut.runtime / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({"hooks": hooks}, indent=2) + "\n", encoding="utf-8")
    return settings


def spawn_puppet(
    sut: Sut,
    name: str,
    state: PuppetState,
    duration: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Start a deterministic fault injector without bootstrap delivery."""
    if state not in PUPPET_STATES:
        raise SutError(f"unknown puppet state {state!r}")
    puppet_duration = 20.0 if duration is None else duration
    if puppet_duration <= 0:
        raise SutError("puppet duration must be positive")

    wrapper = _write_puppet_wrapper(sut, state, puppet_duration)
    _assert_safe_puppet_binary(wrapper)
    command = spawn_command(sut, name, PUPPET_ROLE, "hold a deterministic fault state", model=PUPPET_MODEL)
    command.extend(["--binary", str(wrapper), "--no-doorbell"])
    completed = subprocess.run(command, env=sut.env, text=True, capture_output=True, check=False, timeout=15)
    if completed.returncode != 0:
        raise SutError(f"puppet {name!r} failed to spawn: {completed.stderr.strip()}")
    return completed


def _write_puppet_wrapper(sut: Sut, state: PuppetState, duration: float) -> Path:
    """Encode state in an executable because spawn has no custom argv channel."""
    wrapper = _puppet_wrapper_path(sut, state, duration)
    script = (
        "#!/bin/sh\n"
        f"exec {shlex.quote(sys.executable)} {shlex.quote(str(PUPPET_PROGRAM.resolve()))} "
        f"--state {shlex.quote(state)} --for {duration:g}\n"
    )
    wrapper.write_text(script, encoding="utf-8")
    wrapper.chmod(0o755)
    return wrapper


def _puppet_wrapper_path(sut: Sut, state: PuppetState, duration: float) -> Path:
    return sut.runtime / f"pupp-{state}-{duration:g}"


def _assert_safe_puppet_binary(binary: Path) -> None:
    """Prevent provider inference from treating a wrapper as a real worker CLI."""
    lowered = binary.name.lower()
    if any(marker in lowered for marker in _PROVIDER_NAME_MARKERS):
        raise SutError(f"puppet wrapper name selects a worker provider: {binary.name!r}")


def destroy_sut(sut: Sut, *, preserve: bool) -> Path | None:
    """Close the run, independently kill its tmux session, then clean its files."""
    _run_ignoring_failure(
        [
            sys.executable,
            str(sut.agentctl),
            "close-run",
            "--runtime",
            str(sut.runtime),
            "--run",
            sut.run,
            "--force",
        ],
        env=sut.env,
    )
    _run_ignoring_failure(["tmux", "kill-session", "-t", sut.run], env=sut.env)
    if preserve:
        return sut.runtime
    _remove_workspace_trust(sut.runtime)
    shutil.rmtree(sut.runtime, ignore_errors=True)
    return None


def _run_ignoring_failure(command: list[str], *, env: dict[str, str]) -> None:
    try:
        subprocess.run(command, check=False, capture_output=True, env=env, text=True)
    except OSError:
        pass


def _preseed_workspace_trust(workspace: Path) -> None:
    config = _load_claude_config()
    projects = config.setdefault("projects", {})
    if not isinstance(projects, dict):
        raise SutError("Claude configuration has a non-object projects field")
    entry = projects.setdefault(str(workspace), {})
    if not isinstance(entry, dict):
        raise SutError(f"Claude configuration has a non-object project entry for {workspace}")
    entry["hasTrustDialogAccepted"] = True
    _write_claude_config(config)


def _remove_workspace_trust(workspace: Path) -> None:
    try:
        config = _load_claude_config()
    except SutError:
        return
    projects = config.get("projects")
    if not isinstance(projects, dict):
        return
    entry = projects.get(str(workspace))
    if not isinstance(entry, dict) or entry.get("hasTrustDialogAccepted") is not True:
        return
    del projects[str(workspace)]
    _write_claude_config(config)


def _load_claude_config() -> dict[str, Any]:
    if not CLAUDE_CONFIG_PATH.exists():
        return {}
    try:
        raw: object = json.loads(CLAUDE_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SutError(f"could not read Claude configuration at {CLAUDE_CONFIG_PATH}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SutError(f"Claude configuration at {CLAUDE_CONFIG_PATH} is not an object")
    return raw


def _write_claude_config(config: dict[str, Any]) -> None:
    CLAUDE_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CLAUDE_CONFIG_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    temporary.replace(CLAUDE_CONFIG_PATH)
