"""Claude Bash-hook endpoint that records Route A command observations."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    """Build the standalone hook argument parser."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--agentctl", type=Path, required=True)
    parser.add_argument("--phase", choices=("pre", "post"), required=True)
    return parser


def main() -> int:
    """Append a best-effort hook record without perturbing the worker."""
    args = build_parser().parse_args()
    try:
        payload = _payload()
        record = _record(payload, args.phase)
        if args.phase == "pre":
            record.update(_screen_capture(payload, args.agentctl))
        _append(record)
    except Exception:
        # The probe detects missing or malformed logs as a harness error later.
        # A hook failure must never alter the worker's Bash command behavior.
        pass
    return 0


def _payload() -> dict[str, Any]:
    value = json.load(sys.stdin)
    return value if isinstance(value, dict) else {}


def _record(payload: dict[str, Any], phase: str) -> dict[str, object]:
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    response = payload.get("tool_response") if phase == "post" else None
    return {
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "phase": phase,
        "hook_event": payload.get("hook_event_name"),
        "tool": payload.get("tool_name"),
        "command": command,
        "response": json.dumps(response, ensure_ascii=False) if response is not None else None,
        "session_id": payload.get("session_id"),
        "agent_env": os.environ.get("AGENT_TABS_AGENT"),
        "run_env": os.environ.get("AGENT_TABS_RUN"),
    }


def _screen_capture(payload: dict[str, Any], agentctl: Path) -> dict[str, str]:
    """Capture a screen before the observed read so later comparison has evidence."""
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or "--screen" not in command or "agentctl" not in command:
        return {}
    runtime = os.environ.get("AGENT_TABS_RUNTIME")
    run = os.environ.get("AGENT_TABS_RUN")
    if runtime is None or run is None:
        return {}
    try:
        arguments = _read_arguments(command)
    except ValueError:
        return {}
    if arguments is None:
        return {}
    agent, lines = arguments
    completed = subprocess.run(
        [sys.executable, str(agentctl), "read", agent, "--screen", lines, "--runtime", runtime, "--run", run],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    return {"screen": completed.stdout} if completed.returncode == 0 else {}


def _read_arguments(command: str) -> tuple[str, str] | None:
    """Extract a direct ``agentctl read <agent> --screen <lines>`` call."""

    argv = shlex.split(command)
    for index, value in enumerate(argv):
        if Path(value).name not in {"agentctl", "agentctl.py"}:
            continue
        tail = argv[index + 1 :]
        if "read" not in tail:
            continue
        read_index = tail.index("read")
        arguments = tail[read_index + 1 :]
        if not arguments or "--screen" not in arguments:
            continue
        screen_index = arguments.index("--screen")
        if screen_index + 1 >= len(arguments):
            return None
        return arguments[0], arguments[screen_index + 1]
    return None


def _append(record: dict[str, object]) -> None:
    runtime = os.environ.get("AGENT_TABS_RUNTIME")
    run = os.environ.get("AGENT_TABS_RUN")
    if runtime is None or run is None:
        return
    path = Path(runtime) / run / "commands.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


if __name__ == "__main__":
    raise SystemExit(main())
