"""The genericity contract, encoded as a test rather than as an intention.

This tool is meant to be lifted into its own repository unchanged. Vocabulary
borrowed from whatever project it happens to be developed in is coupling that
costs nothing today and is a painful diff later, so it is banned outright in the
files that ship as the product.

Test docstrings are deliberately *not* covered. A note saying which defect a
fixture was written to catch is provenance -- deleting it loses the reason the
fixture looks the way it does. What is banned everywhere, including here, is the
name of the host repository, which is the only real coupling.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TOOL_DIR = Path(__file__).resolve().parents[1]

# The product: what would be copied into a standalone repository.
SHIPPED = ("agentctl.py", "SKILL.md", "WORKER.md", "examples/reviewer-role.md")

BANNED = ("ticket", "sprint", "cvviewer")
HOST_REPO = "cvviewer"


def _hits(text: str, word: str) -> list[str]:
    """Whole-word, case-insensitive matches, with a little surrounding context."""
    return [match.group(0) for match in re.finditer(rf".{{0,40}}\b{word}\b.{{0,40}}", text, re.IGNORECASE)]


@pytest.mark.parametrize("filename", SHIPPED)
def test_shipped_files_exist(filename: str) -> None:
    """A missing file would make every grep below pass vacuously."""
    assert (TOOL_DIR / filename).is_file()


@pytest.mark.parametrize("filename", SHIPPED)
@pytest.mark.parametrize("word", BANNED)
def test_shipped_files_carry_no_host_project_vocabulary(filename: str, word: str) -> None:
    text = (TOOL_DIR / filename).read_text(encoding="utf-8")
    assert _hits(text, word) == []


@pytest.mark.parametrize("word", BANNED)
def test_the_grep_can_actually_fail(word: str) -> None:
    """Positive control.

    Every assertion above passes trivially if the matcher is broken. This one
    fails if the matcher stops matching, which is the failure mode that would
    silently retire the whole contract.
    """
    assert _hits(f"a stray {word} reference", word) != []


def test_word_boundaries_do_not_produce_false_positives() -> None:
    """`ticket` must not fire on `ticketing`-style substrings of unrelated words."""
    assert _hits("the run id is cvv and the state is idle", HOST_REPO) == []


def test_the_host_repository_name_appears_nowhere_in_the_tool() -> None:
    """Stricter than the shipped-file rule, and applied to tests too.

    Sprint vocabulary in a test docstring is provenance. The host repository's
    name is never anything but coupling.
    """
    this_file = Path(__file__).resolve()
    offenders: list[str] = []
    for path in sorted(TOOL_DIR.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".md"} or "__pycache__" in path.parts:
            continue
        if path == this_file:
            continue  # the enforcer has to name what it bans
        if _hits(path.read_text(encoding="utf-8"), HOST_REPO):
            offenders.append(str(path.relative_to(TOOL_DIR)))
    assert offenders == []


def test_the_tool_is_a_single_self_contained_module() -> None:
    """No package, no relative imports: one file plus its documents."""
    assert not (TOOL_DIR / "__init__.py").exists()
    source = (TOOL_DIR / "agentctl.py").read_text(encoding="utf-8")
    assert "\nfrom ." not in source
    assert "\nimport ." not in source
