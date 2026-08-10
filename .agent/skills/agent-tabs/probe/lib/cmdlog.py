"""Route A command-log parsing for cmdlog-dependent conformance checks."""

from __future__ import annotations

import json
import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from agentctl import RunPaths

from probe.lib.assertions import HarnessError

COMMANDS_PATH = "commands.jsonl"
Phase = Literal["pre", "post"]
_AGENTCTL_COMMANDS = frozenset({"seq", "wait", "read", "send", "spawn", "list", "status", "close", "reap", "close-run", "reply"})


@dataclass(frozen=True)
class CommandRecord:
    """One Bash tool invocation observed by the probe-owned Route A hook."""

    ts: str
    command: str
    agent: str | None
    run: str | None
    phase: Phase
    screen: str | None = None
    response: str | None = None


@dataclass(frozen=True)
class Invocation:
    """An ``agentctl`` subcommand parsed from an observed Bash command."""

    record: CommandRecord
    name: str
    arguments: tuple[str, ...]


def path_for(paths: RunPaths) -> Path:
    """Return the run-local command log path."""
    return paths.root / COMMANDS_PATH


def load(paths: RunPaths) -> list[CommandRecord]:
    """Load a non-empty, structurally valid Route A command log."""
    path = path_for(paths)
    if not path.is_file():
        raise HarnessError(f"command log is missing: {path}")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise HarnessError(f"could not read command log {path}: {error}") from error
    if not lines:
        raise HarnessError(f"command log is empty: {path}")

    records: list[CommandRecord] = []
    for number, line in enumerate(lines, start=1):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise HarnessError(f"command log line {number} is not JSON") from error
        if not isinstance(raw, dict):
            raise HarnessError(f"command log line {number} is not an object")
        records.append(_record(raw, number))
    return records


def invocations(records: Iterable[CommandRecord]) -> list[Invocation]:
    """Extract one directly invoked ``agentctl`` subcommand from each record."""
    extracted: list[Invocation] = []
    for record in records:
        invocation = _invocation(record)
        if invocation is not None:
            extracted.append(invocation)
    return extracted


def option(arguments: tuple[str, ...], name: str) -> str | None:
    """Return an option's value when it appears as a separate argv element."""
    try:
        index = arguments.index(name)
    except ValueError:
        return None
    if index + 1 >= len(arguments):
        return None
    return arguments[index + 1]


def positional(arguments: tuple[str, ...], index: int) -> str | None:
    """Return positional argv while skipping known agentctl option values."""
    values: list[str] = []
    skip_next = False
    options_with_values = {
        "--runtime",
        "--run",
        "--backend",
        "--until",
        "--timeout",
        "--from-seq",
        "--screen",
        "--since",
        "--file",
        "--wait-idle",
        "--stalled-after",
    }
    for argument in arguments:
        if skip_next:
            skip_next = False
            continue
        if argument in options_with_values:
            skip_next = True
            continue
        if argument.startswith("-"):
            continue
        values.append(argument)
    return values[index] if len(values) > index else None


def timestamp(record: CommandRecord) -> datetime | None:
    """Parse the hook timestamp without turning an old malformed log into a finding."""
    try:
        return datetime.fromisoformat(record.ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _record(raw: dict[str, object], number: int) -> CommandRecord:
    ts = raw.get("ts")
    command = raw.get("command")
    if not isinstance(ts, str) or not ts:
        raise HarnessError(f"command log line {number} has no timestamp")
    if not isinstance(command, str) or not command:
        raise HarnessError(f"command log line {number} has no command")
    raw_phase = raw.get("phase", "pre")
    if raw_phase == "pre":
        phase: Phase = "pre"
    elif raw_phase == "post":
        phase = "post"
    else:
        raise HarnessError(f"command log line {number} has invalid phase")
    agent = raw.get("agent_env")
    run = raw.get("run_env")
    screen = raw.get("screen")
    response = raw.get("response")
    if agent is not None and not isinstance(agent, str):
        raise HarnessError(f"command log line {number} has invalid agent")
    if run is not None and not isinstance(run, str):
        raise HarnessError(f"command log line {number} has invalid run")
    if screen is not None and not isinstance(screen, str):
        raise HarnessError(f"command log line {number} has invalid screen")
    if response is not None and not isinstance(response, str):
        raise HarnessError(f"command log line {number} has invalid response")
    return CommandRecord(ts=ts, command=command, agent=agent, run=run, phase=phase, screen=screen, response=response)


def _invocation(record: CommandRecord) -> Invocation | None:
    try:
        argv = shlex.split(record.command)
    except ValueError:
        return None
    for index, argument in enumerate(argv):
        if Path(argument).name not in {"agentctl", "agentctl.py"}:
            continue
        for command_index, candidate in enumerate(argv[index + 1 :], start=index + 1):
            if candidate in _AGENTCTL_COMMANDS:
                return Invocation(record=record, name=candidate, arguments=tuple(argv[command_index + 1 :]))
    return None
