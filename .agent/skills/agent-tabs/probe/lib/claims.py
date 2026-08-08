"""Claim-registry loading and source-drift detection.

The registry deliberately records only human-verified claims.  Its hashes make
an edit to the protocol documents visible to later probe authors instead of
silently preserving stale coverage.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

TOOL_DIR = Path(__file__).resolve().parents[2]
CLAIMS_PATH = TOOL_DIR / "probe" / "claims.jsonl"

ClaimKind = Literal[
    "worker-behavior",
    "orchestrator-behavior",
    "gate",
    "lifecycle",
    "invariant",
]
CLAIM_KINDS: frozenset[str] = frozenset(
    {
        "worker-behavior",
        "orchestrator-behavior",
        "gate",
        "lifecycle",
        "invariant",
    }
)
SOURCE_PATTERN = re.compile(r"(?P<filename>[^:]+):(?P<first>[1-9]\d*)-(?P<last>[1-9]\d*)\Z")


class ClaimError(ValueError):
    """A registry entry cannot be read or resolved against its source."""


@dataclass(frozen=True)
class Claim:
    """One normative proposition and the document excerpt that supports it."""

    id: str
    src: str
    section: str
    text: str
    kind: ClaimKind
    briefs: tuple[str, ...]
    hash: str


def load(path: Path = CLAIMS_PATH) -> list[Claim]:
    """Load the hand-authored JSONL registry, rejecting malformed entries."""
    claims: list[Claim] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw: object = json.loads(line)
        except json.JSONDecodeError as error:
            raise ClaimError(f"{path}:{line_number}: invalid JSON") from error
        if not isinstance(raw, dict):
            raise ClaimError(f"{path}:{line_number}: claim must be an object")
        claim = _claim_from_mapping(cast(Mapping[str, object], raw), path, line_number)
        if claim.id in seen_ids:
            raise ClaimError(f"{path}:{line_number}: duplicate claim id {claim.id!r}")
        seen_ids.add(claim.id)
        claims.append(claim)
    return claims


def hash_of(claim: Claim, *, root: Path = TOOL_DIR) -> str:
    """Hash the exact, inclusive source lines named by ``claim.src``."""
    path, first, last = _source_range(claim.src, root)
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if last > len(lines):
        raise ClaimError(f"{claim.src}: line range exceeds {path}")
    return hashlib.sha256("".join(lines[first - 1 : last]).encode("utf-8")).hexdigest()


def stale(claims: Iterable[Claim] | None = None, *, root: Path = TOOL_DIR) -> list[Claim]:
    """Return claims whose source moved, disappeared, or no longer matches."""
    registry = list(load() if claims is None else claims)
    stale_claims: list[Claim] = []
    for claim in registry:
        try:
            current_hash = hash_of(claim, root=root)
        except ClaimError:
            stale_claims.append(claim)
            continue
        if current_hash != claim.hash:
            stale_claims.append(claim)
    return stale_claims


def uncovered(claims: Iterable[Claim] | None = None) -> list[Claim]:
    """Return claims with no conformance brief assigned."""
    registry = list(load() if claims is None else claims)
    return [claim for claim in registry if not claim.briefs]


def coverage_counts(claims: Iterable[Claim] | None = None) -> tuple[int, int, int]:
    """Return covered, uncovered, and stale counts for the current registry."""
    registry = list(load() if claims is None else claims)
    stale_ids = {claim.id for claim in stale(registry)}
    covered_count = sum(bool(claim.briefs) and claim.id not in stale_ids for claim in registry)
    return covered_count, len(uncovered(registry)), len(stale_ids)


def _claim_from_mapping(payload: Mapping[str, object], path: Path, line_number: int) -> Claim:
    kind = _required_string(payload, "kind", path, line_number)
    if kind not in CLAIM_KINDS:
        raise ClaimError(f"{path}:{line_number}: invalid claim kind {kind!r}")
    briefs = _briefs(payload, path, line_number)
    return Claim(
        id=_required_string(payload, "id", path, line_number),
        src=_required_string(payload, "src", path, line_number),
        section=_required_string(payload, "section", path, line_number),
        text=_required_string(payload, "text", path, line_number),
        kind=cast(ClaimKind, kind),
        briefs=briefs,
        hash=_required_string(payload, "hash", path, line_number),
    )


def _required_string(payload: Mapping[str, object], key: str, path: Path, line_number: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ClaimError(f"{path}:{line_number}: {key!r} must be a non-empty string")
    return value


def _briefs(payload: Mapping[str, object], path: Path, line_number: int) -> tuple[str, ...]:
    value = payload.get("briefs")
    if not isinstance(value, list) or not all(isinstance(brief, str) and brief for brief in value):
        raise ClaimError(f"{path}:{line_number}: 'briefs' must be a list of non-empty strings")
    return tuple(cast(list[str], value))


def _source_range(src: str, root: Path) -> tuple[Path, int, int]:
    match = SOURCE_PATTERN.fullmatch(src)
    if match is None:
        raise ClaimError(f"invalid source range {src!r}")
    first = int(match.group("first"))
    last = int(match.group("last"))
    if first > last:
        raise ClaimError(f"invalid descending source range {src!r}")
    root = root.resolve()
    path = (root / match.group("filename")).resolve()
    if not path.is_relative_to(root):
        raise ClaimError(f"source path escapes the tool directory: {src!r}")
    if not path.is_file():
        raise ClaimError(f"source file does not exist: {src!r}")
    return path, first, last
