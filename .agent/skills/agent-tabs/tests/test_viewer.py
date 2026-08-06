"""Viewer plugin tests.

`ItermTabViewer` is exercised entirely through an injected runner -- nothing
here shells out to `osascript`, since the machine running the suite may not
have iTerm at all. The quoting round-trip is the load-bearing test: it must be
built by actually running `shlex.split` over the intended command line, not by
hand-transcribing the expected argv, or a broken separator can slip past a
test that "looks right" (see agent-tabs-iteration-1-review.md, T8-1).
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable

import agentctl
import pytest


def _applescript_unescape(text: str) -> str:
    # Inverse of ItermTabViewer._applescript_escape: undo the quote-escape
    # first, then the backslash-escape, since escaping ran backslash-first.
    return text.replace('\\"', '"').replace("\\\\", "\\")


def _extract_command(script: str) -> str:
    marker = 'write text "'
    start = script.index(marker) + len(marker)
    end = script.index('"\n', start)
    return _applescript_unescape(script[start:end])


def _recorder(returncode: int = 0, stderr: str = "") -> tuple[list[str], Callable[[str], subprocess.CompletedProcess[str]]]:
    calls: list[str] = []

    def runner(script: str) -> subprocess.CompletedProcess[str]:
        calls.append(script)
        return subprocess.CompletedProcess(args=["osascript", "-"], returncode=returncode, stdout="", stderr=stderr)

    return calls, runner


def test_reveal_round_trips_a_hostile_run_id_through_both_escaping_layers() -> None:
    calls, runner = _recorder()
    viewer = agentctl.ItermTabViewer(runner=runner)

    run = 'My "Run"\\Two'
    viewer.reveal(run, "@3")

    assert len(calls) == 1
    command = _extract_command(calls[0])

    # Built and split here, not hand-transcribed: shlex.split resolves the
    # shell-escaped `\;` separator to a bare `;`, and treats the env-clearing
    # `TMUX=` prefix as its own word.
    intended = f"TMUX= tmux attach -t {shlex.quote('=' + run)} \\; select-window -t {shlex.quote('@3')}"
    expected = shlex.split(intended)

    assert shlex.split(command) == expected
    assert expected[0] == "TMUX="
    assert expected[expected.index("attach") + 2] == "=" + run
    assert ";" in expected

    # shlex.split alone cannot tell an escaped `\;` apart from a bare `;` --
    # both resolve to the same token, so the round-trip assertion above is
    # blind to this. A bare `;` in the *actual embedded shell command* is a
    # live bug, not a cosmetic one: the human's shell (not tmux) is what
    # reads this line first, and it treats an unescaped `;` as its own
    # command separator, splitting "tmux attach ..." and "select-window ..."
    # into two shell commands -- the second of which is not a program.
    # This was caught by a live spawn, not by the round-trip test above.
    assert "\\;" in command
    assert " ; " not in command
    assert "\\;" not in expected


def test_reveal_uses_the_exact_match_target_not_the_bare_run_id() -> None:
    calls, runner = _recorder()
    viewer = agentctl.ItermTabViewer(runner=runner)

    viewer.reveal("cvv", "@3")

    command = _extract_command(calls[0])
    argv = shlex.split(command)
    assert argv[argv.index("-t")] == "-t"
    assert argv[argv.index("attach") + 2] == "=cvv"
    assert "cvv" != argv[argv.index("attach") + 2]


def test_reveal_raises_viewer_error_on_nonzero_exit_carrying_stderr() -> None:
    _, runner = _recorder(returncode=1, stderr="iTerm got an error: boom")
    viewer = agentctl.ItermTabViewer(runner=runner)

    with pytest.raises(agentctl.ViewerError, match="boom"):
        viewer.reveal("cvv", "@3")


def test_null_viewer_is_a_no_op_for_any_input() -> None:
    agentctl.NullViewer().reveal("anything", "@99")
    agentctl.NullViewer().reveal("", "")


def test_get_viewer_resolves_by_name_and_environment() -> None:
    assert isinstance(agentctl.get_viewer("iterm-tab"), agentctl.ItermTabViewer)

    config = agentctl.Config.from_env({agentctl.ENV_VIEWER: "iterm-tab"})
    assert isinstance(agentctl.get_viewer(None, config), agentctl.ItermTabViewer)

    assert isinstance(agentctl.get_viewer(None, agentctl.Config.from_env({})), agentctl.NullViewer)
    assert isinstance(agentctl.get_viewer(), agentctl.Viewer)


def test_get_viewer_rejects_an_unknown_name() -> None:
    with pytest.raises(agentctl.ViewerError, match="unknown viewer"):
        agentctl.get_viewer("nonsense")


def test_both_viewers_satisfy_the_protocol() -> None:
    assert isinstance(agentctl.NullViewer(), agentctl.Viewer)
    assert isinstance(agentctl.ItermTabViewer(), agentctl.Viewer)
