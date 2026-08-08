"""Build a probe-controlled working directory for T5 Step 0, Route A.

The directory name deliberately contains BOTH a space and an '@' -- the exact
shape that made Iteration 1's review finding B1 fail silently. Every element of
the hook command is shlex.quote()d, mirroring hook_command() at agentctl.py:1132.
"""

from __future__ import annotations

import json
import shlex
import stat
import sys
from pathlib import Path

CWD = Path("/tmp/probe cwd@spike")
LOG = CWD / "commands.jsonl"
LOGGER = CWD / "log_cmd.py"

LOGGER_SRC = """\
import json, sys, datetime, os
try:
    payload = json.load(sys.stdin)
except Exception:
    payload = {}
rec = {
    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
    "hook_event": payload.get("hook_event_name"),
    "tool": payload.get("tool_name"),
    "command": (payload.get("tool_input") or {}).get("command"),
    "cwd": payload.get("cwd"),
    "session_id": payload.get("session_id"),
    "agent_env": os.environ.get("AGENT_TABS_AGENT"),
    "run_env": os.environ.get("AGENT_TABS_RUN"),
}
with open(%(log)s, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec) + "\\n")
# never perturb the subject: always succeed, emit nothing
sys.exit(0)
"""


def main() -> int:
    CWD.mkdir(parents=True, exist_ok=True)
    (CWD / ".claude").mkdir(exist_ok=True)

    LOGGER.write_text(LOGGER_SRC % {"log": repr(str(LOG))}, encoding="utf-8")
    LOGGER.chmod(LOGGER.stat().st_mode | stat.S_IEXEC)

    command = " ".join(shlex.quote(part) for part in [sys.executable, str(LOGGER)])

    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": command}],
                }
            ]
        }
    }
    target = CWD / ".claude" / "settings.json"
    target.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    print("cwd        :", CWD)
    print("  has space:", " " in str(CWD))
    print("  has @    :", "@" in str(CWD))
    print("settings   :", target)
    print("hook cmd   :", command)
    print("log        :", LOG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
