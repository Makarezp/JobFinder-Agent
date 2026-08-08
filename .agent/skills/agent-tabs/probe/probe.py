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

from probe.lib.assertions import HarnessError
from probe.lib.claims import coverage_counts, load
from probe.lib.cmdlog import load as load_commands
from probe.lib.fluency import measure, measure_cmdlog
from probe.lib.ground import events, provider, session_exists
from probe.lib.journal import (
    COVERAGE_PATH,
    JOURNAL_PATH,
    LEDGER_PATH,
    JournalError,
    append,
    cell_status,
    load_ledger,
    normalize_cell,
    write_coverage,
)
from probe.lib.journal import (
    load as load_journal,
)
from probe.lib.oracle import OracleError, triage_finding
from probe.lib.orchestrator_checks import (
    CheckResult,
    ignored_awaiting_human,
    no_teardown,
    polling_wait,
    screen_parsing,
    unwatermarked_send,
)
from probe.lib.runner import run_brief


def build_parser() -> argparse.ArgumentParser:
    """Build the currently implemented command surface."""
    parser = argparse.ArgumentParser(description="Agent-tabs protocol conformance probes")
    subcommands = parser.add_subparsers(dest="command", required=True)
    coverage = subcommands.add_parser("coverage", help="summarize claim coverage and source drift")
    coverage.add_argument("--write", action="store_true", help="regenerate the derived coverage digest")
    coverage.add_argument("--journal", type=Path, default=JOURNAL_PATH, help="journal JSONL path")
    coverage.add_argument("--ledger", type=Path, default=LEDGER_PATH, help="rate-ledger JSONL path")
    coverage.add_argument("--output", type=Path, default=COVERAGE_PATH, help="coverage digest output path")
    checks = subcommands.add_parser("checks", help="run T5a bus-only conformance checks")
    checks.add_argument("--runtime", type=Path, required=True, help="agent-tabs runtime root")
    checks.add_argument("--run", required=True, help="agent-tabs run id")
    run = subcommands.add_parser("run", help="run one real-worker conformance brief")
    run.add_argument("brief", help="brief identifier, for example B002")
    run.add_argument("--trials", type=int, help="override the brief's sequential trial count")
    explore = subcommands.add_parser("explore", help="record one completed author exploration")
    explore.add_argument("--cell", required=True, help="JSON target cell")
    explore.add_argument("--tried", action="append", required=True, help="one attempted approach")
    explore.add_argument("--ruled-out", required=True, help="what the evidence excludes")
    explore.add_argument("--outcome", choices=("finding", "no-finding", "dead-end", "inconclusive"), required=True)
    explore.add_argument("--fault-proof", required=True, help="evidence that the injected fault occurred")
    explore.add_argument("--new-information", help="why a fresh or dead-end cell is being revisited")
    explore.add_argument("--journal", type=Path, default=JOURNAL_PATH, help="journal JSONL path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a probe command and return its process status."""
    args = build_parser().parse_args(argv)
    if args.command == "coverage":
        return _coverage(args)
    if args.command == "run":
        return _run_brief(args.brief, args.trials)
    if args.command == "explore":
        return _run_explore(args)
    if args.command == "checks":
        try:
            return _run_checks(args.runtime, args.run)
        except HarnessError as error:
            print(f"harness error: {error}", file=sys.stderr)
            return 2
    raise AssertionError(f"unhandled command: {args.command}")


def _run_brief(brief_id: str, trials: int | None) -> int:
    """Run a T4 brief and route a measured finding through the isolated oracle."""
    try:
        entry = run_brief(brief_id, trials=trials)
        if entry["outcome"] == "finding":
            entry["verdict"] = triage_finding(entry)
    except (HarnessError, OracleError) as error:
        print(f"harness error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(entry, sort_keys=True))
    return 0


def _coverage(args: argparse.Namespace) -> int:
    """Print claim counts and optionally regenerate the derived digest."""
    registry = load()
    try:
        if args.write:
            write_coverage(args.output, entries=load_journal(args.journal), claims=registry, ledger=load_ledger(args.ledger))
    except JournalError as error:
        print(f"journal error: {error}", file=sys.stderr)
        return 2
    covered, uncovered, stale = coverage_counts(registry)
    print(f"covered: {covered}")
    print(f"uncovered: {uncovered}")
    print(f"stale: {stale}")
    return 0


def _run_explore(args: argparse.Namespace) -> int:
    """Gate and record one completed author exploration before returning."""
    try:
        raw_cell = json.loads(args.cell)
        if not isinstance(raw_cell, list):
            raise JournalError("explore cell must be a JSON array")
        cell = normalize_cell(raw_cell)
        status = cell_status(cell, load_journal(args.journal))
        if status in {"fresh", "dead-end"} and args.new_information is None:
            raise JournalError(f"cell is {status}; pass --new-information to revisit it")
        entry: dict[str, object] = {
            "entry": f"explore-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}",
            "kind": "explore",
            "cell": list(cell),
            "tried": args.tried,
            "ruled_out": args.ruled_out,
            "outcome": args.outcome,
            "fault_proof": args.fault_proof,
        }
        if args.new_information is not None:
            entry["new_information"] = args.new_information
        append(entry, args.journal)
    except (json.JSONDecodeError, JournalError) as error:
        print(f"journal error: {error}", file=sys.stderr)
        return 2
    print(json.dumps(entry, sort_keys=True))
    return 0


def _run_checks(runtime: Path, run: str) -> int:
    paths = RunPaths.build(runtime, run)
    bus_events = events(paths)
    command_records = load_commands(paths)
    providers = {agent: provider(paths, agent) for agent in {event.agent for event in bus_events}}
    results = [
        *ignored_awaiting_human(bus_events, providers),
        no_teardown(bus_events, session_is_alive=session_exists(run)),
        polling_wait(command_records),
        screen_parsing(command_records),
        unwatermarked_send(command_records),
    ]
    fluency = {
        **asdict(measure(bus_events)),
        **asdict(measure_cmdlog(bus_events, command_records)),
    }
    payload = {
        "checks": [result.to_dict() for result in results],
        "fluency": fluency,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    append(
        {
            "entry": f"t5b-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}",
            "kind": "explore",
            "cell": ["C009", "human-interrupt", "orchestrator-loop", "claude", "1"],
            "tried": ["Route A cmdlog", "polling_wait", "screen_parsing", "unwatermarked_send"],
            "ruled_out": "cmdlog checks recorded from the probe-owned Bash hook",
            "outcome": _outcome(results),
            "fault_proof": f"direct command and bus reads for run {run}",
            "checks": payload["checks"],
            "fluency": payload["fluency"],
        }
    )
    return 0


def _outcome(results: Sequence[CheckResult]) -> str:
    verdicts = {result.verdict for result in results}
    if "violation" in verdicts:
        return "finding"
    if "inconclusive" in verdicts or "suspected" in verdicts:
        return "inconclusive"
    return "no-finding"


if __name__ == "__main__":
    raise SystemExit(main())
