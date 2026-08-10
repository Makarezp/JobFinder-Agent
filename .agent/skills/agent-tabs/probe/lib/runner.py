"""Sequential real-worker execution for T4 conformance briefs."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agentctl import RunPaths, next_inbox_path

from probe.grades import GRADES
from probe.lib.assertions import HarnessError, ProbeFailure
from probe.lib.briefs import Brief, load_all, require_valid
from probe.lib.claims import load as load_claims
from probe.lib.ground import outbox_messages
from probe.lib.journal import append as append_journal
from probe.lib.ledger import append as append_ledger
from probe.lib.nonce import mint
from probe.lib.sut import Sut, create_sut, destroy_sut, spawn_command

TOOL_DIR = Path(__file__).resolve().parents[2]
ROLE_PATH = TOOL_DIR / "probe" / "roles" / "probe-worker.md"
WORKER_NAME = "worker"
MODEL = "haiku"
COMMIT = "1bb37a7"
READY_TIMEOUT = 120.0


@dataclass(frozen=True)
class TrialResult:
    """One trial's observable result and any preserved failure artifact."""

    passed: bool
    artifact: Path | None


def run_trials(brief: Brief, *, trials: int, control: bool) -> list[TrialResult]:
    """Run trials sequentially; concurrent tmux SUTs have no isolation story yet."""
    return [_run_trial(brief, index=index, control=control) for index in range(1, trials + 1)]


def run_brief(brief_id: str, *, trials: int | None = None) -> dict[str, object]:
    """Run a control then a target brief, recording the target's measured rate."""
    registry = require_valid(load_all(), load_claims(), GRADES)
    by_id = {brief.id: brief for brief in registry}
    try:
        brief = by_id[brief_id]
        control = by_id[brief.control]
    except KeyError as error:
        raise HarnessError(f"unknown brief {brief_id!r}") from error
    count = brief.trials if trials is None else trials
    if count <= 0:
        raise HarnessError("trials must be positive")

    started = datetime.now(UTC)
    control_results = run_trials(control, trials=count, control=True)
    control_rate = _rate(control_results)
    if control_rate < control.expect_rate:
        raise HarnessError(f"{brief.id}: control {control.id} rate {control_rate} below {control.expect_rate}")

    results = run_trials(brief, trials=count, control=False)
    rate = _rate(results)
    artifacts = [str(result.artifact) for result in results if result.artifact is not None]
    outcome = "no-finding" if rate >= brief.expect_rate else "finding"
    elapsed = (datetime.now(UTC) - started).total_seconds()
    entry = {
        "ts": started.isoformat().replace("+00:00", "Z"),
        "brief": brief.id,
        "cell": list(brief.cell),
        "commit": COMMIT,
        "model": MODEL,
        "trials": count,
        "passed": sum(result.passed for result in results),
        "rate": rate,
        "control_rate": control_rate,
        "outcome": outcome,
        "artifacts": artifacts,
        "entry": f"t4-{started.strftime('%Y%m%dT%H%M%S%fZ')}",
        "wall_seconds": elapsed,
    }
    append_ledger(entry)
    append_journal({"kind": "trial", **entry})
    return entry


def write_lost_doorbell(paths: RunPaths, agent: str, body: str) -> Path:
    """Write a send-identical inbox message without ringing a doorbell.

    The name comes from agentctl's source-of-truth scan and exclusive creation
    preserves an existing instruction if another writer wins the race.
    """
    candidate = next_inbox_path(paths, agent)
    with candidate.open("x", encoding="utf-8") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())
    return candidate


def _run_trial(brief: Brief, *, index: int, control: bool) -> TrialResult:
    sut = create_sut(f"{brief.id}-{'control-' if control else ''}{index}", spacey=True)
    failed = False
    harness_error: Exception | None = None
    try:
        bootstrap_watermark = _seq(sut)
        _spawn_worker(sut)
        _wait_for_bootstrap(sut, bootstrap_watermark)
        expected = _exercise(brief, sut, control=control)
        replies = [message.body for message in outbox_messages(sut, WORKER_NAME)]
        GRADES[brief.grade](brief.id, replies, expected, expected)
    except ProbeFailure:
        failed = True
    except (HarnessError, RuntimeError, subprocess.SubprocessError) as error:
        failed = True
        harness_error = error
    finally:
        artifact = destroy_sut(sut, preserve=failed)
    if harness_error is not None:
        raise HarnessError(f"{brief.id} trial {index} did not execute: {artifact}") from harness_error
    return TrialResult(passed=not failed, artifact=artifact)


def _spawn_worker(sut: Sut) -> None:
    command = spawn_command(
        sut,
        WORKER_NAME,
        ROLE_PATH,
        "Open your inbox, then reply exactly HANDSHAKE_READY via agentctl reply and wait.",
        model=MODEL,
    )
    command.extend(["--spawn-timeout", "90", "--bootstrap-timeout", "90"])
    completed = _invoke(sut, command[2:], timeout=100)
    if completed.returncode != 0:
        raise HarnessError(f"worker failed to spawn: {completed.stderr.strip()}")


def _exercise(brief: Brief, sut: Sut, *, control: bool) -> set[str]:
    if brief.id.startswith("B001"):
        return _inbox_discipline(brief, sut)
    if brief.id.startswith("B002"):
        return _lost_doorbell(brief, sut, control=control)
    if brief.id.startswith("B003"):
        return _watermark(brief, sut)
    raise HarnessError(f"no runner for brief {brief.id!r}")


def _inbox_discipline(brief: Brief, sut: Sut) -> set[str]:
    tokens = {mint() for _ in range(3)}
    for token in sorted(tokens):
        watermark = _seq(sut)
        _send(sut, _instruction(token))
        _wait_for_reply(brief, sut, watermark)
    return tokens


def _lost_doorbell(brief: Brief, sut: Sut, *, control: bool) -> set[str]:
    first, second, third = (mint() for _ in range(3))
    watermark = _seq(sut)
    _send(sut, _instruction(first))
    _wait_for_reply(brief, sut, watermark)
    if control:
        watermark = _seq(sut)
        _send(sut, _instruction(second))
        _wait_for_reply(brief, sut, watermark)
    else:
        write_lost_doorbell(RunPaths.build(sut.runtime, sut.run), WORKER_NAME, _instruction(second))
    watermark = _seq(sut)
    _send(sut, _instruction(third))
    _wait_for_reply(brief, sut, watermark)
    _wait_for_turn_end(brief, sut, watermark)
    return {first, second, third}


def _watermark(brief: Brief, sut: Sut) -> set[str]:
    token = mint()
    watermark = _seq(sut)
    _send(sut, _instruction(token), force=True)
    _wait_for_reply(brief, sut, watermark)
    after_reply = _seq(sut)
    completed = _invoke(
        sut,
        ["wait", "--until", f"agent={WORKER_NAME},type=reply", "--from-seq", str(after_reply), "--timeout", str(brief.wait_timeout)],
        timeout=brief.wait_timeout + 5,
    )
    if completed.returncode != 2 or completed.stdout:
        raise ProbeFailure(brief.id, "timeout after reply watermark", completed.stdout)
    return {token}


def _send(sut: Sut, body: str, *, force: bool = False) -> None:
    arguments = ["send", WORKER_NAME, body]
    if force:
        arguments.append("--force")
    else:
        arguments.extend(["--wait-idle", str(READY_TIMEOUT)])
    completed = _invoke(sut, arguments, timeout=READY_TIMEOUT + 5)
    if completed.returncode != 0:
        raise HarnessError(f"send did not deliver: {completed.stderr.strip()} {completed.stdout.strip()}")


def _wait_for_bootstrap(sut: Sut, watermark: int) -> None:
    """Wait for the durable bootstrap reply before taking send watermarks."""
    completed = _invoke(
        sut,
        [
            "wait",
            "--until",
            f"agent={WORKER_NAME},type=reply",
            "--from-seq",
            str(watermark),
            "--timeout",
            str(READY_TIMEOUT),
        ],
        timeout=READY_TIMEOUT + 5,
    )
    if completed.returncode != 0:
        raise HarnessError(f"worker bootstrap did not finish: {completed.stderr.strip()}")


def _instruction(token: str) -> str:
    """Make the nonce an explicit, low-ambiguity worker instruction."""
    return f"Probe instruction: reply with the token you consumed this turn.\n{token}"


def _wait_for_reply(brief: Brief, sut: Sut, watermark: int) -> None:
    completed = _invoke(
        sut,
        [
            "wait",
            "--until",
            f"agent={WORKER_NAME},type=reply",
            "--from-seq",
            str(watermark),
            "--timeout",
            str(brief.wait_timeout),
        ],
        timeout=brief.wait_timeout + 5,
    )
    if completed.returncode != 0:
        raise HarnessError(f"worker did not reply before timeout: {completed.stderr.strip()}")


def _wait_for_turn_end(brief: Brief, sut: Sut, watermark: int) -> None:
    completed = _invoke(
        sut,
        [
            "wait",
            "--until",
            f"agent={WORKER_NAME},type=turn_end",
            "--from-seq",
            str(watermark),
            "--timeout",
            str(brief.wait_timeout),
        ],
        timeout=brief.wait_timeout + 5,
    )
    if completed.returncode != 0:
        raise HarnessError(f"worker did not finish its turn before timeout: {completed.stderr.strip()}")


def _seq(sut: Sut) -> int:
    completed = _invoke(sut, ["seq"], timeout=10)
    if completed.returncode != 0:
        raise HarnessError(f"could not capture sequence watermark: {completed.stderr.strip()}")
    try:
        return int(completed.stdout.strip())
    except ValueError as error:
        raise HarnessError(f"invalid sequence watermark: {completed.stdout!r}") from error


def _invoke(sut: Sut, arguments: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(sut.agentctl), *arguments, "--runtime", str(sut.runtime), "--run", sut.run],
        env=sut.env,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _rate(results: list[TrialResult]) -> float:
    return sum(result.passed for result in results) / len(results)
