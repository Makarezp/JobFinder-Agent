"""Sentinel-prefixed tokens for mechanically grading real-worker replies."""

from __future__ import annotations

import random
import re

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TOKEN_PATTERN = re.compile(r"\bTOK-[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{4}\b")
_issued: set[str] = set()


def mint() -> str:
    """Mint a unique, terminal-readable token for the current process."""
    while True:
        token = f"TOK-{''.join(random.choices(ALPHABET, k=4))}"
        if token not in _issued:
            _issued.add(token)
            return token


def tokens_in(text: str) -> set[str]:
    """Return only valid sentinel-prefixed probe tokens from text."""
    return set(TOKEN_PATTERN.findall(text))
