"""Validated append-only journal and deterministic coverage digest."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Literal, cast

from probe.lib.claims import Claim, ClaimError, hash_of, stale
from probe.lib.claims import load as load_claims

TOOL_DIR = Path(__file__).resolve().parents[2]
JOURNAL_PATH = TOOL_DIR / "probe" / "journal.jsonl"
LEDGER_PATH = TOOL_DIR / "probe" / "ledger.jsonl"
COVERAGE_PATH = TOOL_DIR / "probe" / "COVERAGE.md"

EntryKind = Literal["trial", "explore", "verdict", "invalidate"]
CellStatus = Literal["fresh", "stale", "dead-end", "unvisited"]
Cell = tuple[str, str, str, str, str]

ENTRY_KINDS: frozenset[str] = frozenset({"trial", "explore", "verdict", "invalidate"})
OUTCOMES: frozenset[str] = frozenset({"finding", "no-finding", "dead-end", "inconclusive"})
VERDICTS: frozenset[str] = frozenset({"code", "doc-gap", "doc-rewrite", "harness", "duplicate"})
FAULTS: frozenset[str] = frozenset(
    {
        "none",
        "lost-doorbell",
        "copy-mode",
        "busy",
        "dirty-composer",
        "hard-kill",
        "spacey-path",
        "corrupt-settings",
        "human-interrupt",
        "inbox-discipline",
        "watermark",
    }
)
COUNTERPARTIES: frozenset[str] = frozenset({"real-haiku", "real-sonnet", "puppet", "orchestrator-loop"})
PROVIDERS: frozenset[str] = frozenset({"claude", "codex"})
CONCURRENCIES: frozenset[str] = frozenset({"1", "n-workers", "worktree"})
ABSOLUTE_PATH = re.compile(r"/(?:Users|tmp|private)(?:/[^\s`)]*)?")


class JournalError(ValueError):
    """A journal record or target cell violates the probe contract."""


def append(
    entry: Mapping[str, object],
    path: Path = JOURNAL_PATH,
    *,
    claims: Iterable[Claim] | None = None,
) -> dict[str, object]:
    """Validate and durably append one journal record, returning its canonical form."""
    canonical = _canonical_entry(entry, claims=claims)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(canonical, separators=(",", ":"), ensure_ascii=False) + "\n")
        handle.flush()
    return canonical


def load(path: Path = JOURNAL_PATH) -> list[dict[str, object]]:
    """Load existing append-only records, preserving legacy entries for the digest."""
    return _load_jsonl(path, label="journal")


def load_ledger(path: Path = LEDGER_PATH) -> list[dict[str, object]]:
    """Load rate-ledger records used by the derived coverage digest."""
    return _load_jsonl(path, label="ledger")


def cell_status(
    cell: Sequence[object],
    entries: Iterable[Mapping[str, object]] | None = None,
    *,
    claims: Iterable[Claim] | None = None,
) -> CellStatus:
    """Classify a target cell without mutating its append-only evidence."""
    target = normalize_cell(cell)
    matching = [entry for entry in (load() if entries is None else entries) if _entry_cell(entry) == target]
    if not matching:
        return "unvisited"
    latest = matching[-1]
    try:
        current_hash = _claim_hash(target[0], claims)
    except JournalError:
        return "stale"
    if latest.get("claim_hash") != current_hash:
        return "stale"
    if latest.get("outcome") == "dead-end":
        return "dead-end"
    return "fresh"


def regenerate_coverage(
    entries: Iterable[Mapping[str, object]] | None = None,
    *,
    claims: Iterable[Claim] | None = None,
    ledger: Iterable[Mapping[str, object]] | None = None,
) -> str:
    """Render the byte-stable digest from explicit journal, claim, and ledger inputs."""
    journal_entries = list(load() if entries is None else entries)
    registry = list(load_claims() if claims is None else claims)
    ledger_entries = list(load_ledger() if ledger is None else ledger)
    stale_ids = {claim.id for claim in stale(registry)}
    covered = [claim.id for claim in registry if claim.briefs and claim.id not in stale_ids]
    uncovered = [claim.id for claim in registry if not claim.briefs]
    stale_claims = [claim.id for claim in registry if claim.id in stale_ids]
    lines = [
        "<!-- GENERATED FILE — DO NOT EDIT. Regenerate with `probe.py coverage --write`. -->",
        "# Probe Coverage Digest",
        "",
        "## Claims",
        f"- Covered ({len(covered)}): {_ids(covered)}",
        f"- Uncovered ({len(uncovered)}): {_ids(uncovered)}",
        f"- Stale ({len(stale_claims)}): {_ids(stale_claims)}",
        "",
        "## Rate trends",
    ]
    lines.extend(_rate_trends(ledger_entries) or ["- No recorded brief rates."])
    lines.extend(["", "## Dead ends"])
    lines.extend(_dead_ends(journal_entries) or ["- None."])
    lines.extend(["", "## Ranked unvisited cells"])
    lines.extend(_ranked_unvisited(registry, journal_entries) or ["- None."])
    return "\n".join(lines) + "\n"


def write_coverage(
    path: Path = COVERAGE_PATH,
    *,
    entries: Iterable[Mapping[str, object]] | None = None,
    claims: Iterable[Claim] | None = None,
    ledger: Iterable[Mapping[str, object]] | None = None,
) -> str:
    """Regenerate the derived digest and write it as a complete replacement."""
    digest = regenerate_coverage(entries, claims=claims, ledger=ledger)
    path.write_text(digest, encoding="utf-8")
    return digest


def normalize_cell(cell: Sequence[object]) -> Cell:
    """Validate one coordinate-system cell and normalize single-worker spelling."""
    if len(cell) != 5:
        raise JournalError("cell must contain claim, fault, counterparty, provider, and concurrency")
    claim, fault, counterparty, provider, concurrency = cell
    if not isinstance(claim, str) or not claim:
        raise JournalError("cell claim must be a non-empty string")
    if not isinstance(fault, str) or fault not in FAULTS:
        raise JournalError(f"unknown cell fault {fault!r}")
    if not isinstance(counterparty, str) or counterparty not in COUNTERPARTIES:
        raise JournalError(f"unknown cell counterparty {counterparty!r}")
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise JournalError(f"unknown cell provider {provider!r}")
    if isinstance(concurrency, int) and not isinstance(concurrency, bool):
        concurrency = str(concurrency)
    if not isinstance(concurrency, str) or concurrency not in CONCURRENCIES:
        raise JournalError(f"unknown cell concurrency {concurrency!r}")
    return claim, fault, counterparty, provider, concurrency


def _canonical_entry(entry: Mapping[str, object], *, claims: Iterable[Claim] | None) -> dict[str, object]:
    canonical = dict(entry)
    kind = canonical.get("kind")
    if kind not in ENTRY_KINDS:
        raise JournalError(f"invalid journal kind {kind!r}")
    if not isinstance(canonical.get("entry"), str) or not canonical["entry"]:
        raise JournalError("journal entry requires a non-empty entry id")
    raw_cell = canonical.get("cell")
    if not isinstance(raw_cell, list):
        raise JournalError("journal entry requires a cell array")
    cell = normalize_cell(raw_cell)
    canonical["cell"] = list(cell)
    canonical["claim_hash"] = _claim_hash(cell[0], claims)
    if kind == "explore":
        _validate_explore(canonical)
    elif kind == "trial":
        _validate_trial(canonical)
    elif kind == "verdict":
        _validate_verdict(canonical)
    else:
        stale_briefs = canonical.get("stale_briefs")
        if not isinstance(stale_briefs, list) or not all(isinstance(brief, str) and brief for brief in stale_briefs):
            raise JournalError("invalidate entry requires non-empty stale_briefs strings")
    return canonical


def _validate_explore(entry: Mapping[str, object]) -> None:
    tried = entry.get("tried")
    if not isinstance(tried, list) or not tried or not all(isinstance(item, str) and item for item in tried):
        raise JournalError("explore entry requires non-empty tried strings")
    _required_string(entry, "ruled_out")
    outcome = entry.get("outcome")
    if outcome not in OUTCOMES:
        raise JournalError(f"invalid explore outcome {outcome!r}")
    proof = entry.get("fault_proof")
    if not isinstance(proof, str) or not proof:
        if outcome == "dead-end":
            raise JournalError("dead-end explore entry requires fault_proof")
        raise JournalError("explore entry requires fault_proof")


def _validate_verdict(entry: Mapping[str, object]) -> None:
    verdict = _required_string(entry, "verdict")
    if verdict not in VERDICTS:
        raise JournalError(f"invalid verdict {verdict!r}")
    claim = entry.get("claim")
    if verdict in {"code", "doc-rewrite", "duplicate"}:
        if not isinstance(claim, str) or not claim:
            raise JournalError(f"{verdict} verdict requires a claim citation")
    elif verdict == "doc-gap":
        if claim is not None:
            raise JournalError("doc-gap verdict must use claim null")
    elif claim is not None and (not isinstance(claim, str) or not claim):
        raise JournalError("verdict claim must be a non-empty string or null")
    if isinstance(claim, str):
        _claim_hash(claim, None)
    for key in ("trial_entry", "brief", "commit", "summary", "evidence"):
        _required_string(entry, key)
    for key in ("rate", "control_rate"):
        value = entry.get(key)
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise JournalError(f"verdict entry requires numeric {key}")
    artifacts = entry.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts or not all(isinstance(artifact, str) and artifact for artifact in artifacts):
        raise JournalError("verdict entry requires preserved artifact paths")


def _validate_trial(entry: Mapping[str, object]) -> None:
    for key in ("ts", "brief", "commit", "model", "outcome"):
        _required_string(entry, key)
    if entry["outcome"] not in OUTCOMES - {"dead-end", "inconclusive"}:
        raise JournalError(f"invalid trial outcome {entry['outcome']!r}")
    for key in ("trials", "passed"):
        value = entry.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise JournalError(f"trial entry requires non-negative integer {key}")
    for key in ("rate", "control_rate", "wall_seconds"):
        value = entry.get(key)
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise JournalError(f"trial entry requires numeric {key}")
    artifacts = entry.get("artifacts")
    if not isinstance(artifacts, list) or not all(isinstance(artifact, str) for artifact in artifacts):
        raise JournalError("trial entry requires artifact strings")


def _required_string(entry: Mapping[str, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value:
        raise JournalError(f"journal entry requires non-empty {key}")
    return value


def _claim_hash(claim_id: str, claims: Iterable[Claim] | None) -> str:
    registry = {claim.id: claim for claim in (load_claims() if claims is None else claims)}
    try:
        return hash_of(registry[claim_id])
    except KeyError as error:
        raise JournalError(f"unknown cell claim {claim_id!r}") from error
    except ClaimError as error:
        raise JournalError(f"unresolvable cell claim {claim_id!r}") from error


def _load_jsonl(path: Path, *, label: str) -> list[dict[str, object]]:
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise JournalError(f"{label} {path}:{line_number}: invalid JSON") from error
        if not isinstance(raw, dict):
            raise JournalError(f"{label} {path}:{line_number}: entry must be an object")
        entries.append(cast(dict[str, object], raw))
    return entries


def _entry_cell(entry: Mapping[str, object]) -> Cell | None:
    cell = entry.get("cell")
    if not isinstance(cell, list):
        return None
    try:
        return normalize_cell(cell)
    except JournalError:
        return None


def _ids(values: Iterable[str]) -> str:
    values = list(values)
    return ", ".join(values) if values else "None"


def _rate_trends(entries: Iterable[Mapping[str, object]]) -> list[str]:
    by_brief: dict[str, list[float]] = {}
    for entry in entries:
        brief = entry.get("brief")
        rate = entry.get("rate")
        if isinstance(brief, str) and isinstance(rate, int | float) and not isinstance(rate, bool):
            by_brief.setdefault(brief, []).append(float(rate))
    lines: list[str] = []
    for brief in sorted(by_brief):
        rates = by_brief[brief]
        arrow = "→" if len(rates) == 1 else _arrow(rates[-2], rates[-1])
        lines.append(f"- {brief}: {' → '.join(f'{rate:.2f}' for rate in rates)} {arrow}")
    return lines


def _arrow(previous: float, current: float) -> str:
    if current > previous:
        return "↑"
    if current < previous:
        return "↓"
    return "→"


def _dead_ends(entries: Iterable[Mapping[str, object]]) -> list[str]:
    lines: list[str] = []
    for entry in entries:
        if entry.get("outcome") != "dead-end":
            continue
        entry_id = entry.get("entry")
        reason = entry.get("ruled_out")
        proof = entry.get("fault_proof")
        if isinstance(entry_id, str) and isinstance(reason, str) and isinstance(proof, str) and proof:
            lines.append(f"- {entry_id}: {_redact_paths(reason)}")
    return lines


def _ranked_unvisited(claims: Iterable[Claim], entries: Iterable[Mapping[str, object]]) -> list[str]:
    lines: list[str] = []
    for claim in sorted(claims, key=lambda item: (bool(item.briefs), item.id)):
        cell = (claim.id, _baseline_fault(claim), _counterparty(claim), "claude", "1")
        if cell_status(cell, entries, claims=claims) == "unvisited":
            lines.append(f"{len(lines) + 1}. {' / '.join(cell)}")
    return lines


def _baseline_fault(claim: Claim) -> str:
    return {
        "worker-behavior": "lost-doorbell",
        "orchestrator-behavior": "human-interrupt",
        "gate": "dirty-composer",
        "lifecycle": "hard-kill",
        "invariant": "none",
    }[claim.kind]


def _counterparty(claim: Claim) -> str:
    return "orchestrator-loop" if claim.kind == "orchestrator-behavior" else "real-haiku"


def _redact_paths(value: str) -> str:
    return ABSOLUTE_PATH.sub("<artifact>", value)
