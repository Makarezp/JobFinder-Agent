"""Typed conformance-brief loading and structural validation."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from probe.lib.claims import Claim

TOOL_DIR = Path(__file__).resolve().parents[2]
BRIEFS_DIR = TOOL_DIR / "probe" / "briefs"


class BriefError(ValueError):
    """A conformance brief is malformed or does not resolve to its dependencies."""


@dataclass(frozen=True)
class Brief:
    """A human-authored scenario with all machine-executed parameters explicit."""

    id: str
    claim: str
    cell: tuple[str, str, str, str, int]
    trials: int
    expect_rate: float
    control: str
    wait_timeout: float
    grade: str
    body: str
    path: Path


def load(path: Path) -> Brief:
    """Load one YAML-front-matter brief without depending on a YAML parser."""
    front_matter, body = _front_matter(path)
    return Brief(
        id=_string(front_matter, "id", path),
        claim=_string(front_matter, "claim", path),
        cell=_cell(front_matter, path),
        trials=_positive_int(front_matter, "trials", path),
        expect_rate=_rate(front_matter, path),
        control=_string(front_matter, "control", path),
        wait_timeout=_positive_float(front_matter, "wait_timeout", path),
        grade=_string(front_matter, "grade", path),
        body=body,
        path=path,
    )


def load_all(directory: Path = BRIEFS_DIR) -> list[Brief]:
    """Load briefs in deterministic identifier order."""
    return sorted((load(path) for path in directory.glob("*.md")), key=lambda brief: brief.id)


def validate(briefs: Iterable[Brief], claims: Iterable[Claim], grades: Mapping[str, object]) -> list[BriefError]:
    """Return every cross-reference error without starting tmux or a model."""
    registry = list(briefs)
    claim_ids = {claim.id for claim in claims}
    brief_ids = {brief.id for brief in registry}
    errors: list[BriefError] = []
    if len(brief_ids) != len(registry):
        errors.append(BriefError("duplicate brief id"))
    for brief in registry:
        if brief.claim not in claim_ids:
            errors.append(BriefError(f"{brief.id}: unknown claim {brief.claim!r}"))
        if brief.control not in brief_ids:
            errors.append(BriefError(f"{brief.id}: unknown control {brief.control!r}"))
        if brief.grade not in grades:
            errors.append(BriefError(f"{brief.id}: unknown grade {brief.grade!r}"))
    return errors


def require_valid(briefs: Iterable[Brief], claims: Iterable[Claim], grades: Mapping[str, object]) -> list[Brief]:
    """Return validated briefs or raise one summary error."""
    registry = list(briefs)
    errors = validate(registry, claims, grades)
    if errors:
        raise BriefError("; ".join(str(error) for error in errors))
    return registry


def _front_matter(path: Path) -> tuple[dict[str, str], str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise BriefError(f"{path}: missing opening front-matter delimiter")
    try:
        closing = lines.index("---", 1)
    except ValueError as error:
        raise BriefError(f"{path}: missing closing front-matter delimiter") from error
    fields: dict[str, str] = {}
    for line in lines[1:closing]:
        key, separator, value = line.partition(":")
        if not separator or not key or not value.strip() or key in fields:
            raise BriefError(f"{path}: invalid front-matter line {line!r}")
        fields[key] = value.strip()
    return fields, "\n".join(lines[closing + 1 :]).strip()


def _string(fields: Mapping[str, str], key: str, path: Path) -> str:
    value = fields.get(key)
    if value is None or not value:
        raise BriefError(f"{path}: missing {key!r}")
    return value


def _positive_int(fields: Mapping[str, str], key: str, path: Path) -> int:
    try:
        value = int(_string(fields, key, path))
    except ValueError as error:
        raise BriefError(f"{path}: {key!r} must be an integer") from error
    if value <= 0:
        raise BriefError(f"{path}: {key!r} must be positive")
    return value


def _positive_float(fields: Mapping[str, str], key: str, path: Path) -> float:
    try:
        value = float(_string(fields, key, path))
    except ValueError as error:
        raise BriefError(f"{path}: {key!r} must be a number") from error
    if value <= 0:
        raise BriefError(f"{path}: {key!r} must be positive")
    return value


def _rate(fields: Mapping[str, str], path: Path) -> float:
    value = _positive_float(fields, "expect_rate", path)
    if value > 1:
        raise BriefError(f"{path}: 'expect_rate' must be at most 1")
    return value


def _cell(fields: Mapping[str, str], path: Path) -> tuple[str, str, str, str, int]:
    try:
        raw: object = json.loads(_string(fields, "cell", path))
    except json.JSONDecodeError as error:
        raise BriefError(f"{path}: 'cell' must be a JSON array") from error
    if not isinstance(raw, list) or len(raw) != 5:
        raise BriefError(f"{path}: 'cell' must have five values")
    first, second, third, fourth, fifth = raw
    if not all(isinstance(value, str) and value for value in (first, second, third, fourth)):
        raise BriefError(f"{path}: first four cell values must be non-empty strings")
    if not isinstance(fifth, int) or isinstance(fifth, bool) or fifth <= 0:
        raise BriefError(f"{path}: final cell value must be a positive integer")
    return first, second, third, fourth, fifth
