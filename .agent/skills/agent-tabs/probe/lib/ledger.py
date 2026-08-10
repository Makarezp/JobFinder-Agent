"""Append-only rate ledger for real-worker conformance runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LEDGER_PATH = Path(__file__).resolve().parents[1] / "ledger.jsonl"


def append(entry: dict[str, Any], path: Path = LEDGER_PATH) -> None:
    """Append one durable conformance result."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")
        handle.flush()
