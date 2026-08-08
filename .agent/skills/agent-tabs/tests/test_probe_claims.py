"""Regression coverage for the hand-seeded claim registry."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from probe import probe
from probe.lib.claims import Claim, hash_of, load, stale, uncovered

TOOL_DIR = Path(__file__).resolve().parents[1]


class CapturedOutput(Protocol):
    """The subset of pytest's capture result used by this test."""

    out: str


class CapturedOutputFixture(Protocol):
    """The subset of pytest's capture fixture used by this test."""

    def readouterr(self) -> CapturedOutput: ...


def _fixture_claim(source_hash: str) -> Claim:
    return Claim(
        id="C999",
        src="fixture.md:2-2",
        section="Fixture",
        text="fixture claim",
        kind="invariant",
        briefs=(),
        hash=source_hash,
    )


def test_seeded_claims_resolve_to_current_source_and_existing_briefs() -> None:
    """Protocol edits must make a stale registry entry visible immediately."""
    for claim in load():
        assert hash_of(claim) == claim.hash
        for brief in claim.briefs:
            assert (TOOL_DIR / "probe" / "briefs" / f"{brief}.md").is_file()


def test_stale_only_changes_when_its_referenced_source_changes(tmp_path: Path) -> None:
    """Unrelated edits must not discard a valid claim's coverage."""
    source = tmp_path / "fixture.md"
    source.write_text("before\ntarget\nafter\n", encoding="utf-8")
    claim = _fixture_claim(hash_of(_fixture_claim(""), root=tmp_path))

    assert stale([claim], root=tmp_path) == []

    source.write_text("changed-before\ntarget\nafter\n", encoding="utf-8")
    assert stale([claim], root=tmp_path) == []

    source.write_text("changed-before\nchanged-target\nafter\n", encoding="utf-8")
    assert stale([claim], root=tmp_path) == [claim]


def test_uncovered_returns_only_claims_without_briefs() -> None:
    """A registry entry becomes covered only when a brief explicitly names it."""
    uncovered_claim = _fixture_claim("hash")
    covered_claim = Claim(
        id="C998",
        src=uncovered_claim.src,
        section=uncovered_claim.section,
        text=uncovered_claim.text,
        kind=uncovered_claim.kind,
        briefs=("B001",),
        hash=uncovered_claim.hash,
    )

    assert uncovered([uncovered_claim, covered_claim]) == [uncovered_claim]


def test_coverage_command_reports_registry_counts(capsys: CapturedOutputFixture) -> None:
    """The human-facing command reports covered, uncovered, and stale claims."""
    assert probe.main(["coverage"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "covered: 0\nuncovered: 15\nstale: 0\n"
