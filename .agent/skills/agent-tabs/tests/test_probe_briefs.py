"""Regression coverage for T4 real-worker conformance briefs."""

from __future__ import annotations

from pathlib import Path

import agentctl
import pytest
from probe import probe
from probe.grades import GRADES, grade_tokens
from probe.lib.assertions import HarnessError, ProbeFailure
from probe.lib.briefs import load_all, validate
from probe.lib.claims import load as load_claims
from probe.lib.runner import TrialResult, run_brief, write_lost_doorbell


def test_seeded_briefs_resolve_claims_controls_grades_and_timeouts() -> None:
    """Every checked-in brief is executable metadata, not unchecked prose."""
    briefs = load_all()
    assert validate(briefs, load_claims(), GRADES) == []
    assert {brief.id for brief in briefs} == {
        "B001",
        "B001-control",
        "B002",
        "B002-control",
        "B003",
        "B003-control",
    }
    assert all(brief.wait_timeout == 10 for brief in briefs)


def test_b002_token_grade_rejects_a_missing_nonce() -> None:
    expected = {"TOK-ABCD", "TOK-EFGH", "TOK-HJKM"}
    with pytest.raises(ProbeFailure):
        grade_tokens("B002", ["TOK-ABCD\nTOK-EFGH"], expected, expected)


def test_b002_token_grade_allows_ordinary_worker_prose() -> None:
    expected = {"TOK-ABCD", "TOK-EFGH", "TOK-HJKM"}
    grade_tokens("B002", ["TOK-ABCD TODO JSON DONE\nTOK-EFGH\nTOK-HJKM"], expected, expected)


def test_lost_doorbell_file_uses_agentctl_filename_and_exact_body(tmp_path: Path) -> None:
    paths = agentctl.RunPaths.build(tmp_path, "brief")
    agentctl.write_inbox(paths, "worker", "bootstrap")
    agentctl.write_inbox(paths, "worker", "message A")

    path = write_lost_doorbell(paths, "worker", "message B")

    assert path.name == f"{3:0{agentctl.INBOX_WIDTH}d}.md"
    assert path.read_text(encoding="utf-8") == "message B"


def test_control_failure_is_harness_error_and_writes_no_finding_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing control blocks target grading instead of manufacturing a finding."""
    ledger: list[dict[str, object]] = []
    monkeypatch.setattr("probe.lib.runner.run_trials", _failed_control)
    monkeypatch.setattr("probe.lib.runner.append_ledger", ledger.append)

    with pytest.raises(HarnessError):
        run_brief("B002", trials=1)

    assert ledger == []


def test_probe_command_returns_two_for_harness_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_: str, *, trials: int | None) -> dict[str, object]:
        raise HarnessError("control failed")

    monkeypatch.setattr(probe, "run_brief", fail)
    assert probe._run_brief("B002", 1) == 2


def _failed_control(*_: object, **__: object) -> list[TrialResult]:
    return [TrialResult(passed=False, artifact=None)]
