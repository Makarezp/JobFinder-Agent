"""Named, mechanical grades used by conformance briefs."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from probe.lib.assertions import assert_tokens
from probe.lib.nonce import tokens_in

Grade = Callable[[str, Iterable[str], set[str], set[str]], None]


def grade_tokens(brief_id: str, replies: Iterable[str], expected: set[str], minted: set[str]) -> None:
    """Grade nonce coverage while allowing all non-token worker prose."""
    echoed = set().union(*(tokens_in(reply) for reply in replies))
    assert_tokens(brief_id, echoed, expected, minted)


GRADES: dict[str, Grade] = {"tokens": grade_tokens}
