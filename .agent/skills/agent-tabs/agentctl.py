#!/usr/bin/env python3
"""agentctl -- launch, message and observe human-visible agent sessions.

Two layers so far:

* the bus -- durable run directories, an append-only event log, and agent state
  derived purely from that log;
* the backend -- every terminal-specific operation, behind one small interface
  so that supporting a different terminal means writing one class.

Deliberately stdlib-only. This tool must run in any repository, with or without
a virtualenv, and is intended to be lifted into its own repo unchanged.
"""

from __future__ import annotations

import sys

# Must run before the 3.11+ imports below, or the failure a user sees is
# `ImportError: cannot import name 'StrEnum'` -- true, but it says nothing about
# the cause. This tool is meant to be dropped into any repository, so the
# interpreter it lands on is exactly the thing that varies.
# noqa: UP036 is required: ruff targets py311 and so reads this as dead code.
if sys.version_info < (3, 11):  # noqa: UP036
    raise SystemExit(f"agentctl requires Python 3.11+, found {sys.version.split()[0]} at {sys.executable}")

import argparse
import fcntl
import hashlib
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__version__ = "0.1.0"

log = logging.getLogger("agentctl")

ENV_RUNTIME = "AGENT_TABS_RUNTIME"
ENV_RUN = "AGENT_TABS_RUN"
ENV_AGENT = "AGENT_TABS_AGENT"
ENV_BACKEND = "AGENT_TABS_BACKEND"
ENV_VIEWER = "AGENT_TABS_VIEWER"

DEFAULT_STATE_HOME = "~/.local/state/agent-tabs"
DEFAULT_BACKEND = "tmux"
# On macOS, make the human-visible experience the default. `none` remains
# available through --viewer none or AGENT_TABS_VIEWER=none for headless runs.
DEFAULT_VIEWER = "iterm-tab"
AGY_BOOT_DELAY = 1.5

INBOX_WIDTH = 4
REPO_HASH_WIDTH = 12


class AgentTabsError(Exception):
    """Base class for every error this tool raises deliberately."""


class BusError(AgentTabsError):
    """The on-disk bus could not be resolved, read or written."""


# ---------------------------------------------------------------------------
# Configuration -- the single point at which the environment is read.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Environment-derived settings.

    This is the only place in the tool that reads environment variables. The
    project's own ``Settings`` singleton cannot be used here: agentctl must run
    in repositories that have no virtualenv and no application code at all.
    """

    runtime_root: Path | None
    run: str | None
    agent: str | None
    backend: str
    viewer: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        source = os.environ if env is None else env
        raw_root = source.get(ENV_RUNTIME)
        return cls(
            runtime_root=Path(raw_root).expanduser() if raw_root else None,
            run=source.get(ENV_RUN),
            agent=source.get(ENV_AGENT),
            backend=source.get(ENV_BACKEND, DEFAULT_BACKEND),
            viewer=source.get(ENV_VIEWER, DEFAULT_VIEWER),
        )


# ---------------------------------------------------------------------------
# Runtime root resolution
# ---------------------------------------------------------------------------


def git_common_dir(cwd: Path | None = None) -> Path:
    """Absolute path of the *main* repository's .git directory.

    ``--git-common-dir`` is used rather than ``--show-toplevel`` on purpose:
    inside a linked worktree the latter returns the worktree, which would give
    an agent running in a worktree a different runtime root from the
    orchestrator that spawned it.
    """
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:  # git binary missing
        raise BusError(f"could not run git: {exc}") from exc
    if completed.returncode != 0:
        raise BusError(f"not inside a git repository ({completed.stderr.strip()})")
    return Path(completed.stdout.strip()).resolve()


def default_runtime_root(cwd: Path | None = None) -> Path:
    """Runtime root outside the repository and outside any cloud-synced tree.

    The runtime tree holds a high-churn append-only log and git worktrees. Both
    are hostile to file-syncing daemons, and the tree bakes absolute paths, so
    it is disposable rather than portable. Keeping it out of the repo makes that
    true by construction instead of by discipline.
    """
    common = git_common_dir(cwd)
    repo_dir = common.parent if common.name == ".git" else common
    digest = hashlib.sha1(str(common).encode("utf-8")).hexdigest()[:REPO_HASH_WIDTH]
    return Path(DEFAULT_STATE_HOME).expanduser() / f"{repo_dir.name}-{digest}"


def resolve_runtime_root(cli_runtime: str | None = None, config: Config | None = None, cwd: Path | None = None) -> Path:
    """Resolve the runtime root: --runtime, then the environment, then the default.

    The orchestrator resolves this once and passes it explicitly to every
    worker. Nothing running inside a worker may re-derive it.
    """
    if cli_runtime:
        return Path(cli_runtime).expanduser().resolve()
    cfg = config if config is not None else Config.from_env()
    if cfg.runtime_root is not None:
        return cfg.runtime_root.resolve()
    return default_runtime_root(cwd)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunPaths:
    """Every path belonging to one run. Constructed, never guessed at call sites."""

    root: Path
    run: str

    @classmethod
    def build(cls, runtime_root: Path | str, run: str) -> RunPaths:
        return cls(root=Path(runtime_root).expanduser().resolve() / run, run=run)

    @property
    def runtime_root(self) -> Path:
        return self.root.parent

    @property
    def bus(self) -> Path:
        return self.root / "bus.jsonl"

    @property
    def worktrees(self) -> Path:
        return self.root / "worktrees"

    def agent_dir(self, agent: str) -> Path:
        return self.root / "agents" / agent

    def meta(self, agent: str) -> Path:
        return self.agent_dir(agent) / "meta.json"

    def state(self, agent: str) -> Path:
        return self.agent_dir(agent) / "state.json"

    def settings(self, agent: str) -> Path:
        return self.agent_dir(agent) / "settings.json"

    def inbox(self, agent: str) -> Path:
        return self.agent_dir(agent) / "inbox"

    def outbox(self, agent: str) -> Path:
        return self.agent_dir(agent) / "outbox"

    def ensure_agent(self, agent: str) -> None:
        self.inbox(agent).mkdir(parents=True, exist_ok=True)
        self.outbox(agent).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


class EventType(StrEnum):
    SPAWNED = "spawned"
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    MESSAGE_SENT = "message_sent"
    REPLY = "reply"
    BLOCKED = "blocked"
    QUESTION = "question"
    EXIT = "exit"
    ERROR = "error"
    UNKNOWN = "__unknown__"

    @classmethod
    def parse(cls, value: str) -> EventType:
        """Map an on-disk value to a member, never raising.

        A log written by a newer version of this tool must remain readable by an
        older one; an unrecognised type degrades to UNKNOWN and the raw string is
        preserved on the event.
        """
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN


REPORT_TYPES = frozenset({EventType.REPLY, EventType.QUESTION, EventType.BLOCKED})
HALT_TYPES = frozenset({EventType.QUESTION, EventType.BLOCKED})


def utc_now() -> str:
    """UTC ISO-8601 with millisecond precision and a Z suffix."""
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


@dataclass(frozen=True)
class Event:
    ts: str
    run: str
    agent: str
    type: EventType
    seq: int
    data: dict[str, Any]
    raw_type: str = ""

    def wire_type(self) -> str:
        return self.raw_type or self.type.value

    def to_line(self) -> str:
        payload = {
            "ts": self.ts,
            "run": self.run,
            "agent": self.agent,
            "type": self.wire_type(),
            "seq": self.seq,
            "data": self.data,
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_obj(cls, obj: dict[str, Any]) -> Event:
        raw = str(obj.get("type", ""))
        return cls(
            ts=str(obj.get("ts", "")),
            run=str(obj.get("run", "")),
            agent=str(obj.get("agent", "")),
            type=EventType.parse(raw),
            seq=int(obj.get("seq", 0)),
            data=obj.get("data") or {},
            raw_type=raw,
        )


def _parse_line(line: str) -> Event | None:
    """Parse one log line, returning None for anything unusable.

    A process killed mid-write leaves a truncated final line. That must never
    prevent the rest of the log from being read, nor block the next append.
    """
    text = line.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        log.debug("skipping unparseable bus line: %.80s", text)
        return None
    if not isinstance(obj, dict):
        return None
    return Event.from_obj(obj)


def read_events(paths: RunPaths, agent: str | None = None) -> list[Event]:
    """All events for a run, in sequence order, skipping corrupt lines."""
    if not paths.bus.exists():
        return []
    events: list[Event] = []
    with paths.bus.open("r", encoding="utf-8") as handle:
        for line in handle:
            event = _parse_line(line)
            if event is None:
                continue
            if agent is None or event.agent == agent:
                events.append(event)
    events.sort(key=lambda item: item.seq)
    return events


def append_event(paths: RunPaths, agent: str, event_type: EventType, data: dict[str, Any] | None = None) -> Event:
    """Append one event under an exclusive lock, assigning the next sequence.

    macOS ships no flock(1) binary, so the stdlib fcntl call is used directly.
    The sequence number is assigned inside the lock, which is what makes it
    safe for hooks in several independent agent processes to write at once.
    """
    paths.root.mkdir(parents=True, exist_ok=True)
    with paths.bus.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            last_seq = 0
            terminated = True
            for line in handle:
                # A process killed mid-write leaves a final line with no newline.
                # Appending straight onto it would splice the two records together
                # and lose *this* event as well as the damaged one.
                terminated = line.endswith("\n")
                existing = _parse_line(line)
                if existing is not None and existing.seq > last_seq:
                    last_seq = existing.seq
            event = Event(
                ts=utc_now(),
                run=paths.run,
                agent=agent,
                type=event_type,
                seq=last_seq + 1,
                data=data or {},
            )
            handle.seek(0, os.SEEK_END)
            handle.write(("" if terminated else "\n") + event.to_line() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return event


def max_seq(paths: RunPaths) -> int:
    """Current high-water mark, for callers that need a watermark before sending."""
    events = read_events(paths)
    return events[-1].seq if events else 0


# ---------------------------------------------------------------------------
# Outbox
# ---------------------------------------------------------------------------


class OutboxStatus(StrEnum):
    REPLY = "reply"
    QUESTION = "question"
    BLOCKED = "blocked"

    @classmethod
    def parse(cls, value: str) -> OutboxStatus | None:
        try:
            return cls(value.strip().lower())
        except ValueError:
            return None


@dataclass(frozen=True)
class OutboxMessage:
    path: Path
    index: int
    status: OutboxStatus
    body: str
    meta: dict[str, str]
    malformed: bool = False


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a leading ``---`` delimited block from the body.

    Hand-rolled rather than using PyYAML: the tool takes no third-party
    dependencies, and the frontmatter here is a flat string-to-string map.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "\n".join(lines[index + 1 :]).lstrip("\n")
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return {}, text  # unterminated block -- treat the whole file as body


def read_outbox(paths: RunPaths, agent: str, since: int = 0) -> list[OutboxMessage]:
    """Outbox messages in index order.

    A message whose status is missing or unrecognised is returned flagged as
    malformed and defaulted to ``reply`` -- never silently dropped, because a
    dropped message is an instruction the orchestrator will wait on forever.
    """
    directory = paths.outbox(agent)
    if not directory.exists():
        return []
    messages: list[OutboxMessage] = []
    for path in sorted(directory.glob("*.md")):
        try:
            index = int(path.stem)
        except ValueError:
            continue
        if index <= since:
            continue
        text = path.read_text(encoding="utf-8")
        meta, body = _parse_frontmatter(text)
        status = OutboxStatus.parse(meta.get("status", ""))
        messages.append(
            OutboxMessage(
                path=path,
                index=index,
                status=status or OutboxStatus.REPLY,
                body=body,
                meta=meta,
                malformed=status is None,
            )
        )
    return messages


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


def next_inbox_path(paths: RunPaths, agent: str) -> Path:
    """Next free zero-padded inbox filename. Never overwrites an existing message."""
    directory = paths.inbox(agent)
    directory.mkdir(parents=True, exist_ok=True)
    highest = 0
    for path in directory.glob("*.md"):
        try:
            highest = max(highest, int(path.stem))
        except ValueError:
            continue
    return directory / f"{highest + 1:0{INBOX_WIDTH}d}.md"


def write_inbox(paths: RunPaths, agent: str, body: str) -> Path:
    directory = paths.inbox(agent)
    directory.mkdir(parents=True, exist_ok=True)
    candidate = next_inbox_path(paths, agent)
    while True:
        try:
            with candidate.open("x", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            return candidate
        except FileExistsError:
            candidate = directory / f"{int(candidate.stem) + 1:0{INBOX_WIDTH}d}.md"


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(StrEnum):
    IDLE = "idle"
    BUSY = "busy"
    AWAITING_HUMAN = "awaiting_human"
    DEAD = "dead"


def derive_state(events: Sequence[Event], outbox: Sequence[OutboxMessage] = ()) -> AgentState:
    """Agent state as a pure function of the event stream.

    ``state.json`` is a cache of this and never a source of truth: any read path
    that cannot fall back to replaying the log is a bug.

    A report (reply/question/blocked) only counts while it is newer than the
    most recent ``turn_start``, so answering a question in the pane clears
    ``awaiting_human`` on the agent's next turn rather than latching forever.
    The outbox is consulted only when no report events exist at all, which is
    the fallback tier for workers whose hooks are not wired.
    """
    state = AgentState.IDLE
    last_turn_start = 0
    pending: EventType | None = None
    saw_report = False

    for event in sorted(events, key=lambda item: item.seq):
        if event.type is EventType.TURN_START:
            state = AgentState.BUSY
            last_turn_start = event.seq
            pending = None
        elif event.type is EventType.TURN_END:
            state = AgentState.IDLE
        elif event.type is EventType.SPAWNED:
            state = AgentState.IDLE
        elif event.type in (EventType.EXIT, EventType.ERROR):
            state = AgentState.DEAD
        elif event.type in REPORT_TYPES:
            saw_report = True
            if event.seq > last_turn_start:
                pending = event.type

    if state is AgentState.DEAD:
        return state

    if pending in HALT_TYPES:
        return AgentState.AWAITING_HUMAN

    if not saw_report and outbox and state is AgentState.IDLE:
        newest = max(outbox, key=lambda item: item.index)
        if newest.status in (OutboxStatus.QUESTION, OutboxStatus.BLOCKED):
            return AgentState.AWAITING_HUMAN

    return state


def refresh_state_cache(paths: RunPaths, agent: str) -> AgentState:
    """Recompute state from the log and write the cache. Returns the new state."""
    state = derive_state(read_events(paths, agent), read_outbox(paths, agent))
    paths.ensure_agent(agent)
    paths.state(agent).write_text(
        json.dumps({"state": state.value, "updated_at": utc_now()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return state


# ---------------------------------------------------------------------------
# Backends
#
# Everything terminal-specific lives below this line. Nothing above it, and
# nothing in the CLI, may invoke a terminal directly: a second call site would
# defeat the whole point of the interface.
# ---------------------------------------------------------------------------


class BackendError(AgentTabsError):
    """A terminal operation failed."""


class BackendUnavailable(BackendError):
    """The terminal program is not installed."""


@dataclass(frozen=True)
class WindowInfo:
    """A live window: its stable handle and the name shown to the human."""

    handle: str
    name: str


@runtime_checkable
class Backend(Protocol):
    """The complete terminal-specific surface.

    Handles are opaque to callers. For tmux they are window ids, which are
    unique for the lifetime of the server; window *names* are display only.
    """

    def open(self, run: str, name: str, cmd: Sequence[str], cwd: str, env: Mapping[str, str] | None = None) -> str: ...

    def send(self, handle: str, text: str, enter: bool = True) -> None: ...

    def capture(self, handle: str, lines: int = 50, escape: bool = False) -> str: ...

    def in_mode(self, handle: str) -> bool: ...

    def kill(self, handle: str) -> None: ...

    def alive(self, handle: str) -> bool: ...

    def list_handles(self, run: str) -> list[WindowInfo]: ...

    def kill_run(self, run: str) -> None: ...


class ViewerError(AgentTabsError):
    """A viewer could not reveal a window to the human."""


@runtime_checkable
class Viewer(Protocol):
    """Attaches a human's terminal to an already-open window.

    Orthogonal to ``Backend``: a viewer knows only a run id and an opaque
    handle, never how the window was created. It must never call ``backend.*``
    directly, and ``Backend`` must never grow a ``reveal`` method -- the two
    abstractions (how an agent lives in tmux, how a human sees it) stay
    separate on purpose.
    """

    def reveal(self, run: str, handle: str) -> None: ...


class NullViewer:
    """Today's behaviour: nothing happens, the window stays detached."""

    def reveal(self, run: str, handle: str) -> None:
        return None


class ItermTabViewer:
    """Opens a new iTerm tab in the current window, attached to one agent.

    Drives iTerm the same way ``launch-agents.sh`` does (AppleScript via
    ``osascript``), but only for the "open a tab and attach" half -- the
    agent is already up (T3's readiness handshake proved it); this never
    re-launches or re-bootstraps anything.

    Deliberately a plain ``tmux attach``, not ``tmux -CC``: control mode
    attaches to the whole session as a batch of native tabs, a different
    workflow this viewer does not build. Mixing the two against the same
    session in the same iTerm window is a real footgun -- see SKILL.md.
    """

    def __init__(self, runner: Callable[[str], subprocess.CompletedProcess[str]] | None = None) -> None:
        self._runner = runner or self._osascript

    @staticmethod
    def _osascript(script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["osascript", "-"], input=script, text=True, capture_output=True, check=False)

    @staticmethod
    def _applescript_escape(text: str) -> str:
        # Same rule as launch-agents.sh's esc(): backslash first, then the
        # double-quote that would otherwise close the AppleScript string early.
        return text.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _shell_quote(value: str) -> str:
        # Deliberately not shlex.quote(): that implements POSIX-sh quoting,
        # which treats a leading '=' as safe and leaves it unquoted. But the
        # shell that actually runs this line is the human's interactive
        # shell -- zsh by default on macOS -- which has a non-POSIX
        # extension: an unquoted word starting with '=' undergoes "equals
        # expansion" ('=cmd' -> full path of cmd on $PATH, erroring if not
        # found). Every tmux target this viewer builds is '=<run>', so an
        # unquoted target breaks for every run, not just adversarial ones --
        # this was caught by a live spawn against a real zsh, not by any
        # string-level test. Always single-quoting sidesteps zsh's expansion
        # unconditionally, regardless of what any one shell's quoting rules
        # consider "safe".
        return "'" + value.replace("'", "'\\''") + "'"

    def reveal(self, run: str, handle: str) -> None:
        if shutil.which("osascript") is None:
            raise ViewerError("osascript is not installed or not on PATH (iTerm viewer is macOS-only)")

        # TMUX= clears the env var the new tab would otherwise inherit if
        # agentctl itself runs inside a tmux client -- without it, tmux
        # refuses with "sessions should be nested with care" on every reveal.
        # Only the target and handle are shell-quoted; ';' is tmux's own
        # command separator, not the shell's -- it must reach tmux as a
        # single literal argument, so it is itself escaped from the *shell*
        # that will run this line (`\;`), not passed through shell quoting.
        # An unescaped ' ; ' here is a real, live-tested bug: the shell reads
        # it as its own separator and splits the line into two commands,
        # the second of which ("select-window ...") is not a program.
        command = f"TMUX= tmux attach -t {self._shell_quote(tmux_target(run))} \\; select-window -t {self._shell_quote(handle)}"
        escaped = self._applescript_escape(command)
        script = (
            'tell application "iTerm"\n'
            "  activate\n"
            "  if (count of windows) = 0 then create window with default profile\n"
            "  tell current window\n"
            "    set s to (current session of (create tab with default profile))\n"
            "    tell s\n"
            f'      write text "{escaped}"\n'
            "    end tell\n"
            "  end tell\n"
            "end tell\n"
        )
        completed = self._runner(script)
        if completed.returncode != 0:
            raise ViewerError(f"osascript failed to open an iTerm tab: {completed.stderr.strip()}")


VIEWERS: dict[str, type[Viewer]] = {"none": NullViewer, "iterm-tab": ItermTabViewer}


def get_viewer(name: str | None = None, config: Config | None = None) -> Viewer:
    """Construct a viewer by name: --viewer, then env, then iTerm tabs."""
    cfg = config if config is not None else Config.from_env()
    chosen = name or cfg.viewer
    try:
        factory = VIEWERS[chosen]
    except KeyError as exc:
        raise ViewerError(f"unknown viewer {chosen!r}; available: {', '.join(sorted(VIEWERS))}") from exc
    return factory()


ROOT_WINDOW = "__root__"


def tmux_target(run: str) -> str:
    # '=' forces an exact match, so a run named 'cvv' never resolves to 'cvv-hotfix'.
    # Shared by TmuxBackend and any viewer that also attaches by run id, so the
    # exact-match rule lives in exactly one place.
    return f"={run}"


class TmuxBackend:
    """tmux driver.

    Verified against tmux 3.7b:

    * ``new-window ... -- argv...`` is a true exec vector, not a joined shell
      string: an argument containing a space stays one argument, ``$VAR`` is not
      expanded and a leading dash is not consumed. Injection safety therefore
      holds at the tmux boundary and not merely at the subprocess one.
    * ``send-keys -l --`` delivers text byte-identically, including ``$``,
      backticks and leading dashes.
    * ``-n <name>`` sets ``automatic-rename off`` on that window, so a name
      chosen at creation is not rewritten by the running process.

    Window *names* are nonetheless not unique -- two windows may share one, and
    ``-t session:name`` then silently resolves to whichever comes first. That is
    an orchestrator talking to the wrong agent with no error, so handles are
    always window ids.
    """

    def __init__(self, binary: str = "tmux") -> None:
        self._binary = binary
        self._resolved: str | None = None
        self._last_repaint: dict[str, float] = {}

    def _exe(self) -> str:
        if self._resolved is None:
            found = shutil.which(self._binary)
            if found is None:
                raise BackendUnavailable(f"{self._binary} is not installed or not on PATH")
            self._resolved = found
        return self._resolved

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([self._exe(), *args], capture_output=True, text=True, check=False)

    def _tmux(self, *args: str) -> str:
        completed = self._run(*args)
        if completed.returncode != 0:
            raise BackendError(f"tmux {' '.join(args)} failed: {completed.stderr.strip()}")
        return completed.stdout

    @staticmethod
    def _target(run: str) -> str:
        return tmux_target(run)

    def _session_exists(self, run: str) -> bool:
        return self._run("has-session", "-t", self._target(run)).returncode == 0

    def open(self, run: str, name: str, cmd: Sequence[str], cwd: str, env: Mapping[str, str] | None = None) -> str:
        if not self._session_exists(run):
            self._tmux("new-session", "-d", "-s", run, "-n", ROOT_WINDOW)
        args = ["new-window", "-P", "-F", "#{window_id}", "-d", "-t", self._target(run), "-n", name, "-c", cwd]
        for key, value in (env or {}).items():
            args += ["-e", f"{key}={value}"]
        args += ["--", *cmd]
        handle = self._tmux(*args).strip()
        if not handle:
            raise BackendError(f"tmux did not return a window id for {name!r}")
        return handle

    def send(self, handle: str, text: str, enter: bool = True) -> None:
        # -l sends the text literally; without it a newline in the payload would
        # submit a half-written prompt. Enter is always a separate, deliberate act.
        self._tmux("send-keys", "-t", handle, "-l", "--", text)
        if enter:
            self._tmux("send-keys", "-t", handle, "Enter")

    def capture(self, handle: str, lines: int = 50, escape: bool = False) -> str:
        # -S -N starts N lines above the *top* of the visible pane and captures
        # through to the bottom, so tmux returns N + pane_height lines. Slice to
        # honour the parameter's name.
        # Panes in an *unattached* session do not repaint on their own: Claude
        # Code defers rendering when nobody is watching, so tmux's server-side
        # copy of the pane stays blank or stale. A resize round-trip (SIGWINCH)
        # forces a full redraw; without it the composer gate and the spawn
        # diagnostics would read nothing. `escape` preserves the SGR codes the
        # composer placeholder discriminator needs.
        if self._attached(handle) != "1":
            self._force_repaint(handle)
        flags = ["capture-pane", "-p", "-t", handle, "-S", f"-{lines}"]
        if escape:
            flags.append("-e")
        raw = self._tmux(*flags)
        captured = raw.splitlines()
        # -S -N returns N history lines plus the whole visible pane. A fresh
        # pane has no scrollback yet, so the output is just the visible pane
        # and can be shorter than `lines`; slicing unconditionally would then
        # discard the pane's top (a 76-line pane loses its first 26 lines).
        # Only slice when there is more output than requested.
        return "\n".join(captured[-lines:] if len(captured) > lines else captured)

    def _attached(self, handle: str) -> str:
        """'1' when a client is attached to the pane's session, else '0'."""
        try:
            return self._tmux("display-message", "-p", "-t", handle, "#{session_attached}").strip()
        except BackendError:
            return "1"  # unknown (pane gone): never resize a dead window

    def _force_repaint(self, handle: str) -> None:
        """Resize round-trip on an unattached pane so its program redraws.

        Throttled: the readiness poll calls capture repeatedly, and each
        repaint makes the worker redraw a frame.
        """
        now = time.monotonic()
        if now - self._last_repaint.get(handle, 0.0) < REPAINT_THROTTLE:
            return
        self._last_repaint[handle] = now
        try:
            width = self._tmux("display-message", "-p", "-t", handle, "#{window_width}").strip()
            if not width.isdigit():
                return
            w = int(width)
            # Grow first, then shrink back. tmux rejects a relative -1 with
            # "width too small", and grow can hit the session's maximum width,
            # so try both directions and restore the original either way.
            for delta in (+1, -1):
                try:
                    self._tmux("resize-window", "-t", handle, "-x", str(w + delta))
                    self._tmux("resize-window", "-t", handle, "-x", str(w))
                    return
                except BackendError:
                    continue
        except BackendError:
            pass

    def in_mode(self, handle: str) -> bool:
        return self._tmux("display-message", "-p", "-t", handle, "#{pane_in_mode}").strip() == "1"

    def kill(self, handle: str) -> None:
        self._tmux("kill-window", "-t", handle)

    def alive(self, handle: str) -> bool:
        # Window ids are unique across the whole server, so no run id is needed.
        completed = self._run("list-windows", "-a", "-F", "#{window_id}")
        if completed.returncode != 0:
            return False
        return handle in completed.stdout.split()

    def list_handles(self, run: str) -> list[WindowInfo]:
        completed = self._run("list-windows", "-t", self._target(run), "-F", "#{window_id}\t#{window_name}")
        if completed.returncode != 0:
            return []
        windows: list[WindowInfo] = []
        for line in completed.stdout.splitlines():
            handle, _, name = line.partition("\t")
            if handle and name != ROOT_WINDOW:
                windows.append(WindowInfo(handle=handle, name=name))
        return windows

    def kill_run(self, run: str) -> None:
        if self._session_exists(run):
            self._tmux("kill-session", "-t", self._target(run))


@dataclass
class FakeWindow:
    cmd: list[str]
    cwd: str
    env: dict[str, str]
    name: str
    run: str
    screen: list[str] = field(default_factory=list)
    alive: bool = True
    in_mode: bool = False


class FakeBackend:
    """In-memory backend so every layer above can be tested without a terminal."""

    def __init__(self) -> None:
        self.windows: dict[str, FakeWindow] = {}
        self.sends: list[tuple[str, str, bool]] = []
        self._next_id = 0

    def open(self, run: str, name: str, cmd: Sequence[str], cwd: str, env: Mapping[str, str] | None = None) -> str:
        self._next_id += 1
        handle = f"@{self._next_id}"
        self.windows[handle] = FakeWindow(cmd=list(cmd), cwd=cwd, env=dict(env or {}), name=name, run=run)
        return handle

    def _window(self, handle: str) -> FakeWindow:
        try:
            return self.windows[handle]
        except KeyError as exc:
            raise BackendError(f"no such window: {handle}") from exc

    def send(self, handle: str, text: str, enter: bool = True) -> None:
        window = self._window(handle)
        self.sends.append((handle, text, enter))
        window.screen.append(text)

    def capture(self, handle: str, lines: int = 50, escape: bool = False) -> str:
        return "\n".join(self._window(handle).screen[-lines:])

    def in_mode(self, handle: str) -> bool:
        return self._window(handle).in_mode

    def kill(self, handle: str) -> None:
        self._window(handle).alive = False

    def alive(self, handle: str) -> bool:
        window = self.windows.get(handle)
        return window is not None and window.alive

    def list_handles(self, run: str) -> list[WindowInfo]:
        return [WindowInfo(handle=handle, name=window.name) for handle, window in self.windows.items() if window.run == run and window.alive]

    def kill_run(self, run: str) -> None:
        for window in self.windows.values():
            if window.run == run:
                window.alive = False


BACKENDS: dict[str, type[Backend]] = {"tmux": TmuxBackend, "fake": FakeBackend}


def get_backend(name: str | None = None, config: Config | None = None) -> Backend:
    """Construct a backend by name: --backend, then the environment, then tmux."""
    cfg = config if config is not None else Config.from_env()
    chosen = name or cfg.backend
    try:
        factory = BACKENDS[chosen]
    except KeyError as exc:
        raise BackendError(f"unknown backend {chosen!r}; available: {', '.join(sorted(BACKENDS))}") from exc
    return factory()


# ---------------------------------------------------------------------------
# Spawning
# ---------------------------------------------------------------------------


class SpawnError(AgentTabsError):
    """An agent could not be brought up, or could not be proven to be up."""


AGENT_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


class WorkerProvider(StrEnum):
    """A worker CLI with its own launch and lifecycle contract."""

    CLAUDE = "claude"
    AGY = "agy"
    CODEX = "codex"


DEFAULT_PERMISSION_MODE = "acceptEdits"
DEFAULT_CODEX_SANDBOX = "workspace-write"
DEFAULT_CODEX_APPROVAL = "never"
CODEX_SANDBOXES = frozenset({"read-only", "workspace-write", "danger-full-access"})
CODEX_APPROVAL_POLICIES = frozenset({"untrusted", "on-request", "never"})
DEFAULT_SPAWN_TIMEOUT = 60.0
DEFAULT_BOOTSTRAP_TIMEOUT = 30.0
POLL_INTERVAL = 0.25

# Claude Code hook event -> the bus event it records.
HOOK_EVENTS: dict[str, EventType] = {
    "SessionStart": EventType.SPAWNED,
    "UserPromptSubmit": EventType.TURN_START,
    "Stop": EventType.TURN_END,
    "SessionEnd": EventType.EXIT,
}


class BusTail:
    """Incremental reader over the event log.

    Keeps a byte offset so each poll costs only the bytes appended since the
    last one. There is exactly one tailing implementation in this tool and this
    is it -- a second would drift from this one's edge-case handling.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0

    def poll(self) -> list[Event]:
        if not self.path.exists():
            return []
        size = self.path.stat().st_size
        if size < self.offset:
            # The log was truncated or recreated underneath us.
            self.offset = 0
        if size == self.offset:
            return []

        with self.path.open("rb") as handle:
            handle.seek(self.offset)
            chunk = handle.read()

        # A reader can observe the file mid-append. Consume only whole lines and
        # leave a partial trailing record for the next poll.
        end = chunk.rfind(b"\n")
        if end == -1:
            return []
        complete = chunk[: end + 1]
        self.offset += len(complete)

        events: list[Event] = []
        for line in complete.decode("utf-8", errors="replace").splitlines():
            event = _parse_line(line)
            if event is not None:
                events.append(event)
        return events


PREDICATE_KEYS = ("agent", "type")


@dataclass(frozen=True)
class Predicate:
    """A conjunction of alternations. Two operators, on purpose."""

    agents: frozenset[str] | None = None
    types: frozenset[str] | None = None

    def matches(self, event: Event) -> bool:
        if self.agents is not None and event.agent not in self.agents:
            return False
        return not (self.types is not None and event.wire_type() not in self.types)


def parse_predicate(text: str) -> Predicate:
    """Parse ``agent=critic,type=reply|question``.

    Deliberately parsed with str.split and never eval'd: a predicate may one day
    carry text that originated from an agent.
    """
    agents: frozenset[str] | None = None
    types: frozenset[str] | None = None

    for raw_clause in text.split(","):
        clause = raw_clause.strip()
        if not clause:
            continue
        key, separator, raw_value = clause.partition("=")
        if not separator:
            raise BusError(f"malformed predicate clause {clause!r}: expected key=value")
        values = frozenset(part.strip() for part in raw_value.split("|") if part.strip())
        if not values:
            raise BusError(f"predicate clause {clause!r} has no value")

        name = key.strip().lower()
        if name == "agent":
            agents = values
        elif name == "type":
            types = values
        elif name == "status":
            raise BusError("predicate key 'status' is not supported: a report's status is its event type, so use type=reply|question|blocked")
        else:
            raise BusError(f"unknown predicate key {name!r}; valid keys: {', '.join(PREDICATE_KEYS)}")

    if agents is None and types is None:
        raise BusError(f"predicate must constrain at least one of: {', '.join(PREDICATE_KEYS)}")
    return Predicate(agents=agents, types=types)


def wait_for_match(
    paths: RunPaths,
    predicate: Predicate,
    *,
    from_seq: int = 0,
    timeout: float = 900.0,
    interval: float = POLL_INTERVAL,
) -> Event | None:
    """Block until a matching event is appended, or the timeout elapses.

    Returns None on timeout rather than raising, so callers decide whether a
    timeout is fatal.
    """
    tail = BusTail(paths.bus)
    deadline = time.monotonic() + timeout
    while True:
        for event in tail.poll():
            if event.seq > from_seq and predicate.matches(event):
                return event
        if time.monotonic() >= deadline:
            return None
        time.sleep(interval)


def wait_for_event(
    paths: RunPaths,
    *,
    agent: str | None = None,
    types: Sequence[EventType] = (),
    from_seq: int = 0,
    timeout: float = 60.0,
    interval: float = POLL_INTERVAL,
) -> Event | None:
    """Typed convenience wrapper over :func:`wait_for_match`."""
    predicate = Predicate(
        agents=frozenset({agent}) if agent is not None else None,
        types=frozenset(event_type.value for event_type in types) if types else None,
    )
    return wait_for_match(paths, predicate, from_seq=from_seq, timeout=timeout, interval=interval)


def _git(cwd: Path | str, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise BusError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout


def add_worktree(paths: RunPaths, agent: str, source: Path) -> Path:
    """Give an agent its own checkout, so parallel agents cannot clobber each other."""
    target = paths.worktrees / agent
    target.parent.mkdir(parents=True, exist_ok=True)
    _git(source, "worktree", "add", "--detach", str(target), "HEAD")
    return target


def validated_worktree(paths: RunPaths, worktree: Path | str | None) -> Path | None:
    """Resolve a recorded worktree path, refusing anything outside the runtime tree.

    The guard is the point: a bug or a doctored meta.json must never be able to
    talk git into deleting a directory holding real work. It lives in one
    function so that every removal path shares it -- a guard that holds at only
    some call sites is not a guard.

    Separate from the removal itself so callers can validate *before* taking any
    destructive action, rather than discovering a poisoned path halfway through.
    """
    if not worktree:
        return None
    resolved = Path(worktree).expanduser().resolve()
    allowed = paths.worktrees.resolve()
    if not resolved.is_relative_to(allowed):
        raise BusError(f"refusing to remove worktree outside {allowed}: {resolved}")
    return resolved


def main_checkout(cwd: Path | None = None) -> Path:
    """The main working tree: the only safe place to run `git worktree remove` from.

    Never an agent's own directory. git refuses to remove the worktree you are
    standing in, and an agent spawned with --worktree is standing in precisely
    the one being removed.
    """
    common = git_common_dir(cwd)
    return common.parent if common.name == ".git" else common


def remove_worktree(paths: RunPaths, worktree: Path | str, source: Path) -> None:
    """Remove a worktree, refusing any path outside the runtime tree."""
    resolved = validated_worktree(paths, worktree)
    if resolved is not None and resolved.exists():
        _git(source, "worktree", "remove", "--force", str(resolved))


def hook_command(runtime_root: Path, run: str, agent: str, event: EventType) -> str:
    """Build one hook command string.

    Claude Code runs this through a shell, so every element is quoted. This
    repository's own path contains spaces and an ``@``; unquoted, the hook
    silently never fires -- the session runs normally and exits 0, so the only
    symptom is a spawn that times out against a perfectly healthy screen.
    """
    argv = [
        sys.executable,
        str(Path(__file__).resolve()),
        "hook",
        event.value,
        "--runtime",
        str(runtime_root),
        "--run",
        run,
        "--agent",
        agent,
    ]
    return " ".join(shlex.quote(part) for part in argv)


def write_settings(paths: RunPaths, agent: str) -> Path:
    hooks = {
        hook_name: [{"hooks": [{"type": "command", "command": hook_command(paths.runtime_root, paths.run, agent, event)}]}]
        for hook_name, event in HOOK_EVENTS.items()
    }
    path = paths.settings(agent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"hooks": hooks}, indent=2) + "\n", encoding="utf-8")
    return path


@dataclass(frozen=True)
class AgentMeta:
    name: str
    role: str
    handle: str
    cwd: str
    permission_mode: str
    created_at: str
    binary: str
    provider: str = WorkerProvider.CLAUDE.value
    model: str | None = None
    worktree: str | None = None
    isolated_settings: bool = False

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2) + "\n"

    @classmethod
    def load(cls, path: Path) -> AgentMeta:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("provider", WorkerProvider.CLAUDE.value)
        return cls(**data)


def _one_line(text: str) -> str:
    """Collapse to a single line: the doorbell must never contain a newline."""
    return " ".join(text.split())


def doorbell_text(inbox_path: Path) -> str:
    return _one_line(f"[orchestrator] new instruction: {inbox_path}")


def _validate_initial_task(initial_task: str) -> str:
    if not isinstance(initial_task, str) or not initial_task.strip():
        raise SpawnError("initial task must contain non-whitespace text")
    return initial_task


def bootstrap_body(paths: RunPaths, meta: AgentMeta, initial_task: str) -> str:
    return bootstrap_body_for(paths, meta.name, Path(meta.role), initial_task)


def bootstrap_body_for(paths: RunPaths, name: str, role: Path, initial_task: str) -> str:
    task = _validate_initial_task(initial_task)
    protocol = Path(__file__).resolve().parent / "WORKER.md"
    task_bytes = task.encode("utf-8")
    return (
        f"# Bootstrap: {name}\n\n"
        f"You are running in a terminal window a human can see and type into.\n"
        f"Both that human and an orchestrator can address you.\n\n"
        f"## Worker protocol\n"
        f"Read and follow `{protocol}` for inbox checking and `agentctl reply` reporting.\n\n"
        f"- Check your inbox at the start of every turn: `{paths.inbox(name)}`\n"
        f"- Report with `{Path(__file__).resolve()} reply --status reply|question|blocked` (body on stdin).\n"
        "  Your identity comes from the environment; do not pass --run or --agent yourself.\n"
        "- Never assume the orchestrator can see your screen; report anything it must know through reply.\n\n"
        f"## Role\n"
        f"Read `{role}`; it defines your standing responsibilities, not this assignment.\n\n"
        f"## Initial assignment\n"
        f"<!-- agent-tabs-initial-assignment utf8-bytes={len(task_bytes)} -->\n"
        f"{task}"
    )


def _deliver(paths: RunPaths, backend: Backend, agent: str, handle: str, inbox_path: Path, enter: bool) -> None:
    """Type the pointer. The payload is already on disk before this is called."""
    try:
        backend.send(handle, doorbell_text(inbox_path), enter)
    except Exception as exc:
        with _suppressed():
            append_event(paths, agent, EventType.ERROR, {"stage": "send", "inbox": str(inbox_path), "error": str(exc)})
        raise
    append_event(paths, agent, EventType.MESSAGE_SENT, {"inbox": str(inbox_path)})


def ring_doorbell(paths: RunPaths, backend: Backend, agent: str, handle: str, body: str, enter: bool = True) -> Path:
    """Write the payload to the inbox, then send a one-line pointer to it.

    The keystroke is a doorbell, never the message. A mangled or lost keystroke
    then costs nothing: the instruction is already on disk and the worker reads
    its inbox at the start of every turn.

    Unguarded on purpose -- this is the primitive the bootstrap uses, before any
    state exists to gate on. Everything else goes through ``send_message``.
    """
    inbox_path = write_inbox(paths, agent, body)
    _deliver(paths, backend, agent, handle, inbox_path, enter)
    return inbox_path


def write_reply(paths: RunPaths, agent: str, status: OutboxStatus, body: str) -> Path:
    directory = paths.outbox(agent)
    directory.mkdir(parents=True, exist_ok=True)
    highest = 0
    for existing in directory.glob("*.md"):
        try:
            highest = max(highest, int(existing.stem))
        except ValueError:
            continue
    path = directory / f"{highest + 1:0{INBOX_WIDTH}d}.md"
    path.write_text(f"---\nstatus: {status.value}\n---\n{body}\n", encoding="utf-8")
    append_event(paths, agent, EventType(status.value), {"outbox": str(path)})
    return path


def _known_provider(binary: str) -> WorkerProvider | None:
    """Infer a provider only from an executable name we recognize."""
    name = Path(binary).name.lower()
    if "codex" in name:
        return WorkerProvider.CODEX
    if "agy" in name:
        return WorkerProvider.AGY
    if "claude" in name:
        return WorkerProvider.CLAUDE
    return None


def _resolve_worker(binary_name: str | None, provider_name: str | None) -> tuple[str, WorkerProvider]:
    """Resolve the executable without letting an explicit provider drift."""
    try:
        requested = WorkerProvider(provider_name) if provider_name else None
    except ValueError as exc:
        available = ", ".join(provider.value for provider in WorkerProvider)
        raise SpawnError(f"unknown worker provider {provider_name!r}; available: {available}") from exc
    binary: str | None
    if binary_name:
        binary = shutil.which(binary_name) or str(Path(binary_name).expanduser().resolve())
    elif requested is WorkerProvider.CODEX:
        binary = shutil.which(WorkerProvider.CODEX.value)
    elif requested is WorkerProvider.AGY:
        binary = shutil.which(WorkerProvider.AGY.value)
    elif requested is WorkerProvider.CLAUDE:
        binary = shutil.which(WorkerProvider.CLAUDE.value)
    else:
        binary = shutil.which(WorkerProvider.CLAUDE.value) or shutil.which(WorkerProvider.AGY.value)

    if binary is None:
        needed = requested.value if requested else "claude or agy"
        raise SpawnError(f"{needed} is not installed or not on PATH")

    detected = _known_provider(binary)
    if requested is not None and detected is not None and detected is not requested:
        raise SpawnError(f"binary {binary!r} is {detected.value}, not requested provider {requested.value}")
    return binary, requested or detected or WorkerProvider.CLAUDE


def _worker_argv(
    provider: WorkerProvider,
    binary: str,
    working_dir: Path,
    *,
    settings_path: Path | None,
    model: str | None,
    permission_mode: str,
    isolated_settings: bool,
    codex_sandbox: str | None,
    codex_approval: str | None,
    initial_prompt: str | None,
) -> list[str]:
    """Build a provider's launch vector; callers never construct shell text."""
    if provider is WorkerProvider.CODEX:
        sandbox = codex_sandbox or DEFAULT_CODEX_SANDBOX
        approval = codex_approval or DEFAULT_CODEX_APPROVAL
        if permission_mode != DEFAULT_PERMISSION_MODE:
            raise SpawnError("--permission-mode is not supported by provider codex; use --sandbox and --ask-for-approval")
        if isolated_settings:
            raise SpawnError("--isolated-settings is not supported by provider codex")
        if sandbox not in CODEX_SANDBOXES:
            raise SpawnError(f"invalid Codex sandbox {sandbox!r}")
        if approval not in CODEX_APPROVAL_POLICIES:
            raise SpawnError(f"invalid Codex approval policy {approval!r}")
        argv = [binary, "--cd", str(working_dir), "--sandbox", sandbox, "--ask-for-approval", approval]
        if model:
            argv += ["--model", model]
        if initial_prompt:
            argv.append(initial_prompt)
        return argv

    if provider is WorkerProvider.AGY:
        argv = [binary, "--dangerously-skip-permissions"]
        if permission_mode == "acceptEdits":
            argv += ["--mode", "accept-edits"]
        elif permission_mode and permission_mode != "bypassPermissions":
            argv += ["--mode", permission_mode]
        if model:
            argv += ["--model", model]
        return [*argv, "-i"]

    if settings_path is None:
        raise SpawnError("Claude provider requires generated settings")
    argv = [binary, "--settings", str(settings_path), "--permission-mode", permission_mode]
    if isolated_settings:
        argv += ["--setting-sources", ""]
    if model:
        argv += ["--model", model]
    return argv


def _last_screen_diagnostic(backend: Backend, handle: str, lines: int = 40) -> str:
    """The screen text to embed in a SpawnError, or a note when none exists.

    A dark pane must not render as a healthy blank screen: the old
    ``Last screen:`` output of 40 blank lines read as "the agent was fine"
    exactly when spawn had failed.
    """
    try:
        content = backend.capture(handle, lines)
    except BackendError:
        return "screen capture unavailable (pane gone)"
    if not content.strip():
        return "screen capture unavailable (unattached pane)"
    return content


def spawn_agent(
    paths: RunPaths,
    backend: Backend,
    name: str,
    role: Path,
    *,
    initial_task: str,
    model: str | None = None,
    permission_mode: str = DEFAULT_PERMISSION_MODE,
    isolated_settings: bool = False,
    worktree: bool = False,
    cwd: Path | None = None,
    doorbell: bool = True,
    spawn_timeout: float = DEFAULT_SPAWN_TIMEOUT,
    bootstrap_timeout: float = DEFAULT_BOOTSTRAP_TIMEOUT,
    claude_binary: str | None = None,
    provider: str | None = None,
    codex_sandbox: str | None = None,
    codex_approval: str | None = None,
    viewer: Viewer = NullViewer(),
) -> AgentMeta:
    """Bring up one agent and prove it is up before returning.

    Claude uses a hook handshake. Codex exposes no compatible hook surface, so
    agentctl records its successful launch and delivers the bootstrap through
    the durable inbox instead of fabricating turn events.
    """
    task = _validate_initial_task(initial_task)
    if not AGENT_NAME.match(name):
        raise SpawnError(f"invalid agent name {name!r}: use letters, digits, underscore or hyphen")
    role_path = Path(role).expanduser().resolve()
    if not role_path.is_file():
        raise SpawnError(f"role file not found: {role_path}")
    if any(window.name == name for window in backend.list_handles(paths.run)):
        raise SpawnError(f"agent {name!r} is already running in run {paths.run!r}")

    binary, worker_provider = _resolve_worker(claude_binary, provider)

    source = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
    paths.ensure_agent(name)
    watermark = max_seq(paths)

    worktree_path: Path | None = None
    handle: str | None = None
    bootstrap_path: Path | None = None
    try:
        if worktree:
            worktree_path = add_worktree(paths, name, source)
        working_dir = worktree_path or source

        bootstrap_path = write_inbox(paths, name, bootstrap_body_for(paths, name, role_path, task))
        settings_path = write_settings(paths, name) if worker_provider is not WorkerProvider.CODEX else None
        initial_prompt = None
        if worker_provider is WorkerProvider.CODEX and doorbell:
            initial_prompt = (
                "You are an Agent Tabs worker. Before exploring the repository or asking questions, "
                f"read and follow the worker protocol at {Path(__file__).resolve().parent / 'WORKER.md'} "
                f"and the bootstrap inbox file at {bootstrap_path}. "
                "Treat that file as the orchestrator's task. Do not ask the user to choose a persona. "
                "Use agentctl reply --status reply|question|blocked to report back."
            )
        argv = _worker_argv(
            worker_provider,
            binary,
            working_dir,
            settings_path=settings_path,
            model=model,
            permission_mode=permission_mode,
            isolated_settings=isolated_settings,
            codex_sandbox=codex_sandbox,
            codex_approval=codex_approval,
            initial_prompt=initial_prompt,
        )

        env = {ENV_RUNTIME: str(paths.runtime_root), ENV_RUN: paths.run, ENV_AGENT: name}
        handle = backend.open(paths.run, name, argv, str(working_dir), env)
        try:
            viewer.reveal(paths.run, handle)
        except Exception as exc:  # noqa: BLE001 - a cosmetic step must never fail a spawn
            # Deliberately broader than ViewerError: this call sits inside the
            # outer try/except below, whose handler kills the window and the
            # worktree on ANY exception. A viewer that raises something else
            # (an AttributeError in a script builder, a bad injected runner)
            # would otherwise destroy a healthy agent over a cosmetic failure.
            log.warning("viewer %r could not reveal %s: %s", viewer, handle, exc)
        if worker_provider is WorkerProvider.AGY:
            time.sleep(AGY_BOOT_DELAY)
            if not backend.alive(handle):
                raise SpawnError(
                    f"agy exited on its own within {AGY_BOOT_DELAY}s of starting; last screen:\n{_last_screen_diagnostic(backend, handle)}"
                )
            if doorbell:
                backend.send(handle, "", enter=True)

        meta = AgentMeta(
            name=name,
            role=str(role_path),
            handle=handle,
            cwd=str(working_dir),
            permission_mode=permission_mode,
            created_at=utc_now(),
            binary=binary,
            provider=worker_provider.value,
            model=model,
            worktree=str(worktree_path) if worktree_path else None,
            isolated_settings=isolated_settings,
        )
        paths.meta(name).write_text(meta.to_json(), encoding="utf-8")

        if worker_provider is WorkerProvider.CODEX:
            if not backend.alive(handle):
                raise SpawnError(f"codex exited before bootstrap; last screen:\n{_last_screen_diagnostic(backend, handle)}")
            append_event(paths, name, EventType.SPAWNED, {"provider": WorkerProvider.CODEX.value, "source": "agentctl"})
        elif wait_for_event(paths, agent=name, types=[EventType.SPAWNED], from_seq=watermark, timeout=spawn_timeout) is None:
            raise SpawnError(
                f"agent {name!r} never reported SessionStart within {spawn_timeout:.0f}s.\nLast screen:\n{_last_screen_diagnostic(backend, handle)}"
            )

        if doorbell:
            if worker_provider is WorkerProvider.CODEX:
                if bootstrap_path is None:
                    raise SpawnError("Codex bootstrap inbox was not prepared")
                _deliver(paths, backend, meta.name, meta.handle, bootstrap_path, enter=True)
            else:
                _bootstrap(paths, backend, meta, bootstrap_path, bootstrap_timeout)
        return meta
    except Exception as exc:
        # Never leave a half-live agent: no window, no worktree, and the failure
        # recorded on the bus rather than only in the caller's terminal.
        if handle is not None:
            with _suppressed():
                backend.kill(handle)
        if worktree_path is not None:
            with _suppressed():
                remove_worktree(paths, worktree_path, source)
        bootstrap_error_path: str | None = None
        if bootstrap_path is not None and bootstrap_path.exists():
            agent_dir = paths.agent_dir(name)
            other_files = [path for path in agent_dir.rglob("*") if path.is_file() and path != bootstrap_path]
            if not other_files:
                with _suppressed():
                    bootstrap_path.unlink()
                    for child in (paths.inbox(name), paths.outbox(name)):
                        if child.exists() and not any(child.iterdir()):
                            child.rmdir()
                    if agent_dir.exists() and not any(agent_dir.iterdir()):
                        agent_dir.rmdir()
            else:
                bootstrap_error_path = str(bootstrap_path)
        with _suppressed():
            error_data: dict[str, str] = {"stage": "spawn", "error": str(exc)}
            if bootstrap_error_path is not None:
                error_data["bootstrap"] = bootstrap_error_path
            append_event(paths, name, EventType.ERROR, error_data)
        raise


def _bootstrap(paths: RunPaths, backend: Backend, meta: AgentMeta, bootstrap_path: Path, timeout: float) -> None:
    """Ring the bootstrap doorbell and prove it landed.

    Every later message is recoverable because the worker re-reads its inbox
    each turn. The bootstrap is the exception: if that keystroke is lost the
    agent never takes a turn at all, so the inbox is never read and the agent
    sits idle forever holding a perfectly good instruction. It is the one
    message that must be confirmed, and retried, rather than assumed.
    """
    for attempt in (1, 2):
        watermark = max_seq(paths)
        _deliver(paths, backend, meta.name, meta.handle, bootstrap_path, enter=True)
        if wait_for_event(paths, agent=meta.name, types=[EventType.TURN_START], from_seq=watermark, timeout=timeout) is not None:
            return
        log.warning("bootstrap doorbell for %s not acknowledged (attempt %d)", meta.name, attempt)
    raise SpawnError(
        f"agent {meta.name!r} never started a turn after two bootstrap attempts.\nLast screen:\n{_last_screen_diagnostic(backend, meta.handle)}"
    )


class _suppressed:
    """Swallow errors during cleanup so the original failure is what surfaces."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        if exc is not None:
            log.debug("ignored during cleanup: %s", exc)
        return True


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


EXIT_TIMEOUT = 2
EXIT_QUEUED = 3
DEFAULT_WAIT_TIMEOUT = 900.0
SENDABLE_STATES = frozenset({AgentState.IDLE, AgentState.AWAITING_HUMAN})
COMPOSER_MARKER = "❯"
COMPOSER_SCAN_LINES = 8
REPAINT_THROTTLE = 1.0  # seconds between forced repaints of an unattached pane
DEFAULT_WAIT_IDLE = 120.0


_SGR = re.compile(r"\x1b\[([0-9;:?]*)[ -/]*([@-~])")


def _update_dim_sgr(dim: bool, parameters: str) -> bool:
    """Apply SGR intensity parameters, skipping extended-colour payloads."""
    params = parameters.split(";")
    index = 0
    while index < len(params):
        parameter = params[index]
        if parameter == "0" or parameter == "22":
            dim = False
        elif parameter == "2":
            dim = True
        elif parameter in ("38", "48") and index + 1 < len(params):
            mode = params[index + 1]
            if mode == "2":
                index += 4  # 38;2;r;g;b or 48;2;r;g;b
            elif mode == "5":
                index += 2  # 38;5;n or 48;5;n
        index += 1
    return dim


def _composer_text_dims(line: str) -> list[bool] | None:
    """Dim states of non-space glyphs after the composer marker, if present."""
    dim = False
    glyphs: list[tuple[str, bool]] = []
    position = 0
    for match in _SGR.finditer(line):
        glyphs.extend((character, dim) for character in line[position : match.start()])
        if match.group(2) == "m":
            dim = _update_dim_sgr(dim, match.group(1))
        position = match.end()
    glyphs.extend((character, dim) for character in line[position:])

    marker = next((index for index, (character, _) in enumerate(glyphs) if not character.isspace()), None)
    if marker is None or glyphs[marker][0] != COMPOSER_MARKER:
        return None
    return [dim for character, dim in glyphs[marker + 1 :] if not character.isspace()]


def _input_row_looks_busy(screen: str) -> bool:
    """Best-effort: is there text in the composer that the human has not sent?

    This is the only place in the tool that reads a terminal's *rendering* to
    make a decision, and it will break when the TUI changes. Everything else is
    event-driven and version-independent. Keep it in this one function so there
    is exactly one place to repair.

    Claude Code v2.1.226 renders a *placeholder* in the idle composer (the
    observed text was "check your inbox"); v2.1.223 rendered nothing there. A
    placeholder and genuinely typed text are indistinguishable by content, so
    the discriminator is rendering, not text: the placeholder is emitted dim
    (SGR param 2) while typed text is plain. ``capture(..., escape=True)``
    preserves the escape sequences this function reads.

    Assumption adopted without a live capture (the probe spike was deferred):
    every placeholder glyph is dim and typed text is plain. The style of the
    prompt marker itself is ignored, so a dim marker cannot make real typed
    text look like a placeholder. If a release stops dimming the placeholder,
    this gate fails closed -- it reads the styled text as a busy composer,
    deadlocking sends rather than garbling a human's line. That is the
    opposite, and safer, direction of the v2.1.226 bug this repairs, and it
    surfaces as a red live-worker test rather than a silent wrong send.

    When the marker cannot be found the answer is False -- deliberately failing
    open. A missed detection garbles one line the human is typing, and the
    instruction is already safe in the inbox; failing closed would deadlock
    every workflow the moment the TUI changed.
    """
    for line in reversed(screen.splitlines()):
        text_dims = _composer_text_dims(line)
        if text_dims is not None:
            return bool(text_dims) and not all(text_dims)
    log.debug("composer marker not found; assuming the input row is free")
    return False


def _composer_looks_busy(screen: str, provider: str) -> bool:
    """Apply only a renderer heuristic that is evidenced for this provider."""
    if provider == WorkerProvider.CODEX.value:
        log.debug("Codex composer detector is unavailable; assuming the input row is free")
        return False
    return _input_row_looks_busy(screen)


@dataclass(frozen=True)
class Readiness:
    ready: bool
    reason: str


def is_ready(paths: RunPaths, backend: Backend, agent: str, handle: str | None = None) -> Readiness:
    """Three independent gates, all of which must pass before typing at an agent."""
    state = derive_state(read_events(paths, agent), read_outbox(paths, agent))
    if state not in SENDABLE_STATES:
        return Readiness(False, state.value)

    meta = AgentMeta.load(paths.meta(agent))
    target = handle or meta.handle
    if backend.in_mode(target):
        # The human is scrolled back reading this agent. send-keys would be
        # swallowed by copy-mode, silently, in exactly the situation this
        # framework exists to support. Refuse rather than cancel their scroll.
        return Readiness(False, "copy_mode")
    if _composer_looks_busy(backend.capture(target, COMPOSER_SCAN_LINES, escape=True), meta.provider):
        return Readiness(False, "human_typing")
    return Readiness(True, state.value)


def await_ready(
    paths: RunPaths,
    backend: Backend,
    agent: str,
    handle: str | None = None,
    *,
    timeout: float = DEFAULT_WAIT_IDLE,
    interval: float = POLL_INTERVAL,
) -> Readiness:
    deadline = time.monotonic() + timeout
    while True:
        readiness = is_ready(paths, backend, agent, handle)
        if readiness.ready or time.monotonic() >= deadline:
            return readiness
        time.sleep(interval)


def send_message(
    paths: RunPaths,
    backend: Backend,
    agent: str,
    body: str,
    *,
    enter: bool = True,
    force: bool = False,
    queue: bool = False,
    wait_idle: float = DEFAULT_WAIT_IDLE,
) -> tuple[Path, Readiness]:
    """Deliver an instruction. Returns the inbox path and the readiness verdict.

    The payload is written before any terminal interaction, unconditionally.
    That ordering is the invariant the whole design rests on: a refused, queued
    or mangled send costs nothing, because the instruction is already on disk
    and the worker reads its inbox at the start of every turn.
    """
    meta = AgentMeta.load(paths.meta(agent))
    inbox_path = write_inbox(paths, agent, body)

    if force:
        readiness = Readiness(True, "forced")
    elif queue:
        readiness = is_ready(paths, backend, agent, meta.handle)
    else:
        readiness = await_ready(paths, backend, agent, meta.handle, timeout=wait_idle)

    if not readiness.ready:
        log.debug("queued message for %s: %s", agent, readiness.reason)
        return inbox_path, readiness

    _deliver(paths, backend, agent, meta.handle, inbox_path, enter)
    return inbox_path, readiness


# ---------------------------------------------------------------------------
# Lifecycle: reconciliation and teardown
#
# Three authorities, and they are not interchangeable: the runtime tree says
# which agents *exist*, the backend says which are *alive*, and the bus says
# what that *means*. Every command below reconciles the first two and records
# the answer in the third.
# ---------------------------------------------------------------------------


DEFAULT_CLOSE_TIMEOUT = 30.0
DEFAULT_STALLED_AFTER = 300.0
STATUS_EVENT_TAIL = 15
EXIT_COMMAND = "/exit"


def list_agent_names(paths: RunPaths) -> list[str]:
    """Every agent this run has a record of, alive or not.

    Directories without a meta.json are spawns that died before recording
    anything; they are skipped here and left for ``reap``.
    """
    directory = paths.root / "agents"
    if not directory.is_dir():
        return []
    return sorted(entry.name for entry in directory.iterdir() if entry.is_dir() and (entry / "meta.json").is_file())


def _load_meta(paths: RunPaths, agent: str) -> AgentMeta | None:
    try:
        return AgentMeta.load(paths.meta(agent))
    except (OSError, ValueError, TypeError) as exc:
        log.warning("unreadable meta.json for %s: %s", agent, exc)
        return None


def _has_exited(paths: RunPaths, agent: str) -> bool:
    return any(event.type is EventType.EXIT for event in read_events(paths, agent))


def reconcile(paths: RunPaths, backend: Backend, agents: Sequence[str] | None = None) -> list[str]:
    """Record an ``exit`` for every agent whose window is gone. Returns their names.

    Nothing fires SessionEnd when a human closes a window by hand or the machine
    reboots, so without this the log claims that agent is alive forever and the
    orchestrator waits on a reply that can never come.

    Idempotency is keyed on the absence of an ``exit`` event rather than on the
    derived state. ``error`` also derives to ``dead``, so gating on state would
    permanently exclude a live agent that once had a single failed keystroke.

    Two concurrent callers can both append an ``exit``; the append itself is
    locked, and a duplicate does not change the derived state, so the cost is one
    extra log line rather than a second locking protocol over the bus.
    """
    vanished: list[str] = []
    for agent in list(agents) if agents is not None else list_agent_names(paths):
        if _has_exited(paths, agent):
            continue
        meta = _load_meta(paths, agent)
        if meta is None or backend.alive(meta.handle):
            continue
        append_event(paths, agent, EventType.EXIT, {"reason": "window_vanished"})
        vanished.append(agent)
    return vanished


def _age_seconds(timestamp: str) -> float | None:
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    return (datetime.now(UTC) - parsed).total_seconds()


@dataclass(frozen=True)
class AgentSummary:
    meta: AgentMeta
    state: AgentState
    alive: bool
    outbox_count: int
    uptime_seconds: float | None


def summarise(paths: RunPaths, backend: Backend, agent: str) -> AgentSummary:
    meta = AgentMeta.load(paths.meta(agent))
    outbox = read_outbox(paths, agent)
    return AgentSummary(
        meta=meta,
        state=derive_state(read_events(paths, agent), outbox),
        alive=backend.alive(meta.handle),
        outbox_count=len(outbox),
        uptime_seconds=_age_seconds(meta.created_at),
    )


def stalled_for(events: Sequence[Event], state: AgentState, threshold: float = DEFAULT_STALLED_AFTER) -> float | None:
    """How long an agent has been mid-turn, once that exceeds ``threshold``.

    A worker deadlocked on an unattended permission dialog is indistinguishable
    from one thinking hard: both are ``busy`` with no ``turn_end``. Elapsed time
    is the only signal available, so this is a hint for the human rather than a
    verdict -- it says "go look at that window", never "that agent is broken".
    """
    if state is not AgentState.BUSY:
        return None
    starts = [event for event in events if event.type is EventType.TURN_START]
    if not starts:
        return None
    age = _age_seconds(max(starts, key=lambda event: event.seq).ts)
    return age if age is not None and age >= threshold else None


def close_agent(
    paths: RunPaths,
    backend: Backend,
    agent: str,
    *,
    force: bool = False,
    timeout: float = DEFAULT_CLOSE_TIMEOUT,
    source: Path | None = None,
) -> str:
    """Shut one agent down and clean up after it. Returns what actually happened.

    The graceful path types ``/exit`` so the worker flushes its transcript, but
    it is best effort and **the timeout is the real guarantee**. ``send-keys -l``
    puts the text wherever focus happens to be: mid-turn, in copy-mode, or with a
    dialog open it lands somewhere harmless and the kill follows regardless. Do
    not "fix" this by lengthening the timeout -- there is nothing to wait for.

    The worktree path is validated before anything is killed, so a doctored
    meta.json aborts the whole operation rather than being discovered halfway.
    """
    meta = AgentMeta.load(paths.meta(agent))
    worktree = validated_worktree(paths, meta.worktree)

    if not backend.alive(meta.handle):
        outcome = "already_gone"
    elif force:
        with _suppressed():
            backend.kill(meta.handle)
        outcome = "forced"
    else:
        watermark = max_seq(paths)
        with _suppressed():
            backend.send(meta.handle, EXIT_COMMAND, enter=True)
            wait_for_event(paths, agent=agent, types=[EventType.EXIT], from_seq=watermark, timeout=timeout)
        with _suppressed():
            backend.kill(meta.handle)
        outcome = "graceful"

    if worktree is not None:
        remove_worktree(paths, worktree, source or main_checkout())
    if not _has_exited(paths, agent):
        append_event(paths, agent, EventType.EXIT, {"reason": outcome})
    refresh_state_cache(paths, agent)
    return outcome


@dataclass(frozen=True)
class ReapPlan:
    """What a sweep would remove. Building it touches nothing."""

    agents: list[str]
    worktrees: list[Path]
    session: bool

    @property
    def empty(self) -> bool:
        return not self.agents and not self.worktrees and not self.session


def plan_reap(paths: RunPaths, backend: Backend, *, include_session: bool = False) -> ReapPlan:
    """Find orphans: agents whose window is gone, and worktrees nobody owns."""
    orphans: list[str] = []
    owned: set[Path] = set()
    for agent in list_agent_names(paths):
        meta = _load_meta(paths, agent)
        if meta is None:
            continue
        if backend.alive(meta.handle):
            if meta.worktree:
                owned.add(Path(meta.worktree).expanduser().resolve())
        else:
            orphans.append(agent)

    stale: list[Path] = []
    if paths.worktrees.is_dir():
        stale = sorted(entry for entry in paths.worktrees.iterdir() if entry.is_dir() and entry.resolve() not in owned)

    return ReapPlan(agents=orphans, worktrees=stale, session=include_session and not backend.list_handles(paths.run))


def apply_reap(paths: RunPaths, backend: Backend, plan: ReapPlan) -> None:
    """Act on a plan. Every removal still passes the runtime-tree guard."""
    for agent in plan.agents:
        if not _has_exited(paths, agent):
            append_event(paths, agent, EventType.EXIT, {"reason": "reaped"})
        refresh_state_cache(paths, agent)

    source: Path | None = None
    for worktree in plan.worktrees:
        if source is None:
            source = main_checkout()
        remove_worktree(paths, worktree, source)

    if plan.session:
        backend.kill_run(paths.run)


def close_run(paths: RunPaths, backend: Backend, *, force: bool = False, timeout: float = DEFAULT_CLOSE_TIMEOUT) -> list[str]:
    """Tear down every agent in the run, then the session that held them.

    Every worktree path is validated up front: one poisoned meta.json aborts
    before a single window is killed.

    Known gap: were the orchestrator ever moved inside the tmux session (a
    deferred decision), this would kill the window it is itself running in. That
    is left explicit rather than half-guarded, because a partial guard here would
    read as safety that is not there.
    """
    names = list_agent_names(paths)
    for name in names:
        validated_worktree(paths, AgentMeta.load(paths.meta(name)).worktree)

    for name in names:
        with _suppressed():
            close_agent(paths, backend, name, force=force, timeout=timeout)
    backend.kill_run(paths.run)
    return names


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentctl",
        description="Launch, message and observe human-visible agent sessions.",
    )
    parser.add_argument("--version", action="version", version=f"agentctl {__version__}")
    parser.add_argument("--runtime", help="absolute runtime root; overrides $AGENT_TABS_RUNTIME")
    parser.add_argument("--run", help="run id; overrides $AGENT_TABS_RUN")
    parser.add_argument("--backend", help="backend name; overrides $AGENT_TABS_BACKEND")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging to stderr")

    # Repeated on every subcommand so that `agentctl hook spawned --run X` works
    # as well as `agentctl --run X hook spawned`. SUPPRESS is essential: without
    # it an absent subcommand copy would overwrite the value the top-level
    # parser already stored.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--runtime", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument("--run", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument("--backend", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    seq_parser = subparsers.add_parser("seq", parents=[common], help="print the current event high-water mark")
    seq_parser.set_defaults(handler=_cmd_seq)

    paths_parser = subparsers.add_parser("paths", parents=[common], help="print resolved runtime paths")
    paths_parser.set_defaults(handler=_cmd_paths)

    hook_parser = subparsers.add_parser("hook", parents=[common], help="record a lifecycle event (invoked by Claude Code hooks)")
    hook_parser.add_argument("event", help="event type, e.g. spawned / turn_start / turn_end / exit")
    hook_parser.add_argument("--agent", help=f"agent name; overrides ${ENV_AGENT}")
    hook_parser.set_defaults(handler=_cmd_hook)

    spawn_parser = subparsers.add_parser("spawn", parents=[common], help="launch an agent in a visible window")
    spawn_parser.add_argument("name")
    spawn_parser.add_argument("--role", required=True, help="path to the role document the agent adopts")
    task_group = spawn_parser.add_mutually_exclusive_group(required=True)
    task_group.add_argument("--task", help="the concrete initial assignment")
    task_group.add_argument("--task-file", help="UTF-8 file containing the concrete initial assignment")
    spawn_parser.add_argument(
        "--provider",
        choices=[provider.value for provider in WorkerProvider],
        help="worker CLI contract; omit for legacy Claude then AGY resolution",
    )
    spawn_parser.add_argument("--binary", help="path or name of the worker binary (e.g. claude, agy, or codex)")
    spawn_parser.add_argument("--model", help="model alias, e.g. opus or sonnet")
    spawn_parser.add_argument("--permission-mode", default=DEFAULT_PERMISSION_MODE)
    spawn_parser.add_argument("--sandbox", choices=sorted(CODEX_SANDBOXES), help="Codex sandbox policy (default: workspace-write)")
    spawn_parser.add_argument("--ask-for-approval", choices=sorted(CODEX_APPROVAL_POLICIES), help="Codex approval policy (default: never)")
    spawn_parser.add_argument("--isolated-settings", action="store_true", help="load only the generated settings")
    spawn_parser.add_argument("--worktree", action="store_true", help="give the agent its own git checkout")
    spawn_parser.add_argument("--cwd", help="working directory (default: current)")
    spawn_parser.add_argument("--no-doorbell", action="store_true", help="do not send the bootstrap instruction")
    spawn_parser.add_argument("--spawn-timeout", type=float, default=DEFAULT_SPAWN_TIMEOUT)
    spawn_parser.add_argument("--bootstrap-timeout", type=float, default=DEFAULT_BOOTSTRAP_TIMEOUT)
    spawn_parser.add_argument("--viewer", help="viewer name (default: iterm-tab); overrides $AGENT_TABS_VIEWER")
    spawn_parser.set_defaults(handler=_cmd_spawn)

    send_parser = subparsers.add_parser("send", parents=[common], help="deliver an instruction to a running agent")
    send_parser.add_argument("name")
    send_parser.add_argument("message", nargs="?", help="message text; use --file, or '-' to read stdin")
    send_parser.add_argument("--file", help="read the message body from this file")
    send_parser.add_argument("--no-enter", action="store_true", help="type the pointer but do not submit it")
    send_parser.add_argument("--force", action="store_true", help="skip every readiness gate (racy; human escape hatch)")
    send_parser.add_argument("--queue", action="store_true", help="return immediately if the agent is not ready")
    send_parser.add_argument("--wait-idle", type=float, default=DEFAULT_WAIT_IDLE)
    send_parser.set_defaults(handler=_cmd_send)

    wait_parser = subparsers.add_parser("wait", parents=[common], help="block until a matching event lands on the bus")
    wait_parser.add_argument("--until", required=True, metavar="PREDICATE", help="e.g. 'agent=critic,type=reply|question'")
    wait_parser.add_argument("--timeout", type=float, default=DEFAULT_WAIT_TIMEOUT)
    wait_parser.add_argument("--from-seq", type=int, default=None, help="watermark; defaults to the current end of the log")
    wait_parser.set_defaults(handler=_cmd_wait)

    read_parser = subparsers.add_parser("read", parents=[common], help="read an agent's replies or its raw screen")
    read_parser.add_argument("name")
    read_parser.add_argument("--outbox", action="store_true", help="structured replies (the default)")
    read_parser.add_argument("--screen", type=int, metavar="N", help="last N lines of the agent's window")
    read_parser.add_argument("--since", type=int, default=0, help="only outbox messages after this index")
    read_parser.add_argument("--json", action="store_true", help="machine-readable output")
    read_parser.set_defaults(handler=_cmd_read)

    list_parser = subparsers.add_parser("list", parents=[common], help="show every agent in the run")
    list_parser.add_argument("--json", action="store_true", help="machine-readable output")
    list_parser.set_defaults(handler=_cmd_list)

    status_parser = subparsers.add_parser("status", parents=[common], help="detail on one agent, including a stalled-turn hint")
    status_parser.add_argument("name")
    status_parser.add_argument("--stalled-after", type=float, default=DEFAULT_STALLED_AFTER, help="seconds mid-turn before flagging a stall")
    status_parser.add_argument("--json", action="store_true", help="machine-readable output")
    status_parser.set_defaults(handler=_cmd_status)

    close_parser = subparsers.add_parser("close", parents=[common], help="shut one agent down and clean up after it")
    close_parser.add_argument("name")
    close_parser.add_argument("--force", action="store_true", help="kill immediately, skipping the /exit courtesy")
    close_parser.add_argument("--timeout", type=float, default=DEFAULT_CLOSE_TIMEOUT)
    close_parser.set_defaults(handler=_cmd_close)

    reap_parser = subparsers.add_parser("reap", parents=[common], help="sweep orphaned agents and worktrees (reports only unless --apply)")
    reap_parser.add_argument("--apply", action="store_true", help="actually remove what would be reported")
    reap_parser.add_argument("--all", action="store_true", help="implies --apply, and kills the session once it is empty")
    reap_parser.add_argument("--dry-run", action="store_true", help="explicit form of the default: report and change nothing")
    reap_parser.add_argument("--json", action="store_true", help="machine-readable output")
    reap_parser.set_defaults(handler=_cmd_reap)

    close_run_parser = subparsers.add_parser("close-run", parents=[common], help="tear down every agent and the session holding them")
    close_run_parser.add_argument("--force", action="store_true", help="kill immediately, skipping the /exit courtesy")
    close_run_parser.add_argument("--timeout", type=float, default=DEFAULT_CLOSE_TIMEOUT)
    close_run_parser.set_defaults(handler=_cmd_close_run)

    reply_parser = subparsers.add_parser("reply", parents=[common], help="report back to the orchestrator (invoked by workers)")
    reply_parser.add_argument("--status", default=OutboxStatus.REPLY.value, choices=[status.value for status in OutboxStatus])
    reply_parser.add_argument("--agent", help=f"agent name; overrides ${ENV_AGENT}")
    reply_parser.add_argument("--body", help="message body; read from stdin when omitted")
    reply_parser.set_defaults(handler=_cmd_reply)

    return parser


def _require_run(args: argparse.Namespace, config: Config) -> str:
    run = args.run or config.run
    if not run:
        raise BusError(f"a run id is required: pass --run or set ${ENV_RUN}")
    return run


def _cmd_seq(args: argparse.Namespace, config: Config) -> int:
    paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))
    print(max_seq(paths))
    return 0


def _cmd_paths(args: argparse.Namespace, config: Config) -> int:
    root = resolve_runtime_root(args.runtime, config)
    run = args.run or config.run
    print(f"runtime_root: {root}")
    if run:
        paths = RunPaths.build(root, run)
        print(f"run_root:     {paths.root}")
        print(f"bus:          {paths.bus}")
    return 0


def _require_agent(args: argparse.Namespace, config: Config) -> str:
    agent = getattr(args, "agent", None) or config.agent
    if not agent:
        raise BusError(f"an agent name is required: pass --agent or set ${ENV_AGENT}")
    return agent


def _read_stdin() -> str:
    """Read piped input, treating an unreadable stream as no input.

    Hooks are invoked with stdin attached to a pipe, but a closed or detached
    stream must not raise: `hook` has to stay exit-0, and `send` should report
    a missing message rather than a traceback.
    """
    if sys.stdin is None or sys.stdin.isatty():
        return ""
    try:
        return sys.stdin.read()
    except (OSError, ValueError):
        return ""


def _cmd_hook(args: argparse.Namespace, config: Config) -> int:
    """Record a lifecycle event. Always exits 0.

    This runs inside the worker's own session: a traceback here would print into
    the human's view of that agent and could disturb the session itself. Any
    failure is recorded on the bus instead and swallowed here.
    """
    try:
        payload = _read_stdin()
        paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))
        agent = _require_agent(args, config)
        data: dict[str, Any] = {}
        if payload.strip():
            try:
                parsed = json.loads(payload)
                if isinstance(parsed, dict):
                    data = {key: parsed[key] for key in ("session_id", "cwd") if key in parsed}
            except json.JSONDecodeError:
                data = {"stdin": "unparseable"}
        append_event(paths, agent, EventType.parse(args.event), data)
        refresh_state_cache(paths, agent)
    except Exception as exc:  # noqa: BLE001 -- deliberate: hooks must never fail loudly
        with _suppressed():
            paths = RunPaths.build(resolve_runtime_root(args.runtime, config), args.run or config.run or "unknown")
            append_event(paths, getattr(args, "agent", None) or config.agent or "unknown", EventType.ERROR, {"hook": args.event, "error": str(exc)})
    return 0


def _cmd_spawn(args: argparse.Namespace, config: Config) -> int:
    paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))
    if args.task is not None:
        initial_task = _validate_initial_task(args.task)
    else:
        task_path = Path(args.task_file).expanduser()
        if not task_path.is_file():
            raise SpawnError(f"task file not found: {task_path}")
        try:
            initial_task = task_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise SpawnError(f"could not read task file {task_path}: {exc}") from exc
        initial_task = _validate_initial_task(initial_task)
    meta = spawn_agent(
        paths,
        get_backend(args.backend, config),
        args.name,
        Path(args.role),
        initial_task=initial_task,
        model=args.model,
        permission_mode=args.permission_mode,
        isolated_settings=args.isolated_settings,
        worktree=args.worktree,
        cwd=Path(args.cwd) if args.cwd else None,
        doorbell=not args.no_doorbell,
        spawn_timeout=args.spawn_timeout,
        bootstrap_timeout=args.bootstrap_timeout,
        claude_binary=args.binary,
        provider=args.provider,
        codex_sandbox=args.sandbox,
        codex_approval=args.ask_for_approval,
        viewer=get_viewer(args.viewer, config),
    )
    print(f"{meta.name}\t{meta.handle}\t{meta.cwd}\t{meta.binary}")
    return 0


def _message_body(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).expanduser().read_text(encoding="utf-8")
    if args.message and args.message != "-":
        return str(args.message)
    body = _read_stdin()
    if not body.strip():
        raise BusError("no message given: pass text, --file, or pipe it on stdin")
    return body


def _cmd_send(args: argparse.Namespace, config: Config) -> int:
    paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))
    inbox_path, readiness = send_message(
        paths,
        get_backend(args.backend, config),
        args.name,
        _message_body(args),
        enter=not args.no_enter,
        force=args.force,
        queue=args.queue,
        wait_idle=args.wait_idle,
    )
    if not readiness.ready:
        print(f"queued\t{inbox_path}\t{readiness.reason}")
        return EXIT_QUEUED
    print(f"sent\t{inbox_path}")
    return 0


def _cmd_wait(args: argparse.Namespace, config: Config) -> int:
    """Block until a matching event lands. Designed to be run under background Bash.

    Exit 0 with the event on stdout, 2 on timeout with stdout empty.
    """
    paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))
    predicate = parse_predicate(args.until)
    # Defaulting to the live watermark rather than 0 is essential: matching a
    # historical event would make wait return instantly and look like success.
    from_seq = args.from_seq if args.from_seq is not None else max_seq(paths)

    event = wait_for_match(paths, predicate, from_seq=from_seq, timeout=args.timeout)
    if event is None:
        log.debug("wait timed out after %.0fs", args.timeout)
        return EXIT_TIMEOUT
    print(event.to_line())
    return 0


def _cmd_read(args: argparse.Namespace, config: Config) -> int:
    paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))

    if args.screen:
        meta = AgentMeta.load(paths.meta(args.name))
        screen = get_backend(args.backend, config).capture(meta.handle, args.screen)
        print(json.dumps({"agent": args.name, "screen": screen}, indent=2) if args.json else screen)
        return 0

    messages = read_outbox(paths, args.name, since=args.since)
    state = derive_state(read_events(paths, args.name), messages)
    if args.json:
        payload = {
            "agent": args.name,
            "state": state.value,
            "messages": [
                {"index": message.index, "status": message.status.value, "malformed": message.malformed, "body": message.body} for message in messages
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"{args.name}: {state.value}")
    for message in messages:
        flag = " (malformed frontmatter)" if message.malformed else ""
        print(f"\n--- {message.index:04d} [{message.status.value}]{flag} ---\n{message.body.strip()}")
    return 0


def _format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "-"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    return f"{int(seconds // 3600)}h{int(seconds % 3600 // 60):02d}m"


def _cmd_list(args: argparse.Namespace, config: Config) -> int:
    paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))
    backend = get_backend(args.backend, config)
    reconcile(paths, backend)
    summaries = [summarise(paths, backend, agent) for agent in list_agent_names(paths)]

    if args.json:
        print(
            json.dumps(
                {
                    "run": paths.run,
                    "agents": [
                        {
                            "name": summary.meta.name,
                            "state": summary.state.value,
                            "model": summary.meta.model,
                            "handle": summary.meta.handle,
                            "alive": summary.alive,
                            "uptime_seconds": summary.uptime_seconds,
                            "outbox": summary.outbox_count,
                        }
                        for summary in summaries
                    ],
                },
                indent=2,
            )
        )
        return 0

    if not summaries:
        print(f"no agents in run {paths.run!r}")
        return 0
    print(f"{'NAME':<16}{'STATE':<16}{'MODEL':<10}{'HANDLE':<8}{'UPTIME':<8}OUTBOX")
    for summary in summaries:
        model = summary.meta.model or "-"
        print(
            f"{summary.meta.name:<16}{summary.state.value:<16}{model:<10}"
            f"{summary.meta.handle:<8}{_format_duration(summary.uptime_seconds):<8}{summary.outbox_count}"
        )
    return 0


def _cmd_status(args: argparse.Namespace, config: Config) -> int:
    paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))
    backend = get_backend(args.backend, config)
    reconcile(paths, backend, [args.name])

    summary = summarise(paths, backend, args.name)
    events = read_events(paths, args.name)
    stalled = stalled_for(events, summary.state, args.stalled_after)
    tail = events[-STATUS_EVENT_TAIL:]

    if args.json:
        print(
            json.dumps(
                {
                    "meta": summary.meta.__dict__,
                    "state": summary.state.value,
                    "alive": summary.alive,
                    "uptime_seconds": summary.uptime_seconds,
                    "outbox": summary.outbox_count,
                    "stalled_seconds": stalled,
                    "events": [json.loads(event.to_line()) for event in tail],
                },
                indent=2,
            )
        )
        return 0

    print(f"{summary.meta.name}: {summary.state.value}{'' if summary.alive else ' (window gone)'}")
    print(f"  handle:   {summary.meta.handle}")
    print(f"  model:    {summary.meta.model or '-'}")
    print(f"  role:     {summary.meta.role}")
    print(f"  cwd:      {summary.meta.cwd}")
    print(f"  worktree: {summary.meta.worktree or '-'}")
    print(f"  uptime:   {_format_duration(summary.uptime_seconds)}")
    print(f"  outbox:   {summary.outbox_count}")
    if stalled is not None:
        # Not a verdict: a permission dialog nobody answered looks exactly like
        # hard thinking. Point the human at the window and let them judge.
        print(f"  STALLED:  mid-turn for {_format_duration(stalled)} with no turn_end -- check this window")
    print(f"\n  last {len(tail)} events:")
    for event in tail:
        print(f"    {event.seq:>4}  {event.ts}  {event.wire_type()}")
    return 0


def _cmd_close(args: argparse.Namespace, config: Config) -> int:
    paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))
    outcome = close_agent(paths, get_backend(args.backend, config), args.name, force=args.force, timeout=args.timeout)
    print(f"closed\t{args.name}\t{outcome}")
    return 0


def _cmd_reap(args: argparse.Namespace, config: Config) -> int:
    """Sweep orphans. Reports and changes nothing unless asked to act."""
    paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))
    backend = get_backend(args.backend, config)
    apply = (args.apply or args.all) and not args.dry_run
    plan = plan_reap(paths, backend, include_session=args.all)

    if args.json:
        print(
            json.dumps(
                {"applied": apply, "agents": plan.agents, "worktrees": [str(path) for path in plan.worktrees], "session": plan.session},
                indent=2,
            )
        )
    if apply:
        apply_reap(paths, backend, plan)

    if args.json:
        return 0
    if plan.empty:
        print("nothing to reap")
        return 0
    verb = "removed" if apply else "would remove"
    for agent in plan.agents:
        print(f"{verb} agent record: {agent} (window gone)")
    for worktree in plan.worktrees:
        print(f"{verb} worktree: {worktree}")
    if plan.session:
        print(f"{'killed' if apply else 'would kill'} empty session: {paths.run}")
    if not apply:
        print("\nnothing was changed; pass --apply to act, or --all to also kill the empty session")
    return 0


def _cmd_close_run(args: argparse.Namespace, config: Config) -> int:
    paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))
    names = close_run(paths, get_backend(args.backend, config), force=args.force, timeout=args.timeout)
    print(f"closed run {paths.run}: {', '.join(names) if names else 'no agents'}")
    return 0


def _cmd_reply(args: argparse.Namespace, config: Config) -> int:
    paths = RunPaths.build(resolve_runtime_root(args.runtime, config), _require_run(args, config))
    agent = _require_agent(args, config)
    body = args.body if args.body is not None else _read_stdin()
    path = write_reply(paths, agent, OutboxStatus(args.status), body.strip())
    refresh_state_cache(paths, agent)
    print(path)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="agentctl: %(message)s",
        stream=sys.stderr,
    )
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        result: int = args.handler(args, Config.from_env())
        return result
    except AgentTabsError as exc:
        print(f"agentctl: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
