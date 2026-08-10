"""Validated T7 finding triage and quarantined specification emission."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from probe.lib.assertions import HarnessError
from probe.lib.claims import Claim
from probe.lib.claims import load as load_claims
from probe.lib.ground import outbox_messages
from probe.lib.journal import JOURNAL_PATH, append, normalize_cell
from probe.lib.sut import Sut, create_sut, destroy_sut, spawn_command

TOOL_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = TOOL_DIR.parents[2]
ORACLE_ROLE = TOOL_DIR / "probe" / "roles" / "oracle.md"
SPEC_DIRECTORY = REPOSITORY_ROOT / "work_organisation" / "probe"
ORACLE_NAME = "oracle"
ORACLE_MODEL = "opus"
ORACLE_TIMEOUT = 300.0

VerdictKind = Literal["code", "doc-gap", "doc-rewrite", "harness", "duplicate"]
VERDICTS: frozenset[str] = frozenset({"code", "doc-gap", "doc-rewrite", "harness", "duplicate"})
SPEC_VERDICTS: frozenset[str] = frozenset({"code", "doc-gap", "doc-rewrite"})
_CLAIM_VERDICTS: frozenset[str] = frozenset({"code", "doc-rewrite", "duplicate"})


class OracleError(HarnessError):
    """The oracle envelope, reply, or isolated harness failed validation."""


@dataclass(frozen=True)
class FindingEnvelope:
    """The complete, machine-derived input supplied to the oracle."""

    brief: str
    rate: float
    claim: str
    control_rate: float
    artifacts: tuple[str, ...]
    commit: str
    entry: str
    cell: tuple[str, str, str, str, str]

    def payload(self) -> dict[str, object]:
        """Return the fixed, JSON-only oracle input envelope."""
        return {
            "brief": self.brief,
            "rate": self.rate,
            "claim": self.claim,
            "control_rate": self.control_rate,
            "artifacts": list(self.artifacts),
            "commit": self.commit,
            "entry": self.entry,
        }


@dataclass(frozen=True)
class OracleReply:
    """A schema-checked verdict returned through the oracle's durable outbox."""

    verdict: VerdictKind
    claim: str | None
    summary: str
    evidence: str
    requirements: tuple[str, ...]


def finding_envelope(entry: dict[str, object]) -> FindingEnvelope:
    """Validate one T4 finding record before it reaches any model."""
    if entry.get("outcome") != "finding":
        raise OracleError("oracle requires a finding trial entry")
    brief = _required_string(entry, "brief")
    commit = _required_string(entry, "commit")
    entry_id = _required_string(entry, "entry")
    raw_cell = entry.get("cell")
    if not isinstance(raw_cell, list):
        raise OracleError("finding trial entry requires a cell array")
    cell = normalize_cell(raw_cell)
    rate = _number(entry, "rate")
    control_rate = _number(entry, "control_rate")
    raw_artifacts = entry.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts or not all(isinstance(path, str) and path for path in raw_artifacts):
        raise OracleError("finding trial entry requires a preserved artifact path")
    return FindingEnvelope(
        brief=brief,
        rate=rate,
        claim=cell[0],
        control_rate=control_rate,
        artifacts=tuple(raw_artifacts),
        commit=commit,
        entry=entry_id,
        cell=cell,
    )


def parse_reply(body: str, *, claims: tuple[Claim, ...] | None = None) -> OracleReply:
    """Parse the oracle's sole structured reply; prose is not a valid verdict."""
    try:
        raw: object = json.loads(body)
    except json.JSONDecodeError as error:
        raise OracleError("oracle reply must be a JSON object") from error
    if not isinstance(raw, dict):
        raise OracleError("oracle reply must be a JSON object")
    verdict = raw.get("verdict")
    if verdict not in VERDICTS:
        raise OracleError(f"oracle reply has invalid verdict {verdict!r}")
    claim = raw.get("claim")
    if claim is not None and (not isinstance(claim, str) or not claim):
        raise OracleError("oracle reply claim must be a non-empty string or null")
    if verdict in _CLAIM_VERDICTS and claim is None:
        raise OracleError(f"{verdict} verdict requires a claim citation")
    if verdict == "doc-gap" and claim is not None:
        raise OracleError("doc-gap verdict must use claim null")
    registry = {item.id for item in (load_claims() if claims is None else claims)}
    if claim is not None and claim not in registry:
        raise OracleError(f"oracle reply cites unknown claim {claim!r}")
    summary = _required_string(raw, "summary")
    evidence = _required_string(raw, "evidence")
    requirements = _requirements(raw, required=verdict in SPEC_VERDICTS)
    return OracleReply(
        verdict=verdict,
        claim=claim,
        summary=summary,
        evidence=evidence,
        requirements=requirements,
    )


def open_spec_for_claim(claim: str, directory: Path = SPEC_DIRECTORY) -> Path | None:
    """Find the first open quarantined spec with an exact claim metadata field."""
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("*.md")):
        metadata = _frontmatter(path)
        if metadata.get("status") == "open" and metadata.get("claim") == claim:
            return path
    return None


def triage_finding(
    entry: dict[str, object],
    *,
    journal: Path = JOURNAL_PATH,
    spec_directory: Path = SPEC_DIRECTORY,
) -> dict[str, object]:
    """Route a measured finding once, append its verdict, and possibly emit a spec."""
    envelope = finding_envelope(entry)
    existing = open_spec_for_claim(envelope.claim, spec_directory)
    reply = (
        OracleReply(
            verdict="duplicate",
            claim=envelope.claim,
            summary=f"Open spec already exists: {existing.name}",
            evidence=str(existing),
            requirements=(),
        )
        if existing is not None
        else invoke_oracle(envelope)
    )
    verdict = _verdict_entry(envelope, reply)
    if reply.verdict in SPEC_VERDICTS:
        verdict["spec"] = str(emit_spec(envelope, reply, directory=spec_directory))
    append(verdict, journal)
    return verdict


def invoke_oracle(envelope: FindingEnvelope) -> OracleReply:
    """Run the oracle in its own disposable harness runtime, never the judged SUT."""
    if not ORACLE_ROLE.is_file():
        raise OracleError(f"oracle role is missing: {ORACLE_ROLE}")
    harness = create_sut(f"oracle-{envelope.entry}", spacey=True)
    try:
        command = spawn_command(
            harness,
            ORACLE_NAME,
            ORACLE_ROLE,
            _oracle_task(envelope),
            model=ORACLE_MODEL,
        )
        command.extend(["--spawn-timeout", "120", "--bootstrap-timeout", "120"])
        started = _spawn_oracle(harness, command)
        if started.returncode != 0:
            raise OracleError(f"oracle failed to spawn: {started.stderr.strip()}")
        _wait_for_reply(harness)
        replies = outbox_messages(harness, ORACLE_NAME)
        if len(replies) != 1:
            raise OracleError(f"oracle produced {len(replies)} replies; expected exactly one")
        return parse_reply(replies[0].body)
    except (OSError, subprocess.SubprocessError) as error:
        raise OracleError(f"oracle harness failed: {error}") from error
    finally:
        destroy_sut(harness, preserve=False)


def _spawn_oracle(harness: Sut, command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, env=harness.env, text=True, capture_output=True, check=False, timeout=130)


def emit_spec(envelope: FindingEnvelope, reply: OracleReply, *, directory: Path = SPEC_DIRECTORY) -> Path:
    """Write one quarantined, human-promotable specification without modifying the SUT."""
    if reply.verdict not in SPEC_VERDICTS:
        raise OracleError(f"{reply.verdict} verdict must not emit a spec")
    directory.mkdir(parents=True, exist_ok=True)
    claim = reply.claim if reply.claim is not None else "null"
    path = directory / f"{_slug(envelope.entry)}-{claim.lower()}.md"
    content = _spec_content(envelope, reply)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError as error:
        raise OracleError(f"refusing to overwrite probe spec {path}") from error
    return path


def _verdict_entry(envelope: FindingEnvelope, reply: OracleReply) -> dict[str, object]:
    return {
        "entry": f"verdict-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}",
        "kind": "verdict",
        "cell": list(envelope.cell),
        "verdict": reply.verdict,
        "claim": reply.claim,
        "trial_entry": envelope.entry,
        "brief": envelope.brief,
        "rate": envelope.rate,
        "control_rate": envelope.control_rate,
        "commit": envelope.commit,
        "artifacts": list(envelope.artifacts),
        "summary": reply.summary,
        "evidence": reply.evidence,
    }


def _oracle_task(envelope: FindingEnvelope) -> str:
    return (
        "Triage exactly one probe finding. Read your role. Inspect only the explicitly allowed artifact files; "
        "never recurse or inspect .omc. Decide after those files and reply exactly once through agentctl reply "
        "with one JSON object matching the role schema. Do not modify any file.\\n\\n"
        f"{json.dumps(envelope.payload(), sort_keys=True)}"
    )


def _wait_for_reply(harness: Sut) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(harness.agentctl),
            "wait",
            "--until",
            f"agent={ORACLE_NAME},type=reply",
            "--from-seq",
            "0",
            "--timeout",
            str(ORACLE_TIMEOUT),
            "--runtime",
            str(harness.runtime),
            "--run",
            harness.run,
        ],
        env=harness.env,
        text=True,
        capture_output=True,
        check=False,
        timeout=ORACLE_TIMEOUT + 10,
    )
    if completed.returncode != 0:
        raise OracleError(f"oracle did not reply: {completed.stderr.strip()}")


def _spec_content(envelope: FindingEnvelope, reply: OracleReply) -> str:
    claim = reply.claim if reply.claim is not None else "null"
    requirements = "\n".join(f"* [ ] {requirement}" for requirement in reply.requirements)
    artifacts = "\n".join(f"* `{artifact}`" for artifact in envelope.artifacts)
    return (
        "---\n"
        "status: open\n"
        f"brief: {envelope.brief}\n"
        f"claim: {claim}\n"
        f"rate: {envelope.rate:.6g}\n"
        f"control_rate: {envelope.control_rate:.6g}\n"
        f"commit: {envelope.commit}\n"
        f"journal_entry: {envelope.entry}\n"
        "---\n\n"
        f"# Specification: Probe finding {envelope.entry}\n\n"
        "## 1. Overview\n"
        f"* **Summary:** {reply.summary}\n"
        f"* **Context:** Oracle verdict `{reply.verdict}` for brief `{envelope.brief}` and claim `{claim}`.\n"
        f"* **Target:** `{_target_for(reply.verdict)}`.\n"
        f"* **Evidence:** {reply.evidence}\n"
        "* **Preserved artifacts:**\n"
        f"{artifacts}\n\n"
        "## 2. Functional Requirements\n"
        f"{requirements}\n\n"
        "## 3. Verification & Acceptance Criteria\n"
        "* [ ] Reproduce from the preserved artifact paths above.\n"
        f"* [ ] Verify the stated `{reply.verdict}` disposition against brief `{envelope.brief}`.\n"
    )


def _target_for(verdict: VerdictKind) -> str:
    return {
        "code": ".agent/skills/agent-tabs/agentctl.py",
        "doc-gap": ".agent/skills/agent-tabs/probe/claims.jsonl",
        "doc-rewrite": ".agent/skills/agent-tabs/SKILL.md or .agent/skills/agent-tabs/WORKER.md",
    }.get(verdict, "No specification emitted")


def _required_string(entry: dict[str, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise OracleError(f"oracle {key} must be a non-empty string")
    return value


def _number(entry: dict[str, object], key: str) -> float:
    value = entry.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise OracleError(f"oracle {key} must be numeric")
    return float(value)


def _requirements(entry: dict[str, object], *, required: bool) -> tuple[str, ...]:
    value = entry.get("requirements", [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise OracleError("oracle requirements must be non-empty strings")
    if required and not value:
        raise OracleError("spec-emitting oracle verdict requires requirements")
    return tuple(value)


def _frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return {}
    metadata: dict[str, str] = {}
    for line in lines[1:]:
        if line == "---":
            return metadata
        key, separator, value = line.partition(":")
        if not separator:
            return {}
        metadata[key.strip()] = value.strip()
    return {}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
