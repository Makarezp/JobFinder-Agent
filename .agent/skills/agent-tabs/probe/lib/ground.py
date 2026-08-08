"""Ground-truth readers for the probe harness.

These readers intentionally do not reuse agentctl's read or state-derivation
paths: a probe must not grade the subject through the subject's own parser.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from agentctl import Event, EventType, OutboxMessage, OutboxStatus, RunPaths

from probe.lib.sut import Sut

DEFAULT_PROVIDER = "claude"


def events(sut: Sut | RunPaths, agent: str | None = None, type: EventType | None = None) -> list[Event]:
    """Parse a run's bus directly, retaining newer unknown event types."""
    paths = _paths(sut)
    if not paths.bus.is_file():
        return []

    parsed: list[Event] = []
    for line in paths.bus.read_text(encoding="utf-8").splitlines():
        event = _parse_event(line)
        if event is not None and (agent is None or event.agent == agent) and (type is None or event.type is type):
            parsed.append(event)
    return sorted(parsed, key=lambda event: event.seq)


def provider(sut: Sut | RunPaths, agent: str) -> str:
    """Return a recorded provider, matching agentctl's legacy Claude default."""
    meta_path = _paths(sut).meta(agent)
    if not meta_path.is_file():
        return DEFAULT_PROVIDER
    try:
        raw: object = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_PROVIDER
    if not isinstance(raw, dict):
        return DEFAULT_PROVIDER
    value = raw.get("provider")
    return value if isinstance(value, str) and value else DEFAULT_PROVIDER


def session_exists(run: str) -> bool:
    """Check tmux directly; a missing server or session is simply absent."""
    completed = subprocess.run(
        ["tmux", "has-session", "-t", run],
        capture_output=True,
        check=False,
        text=True,
    )
    return completed.returncode == 0


def inbox_files(sut: Sut | RunPaths, agent: str) -> list[Path]:
    """List an agent's durable inbox files in delivery order."""
    directory = _paths(sut).inbox(agent)
    return sorted(directory.glob("*.md")) if directory.is_dir() else []


def outbox_messages(sut: Sut | RunPaths, agent: str) -> list[OutboxMessage]:
    """Parse an agent's outbox directly, including malformed status metadata."""
    directory = _paths(sut).outbox(agent)
    if not directory.is_dir():
        return []
    messages: list[OutboxMessage] = []
    for path in sorted(directory.glob("*.md")):
        try:
            index = int(path.stem)
        except ValueError:
            continue
        metadata, body = _frontmatter(path.read_text(encoding="utf-8"))
        status = OutboxStatus.parse(metadata.get("status", ""))
        messages.append(
            OutboxMessage(
                path=path,
                index=index,
                status=status or OutboxStatus.REPLY,
                body=body,
                meta=metadata,
                malformed=status is None,
            )
        )
    return messages


def windows(sut: Sut | RunPaths) -> list[str]:
    """List tmux window IDs directly, returning no windows when the session is gone."""
    paths = _paths(sut)
    completed = subprocess.run(
        ["tmux", "list-windows", "-t", paths.run, "-F", "#{window_id}"],
        capture_output=True,
        check=False,
        text=True,
    )
    return completed.stdout.splitlines() if completed.returncode == 0 else []


def screen(sut: Sut | RunPaths, agent: str, lines: int) -> str:
    """Capture a worker pane for observation only."""
    paths = _paths(sut)
    completed = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", f"{paths.run}:{agent}", "-S", f"-{lines}"],
        capture_output=True,
        check=False,
        text=True,
    )
    return completed.stdout if completed.returncode == 0 else ""


def _paths(sut: Sut | RunPaths) -> RunPaths:
    return sut if isinstance(sut, RunPaths) else RunPaths.build(sut.runtime, sut.run)


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    metadata: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return metadata, "\n".join(lines[index + 1 :]).lstrip("\n")
        key, separator, value = line.partition(":")
        if separator:
            metadata[key.strip()] = value.strip()
    return {}, text


def _parse_event(line: str) -> Event | None:
    try:
        raw: object = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    payload = raw.get("data")
    if not isinstance(payload, dict):
        payload = {}
    raw_type = raw.get("type")
    raw_type_text = raw_type if isinstance(raw_type, str) else ""
    try:
        event_type = EventType(raw_type_text)
    except ValueError:
        event_type = EventType.UNKNOWN
    return Event(
        ts=_text(raw, "ts"),
        run=_text(raw, "run"),
        agent=_text(raw, "agent"),
        type=event_type,
        seq=_integer(raw.get("seq")),
        data=_data(payload),
        raw_type=raw_type_text,
    )


def _text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _integer(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _data(payload: dict[Any, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if isinstance(key, str)}
