"""Probe-loop command entry point.

Ticket 3 owns the working coverage command.  Later tickets add runner commands
when they have real behavior to execute.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agentctl import RunPaths

from probe.lib.claims import coverage_counts, load
from probe.lib.fluency import measure
from probe.lib.ground import events, provider, session_exists
from probe.lib.journal import append
from probe.lib.orchestrator_checks import CheckResult, ignored_awaiting_human, no_teardown


def build_parser() -> argparse.ArgumentParser:
    """Build the currently implemented command surface."""
    parser = argparse.ArgumentParser(description="Agent-tabs protocol conformance probes")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("coverage", help="summarize claim coverage and source drift")
    checks = subcommands.add_parser("checks", help="run T5a bus-only conformance checks")
    checks.add_argument("--runtime", type=Path, required=True, help="agent-tabs runtime root")
    checks.add_argument("--run", required=True, help="agent-tabs run id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a probe command and return its process status."""
    args = build_parser().parse_args(argv)
    if args.command == "coverage":
        covered, uncovered, stale = coverage_counts(load())
        print(f"covered: {covered}")
        print(f"uncovered: {uncovered}")
        print(f"stale: {stale}")
        return 0
    if args.command == "checks":
        return _run_checks(args.runtime, args.run)
    raise AssertionError(f"unhandled command: {args.command}")


def _run_checks(runtime: Path, run: str) -> int:
    paths = RunPaths.build(runtime, run)
    bus_events = events(paths)
    providers = {agent: provider(paths, agent) for agent in {event.agent for event in bus_events}}
    results = [
        *ignored_awaiting_human(bus_events, providers),
        no_teardown(bus_events, session_is_alive=session_exists(run)),
    ]
    fluency = measure(bus_events)
    payload = {
        "checks": [result.to_dict() for result in results],
        "fluency": asdict(fluency),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    append(
        {
            "entry": f"t5a-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}",
            "kind": "explore",
            "cell": ["C009", "human-interrupt", "orchestrator-loop", "claude", "1"],
            "tried": ["ignored_awaiting_human", "no_teardown"],
            "ruled_out": "bus-only checks recorded without cmdlog instrumentation",
            "outcome": _outcome(results),
            "fault_proof": f"direct bus read for run {run}; tmux session queried directly",
            "checks": payload["checks"],
            "fluency": payload["fluency"],
        }
    )
    return 0


def _outcome(results: Sequence[CheckResult]) -> str:
    verdicts = {result.verdict for result in results}
    if "violation" in verdicts:
        return "finding"
    if "inconclusive" in verdicts:
        return "inconclusive"
    return "no-finding"


if __name__ == "__main__":
    raise SystemExit(main())
