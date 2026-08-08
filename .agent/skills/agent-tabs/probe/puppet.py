"""Deterministic terminal fault states for agent-tabs conformance probes."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from types import FrameType
from typing import Literal, cast

PuppetState = Literal["busy", "deaf", "dirty-composer", "hard-kill"]
STATES = ("busy", "deaf", "dirty-composer", "hard-kill")
HARD_KILL_DELAY = 3.0
AGENTCTL = Path(__file__).resolve().parents[1] / "agentctl.py"


def build_parser() -> argparse.ArgumentParser:
    """Build the fault-injector command line."""
    parser = argparse.ArgumentParser(description="agent-tabs deterministic fault injector")
    parser.add_argument("--state", choices=STATES, required=True)
    parser.add_argument("--for", dest="duration", type=float, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Enter the requested fault state after making the window observable."""
    args = build_parser().parse_args(argv)
    if args.duration <= 0:
        raise ValueError("--for must be positive")
    state = cast(PuppetState, args.state)
    _STATES[state](args.duration)
    return 0


def _busy(duration: float) -> None:
    _hook("spawned")
    print("puppet busy", flush=True)
    _hook("turn_start")
    time.sleep(duration)
    _hook("turn_end")


def _deaf(_: float) -> None:
    _hook("spawned")
    signal.pause()


def _dirty_composer(_: float) -> None:
    _hook("spawned")
    signal.signal(signal.SIGWINCH, _draw_dirty_composer)
    _draw_dirty_composer(0, None)
    while True:
        signal.pause()


def _hard_kill(_: float) -> None:
    _hook("spawned")
    time.sleep(HARD_KILL_DELAY)
    os.kill(os.getpid(), signal.SIGKILL)


def _draw_dirty_composer(_: int, __: FrameType | None) -> None:
    # agentctl captures only the last composer scan lines; place this synthetic
    # input row at the pane bottom, matching Claude's real composer placement.
    sys.stdout.write("\x1b[999B\r❯ half typed by a human")
    sys.stdout.flush()


def _hook(event: str) -> None:
    subprocess.run([sys.executable, str(AGENTCTL), "hook", event], check=True)


_STATES: dict[PuppetState, Callable[[float], None]] = {
    "busy": _busy,
    "deaf": _deaf,
    "dirty-composer": _dirty_composer,
    "hard-kill": _hard_kill,
}


if __name__ == "__main__":
    raise SystemExit(main())
