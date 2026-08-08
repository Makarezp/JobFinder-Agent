"""Regression coverage for T7 oracle triage and quarantined specification emission."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from probe.lib.journal import JournalError, append, load
from probe.lib.oracle import OracleError, OracleReply, parse_reply, triage_finding
from probe.lib.sut import Sut


def _finding() -> dict[str, object]:
    return {
        "entry": "t4-fixture",
        "kind": "trial",
        "cell": ["C014", "inbox-discipline", "real-haiku", "claude", 1],
        "brief": "B001",
        "commit": "1bb37a7",
        "model": "haiku",
        "trials": 10,
        "passed": 6,
        "rate": 0.6,
        "control_rate": 1.0,
        "outcome": "finding",
        "artifacts": ["/tmp/preserved-t4-fixture"],
        "wall_seconds": 12.0,
    }


def _verdict(*, verdict: str, claim: str | None) -> dict[str, object]:
    return {
        "entry": "verdict-fixture",
        "kind": "verdict",
        "cell": ["C014", "inbox-discipline", "real-haiku", "claude", 1],
        "verdict": verdict,
        "claim": claim,
        "trial_entry": "t4-fixture",
        "brief": "B001",
        "rate": 0.6,
        "control_rate": 1.0,
        "commit": "1bb37a7",
        "artifacts": ["/tmp/preserved-t4-fixture"],
        "summary": "fixture summary",
        "evidence": "fixture evidence",
    }


@pytest.mark.parametrize("verdict", ["code", "doc-rewrite"])
def test_journal_rejects_claimless_citation_verdicts(tmp_path: Path, verdict: str) -> None:
    with pytest.raises(JournalError, match="requires a claim citation"):
        append(_verdict(verdict=verdict, claim=None), tmp_path / "journal.jsonl")


def test_duplicate_claim_skips_oracle_and_emits_no_second_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    spec_directory = tmp_path / "probe"
    spec_directory.mkdir()
    existing = spec_directory / "prior.md"
    existing.write_text("---\nstatus: open\nclaim: C014\n---\n", encoding="utf-8")

    def should_not_run(_: object) -> OracleReply:
        raise AssertionError("duplicate claim must not invoke oracle")

    monkeypatch.setattr("probe.lib.oracle.invoke_oracle", should_not_run)
    journal = tmp_path / "journal.jsonl"

    verdict = triage_finding(_finding(), journal=journal, spec_directory=spec_directory)

    assert verdict["verdict"] == "duplicate"
    assert list(spec_directory.glob("*.md")) == [existing]
    assert load(journal)[0]["verdict"] == "duplicate"


def test_oracle_emits_quarantined_spec_with_required_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reply = OracleReply(
        verdict="doc-rewrite",
        claim="C014",
        summary="The worker ignored a clear inbox-read requirement.",
        evidence="The preserved outbox omits the second token.",
        requirements=("Revise WORKER.md so every turn reads the inbox before work.",),
    )
    monkeypatch.setattr("probe.lib.oracle.invoke_oracle", lambda _: reply)
    spec_directory = tmp_path / "probe"

    verdict = triage_finding(_finding(), journal=tmp_path / "journal.jsonl", spec_directory=spec_directory)

    spec = Path(str(verdict["spec"]))
    content = spec.read_text(encoding="utf-8")
    assert spec.parent == spec_directory
    assert "brief: B001" in content
    assert "claim: C014" in content
    assert "rate: 0.6" in content
    assert "commit: 1bb37a7" in content
    assert "journal_entry: t4-fixture" in content
    assert "/tmp/preserved-t4-fixture" in content
    assert "## 1. Overview" in content
    assert ".agent/skills/agent-tabs/SKILL.md or .agent/skills/agent-tabs/WORKER.md" in content
    assert "## 2. Functional Requirements" in content
    assert "## 3. Verification & Acceptance Criteria" in content


def test_doc_gap_requires_null_claim_and_spec_requirements() -> None:
    with pytest.raises(OracleError, match="must use claim null"):
        parse_reply('{"verdict":"doc-gap","claim":"C014","summary":"x","evidence":"y","requirements":["z"]}')
    with pytest.raises(OracleError, match="requires requirements"):
        parse_reply('{"verdict":"code","claim":"C014","summary":"x","evidence":"y","requirements":[]}')


def test_oracle_task_bounds_artifact_inspection() -> None:
    from probe.lib import oracle

    task = oracle._oracle_task(oracle.finding_envelope(_finding()))

    assert "never recurse or inspect .omc" in task
    assert task.endswith(
        '{"artifacts": ["/tmp/preserved-t4-fixture"], "brief": "B001", "claim": "C014", '
        '"commit": "1bb37a7", "control_rate": 1.0, "entry": "t4-fixture", "rate": 0.6}'
    )


def test_oracle_uses_a_separate_harness_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from probe.lib import oracle

    harness = Sut(runtime=tmp_path / "oracle-runtime", run="oracle-run", agentctl=tmp_path / "agentctl.py", env={})
    calls: list[object] = []

    def fake_create(brief_id: str, *, spacey: bool) -> Sut:
        calls.append((brief_id, spacey))
        return harness

    def fake_spawn(subject: Sut, *_: object, **__: object) -> list[str]:
        calls.append(subject)
        return ["spawn"]

    def fake_wait(subject: Sut) -> None:
        calls.append(subject)

    def fake_destroy(subject: Sut, *, preserve: bool) -> None:
        calls.append((subject, preserve))

    monkeypatch.setattr(oracle, "create_sut", fake_create)
    monkeypatch.setattr(oracle, "spawn_command", fake_spawn)
    monkeypatch.setattr(oracle, "_spawn_oracle", lambda _subject, _command: SimpleNamespace(returncode=0, stderr=""))
    monkeypatch.setattr(oracle, "_wait_for_reply", fake_wait)
    monkeypatch.setattr(
        oracle,
        "outbox_messages",
        lambda _subject, _agent: [SimpleNamespace(body='{"verdict":"harness","claim":null,"summary":"x","evidence":"y","requirements":[]}')],
    )
    monkeypatch.setattr(oracle, "destroy_sut", fake_destroy)

    reply = oracle.invoke_oracle(oracle.finding_envelope(_finding()))

    assert reply.verdict == "harness"
    assert calls == [
        ("oracle-t4-fixture", True),
        harness,
        harness,
        (harness, False),
    ]
