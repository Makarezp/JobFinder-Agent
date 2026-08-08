"""Regression coverage for the durable probe journal and digest."""

from __future__ import annotations

from pathlib import Path

import pytest
from probe import probe
from probe.lib.claims import load as load_claims
from probe.lib.journal import JournalError, append, cell_status, load, regenerate_coverage


def _cell(claim: str = "C001") -> list[object]:
    return [claim, "none", "real-haiku", "claude", 1]


def _explore_entry(*, outcome: str = "no-finding", proof: str | None = "observed evidence") -> dict[str, object]:
    return {
        "entry": "E001",
        "kind": "explore",
        "cell": _cell(),
        "tried": ["fixture"],
        "ruled_out": "fixture outcome",
        "outcome": outcome,
        "fault_proof": proof,
    }


def test_regenerate_coverage_is_byte_identical_for_fixed_inputs() -> None:
    registry = load_claims()
    journal = [{**_explore_entry(), "claim_hash": registry[0].hash}]
    ledger = [
        {"brief": "B001", "rate": 0.0},
        {"brief": "B001", "rate": 1.0},
    ]

    assert regenerate_coverage(journal, claims=registry, ledger=ledger) == regenerate_coverage(journal, claims=registry, ledger=ledger)


def test_append_rejects_unevidenced_dead_end(tmp_path: Path) -> None:
    with pytest.raises(JournalError, match="requires fault_proof"):
        append(_explore_entry(outcome="dead-end", proof=None), tmp_path / "journal.jsonl")


def test_cell_status_marks_changed_claim_hash_stale() -> None:
    claim = load_claims()[0]
    entry = {**_explore_entry(), "claim_hash": "old-hash"}

    assert cell_status(_cell(), [entry], claims=[claim]) == "stale"


def test_legacy_entry_without_a_claim_hash_is_stale() -> None:
    assert cell_status(_cell(), [_explore_entry()]) == "stale"


def test_coverage_digest_never_exposes_absolute_artifact_paths() -> None:
    registry = load_claims()
    entry = {
        **_explore_entry(outcome="dead-end"),
        "ruled_out": "captured /tmp/probe-run and /Users/example/evidence",
        "claim_hash": registry[0].hash,
    }

    digest = regenerate_coverage([entry], claims=registry, ledger=[])

    assert "/tmp" not in digest
    assert "/Users" not in digest
    assert "E001: captured <artifact> and <artifact>" in digest


def test_explore_gate_refuses_fresh_cell_without_new_information(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    journal = tmp_path / "journal.jsonl"
    append(_explore_entry(), journal)
    arguments = [
        "explore",
        "--cell",
        '["C001", "none", "real-haiku", "claude", 1]',
        "--tried",
        "repeat fixture",
        "--ruled-out",
        "still ruled out",
        "--outcome",
        "no-finding",
        "--fault-proof",
        "repeat proof",
        "--journal",
        str(journal),
    ]

    assert probe.main(arguments) == 2
    assert "cell is fresh" in capsys.readouterr().err
    assert probe.main([*arguments, "--new-information", "new runtime release"]) == 0
    records = load(journal)
    assert len(records) == 2
    assert records[-1]["new_information"] == "new runtime release"


def test_coverage_write_includes_t4_claims_and_ranked_unvisited_cells(tmp_path: Path) -> None:
    output = tmp_path / "COVERAGE.md"

    assert probe.main(["coverage", "--write", "--output", str(output)]) == 0
    digest = output.read_text(encoding="utf-8")

    assert "<!-- GENERATED FILE" in digest
    assert "Covered (3): C003, C005, C014" in digest
    assert "## Ranked unvisited cells" in digest
    assert "1. C001 / none / real-haiku / claude / 1" in digest
