"""Structured probe assertions consumed by later conformance oracles."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from agentctl import Event, EventType


@dataclass
class ProbeFailure(Exception):
    """A failed protocol expectation with machine-readable evidence."""

    brief_id: str
    expected: object
    observed: object

    def __post_init__(self) -> None:
        Exception.__init__(self, f"{self.brief_id}: expected {self.expected!r}, observed {self.observed!r}")

    def to_dict(self) -> dict[str, object]:
        """Serialize the contract consumed by the T7 oracle."""
        return asdict(self)


class HarnessError(RuntimeError):
    """The probe cannot establish a trustworthy observation."""


def assert_tokens(brief_id: str, echoed: set[str], expected: set[str], minted: set[str]) -> None:
    """Require all expected tokens and forbid only foreign probe tokens."""
    missing = expected - echoed
    foreign = (echoed & minted) - expected
    if missing or foreign:
        raise ProbeFailure(brief_id, {"missing": missing, "foreign": set()}, {"missing": set(), "foreign": foreign})


def assert_exit(brief_id: str, events: list[Event], agent: str) -> None:
    """Require an agent's final lifecycle event to be ``exit``."""
    matching = [event for event in events if event.agent == agent]
    observed = matching[-1].type.value if matching else None
    if not matching or matching[-1].type is not EventType.EXIT:
        raise ProbeFailure(brief_id, EventType.EXIT.value, observed)


def assert_event_absent(brief_id: str, events: list[Event], event_type: EventType, *, agent: str | None = None) -> None:
    """Require no matching event in a probe result."""
    observed = [event.to_line() for event in events if event.type is event_type and (agent is None or event.agent == agent)]
    if observed:
        raise ProbeFailure(brief_id, f"no {event_type.value} events", observed)


def assert_event_count(
    brief_id: str,
    events: list[Event],
    event_type: EventType,
    count: int,
    *,
    agent: str | None = None,
) -> None:
    """Require exactly ``count`` matching events."""
    observed = sum(event.type is event_type and (agent is None or event.agent == agent) for event in events)
    if observed != count:
        raise ProbeFailure(brief_id, count, observed)


def assert_inbox_contains(brief_id: str, files: list[str], expected: str) -> None:
    """Require an expected payload fragment in directly read inbox content."""
    if not any(expected in content for content in files):
        raise ProbeFailure(brief_id, expected, files)


def assert_screen_lacks(brief_id: str, capture: str, forbidden: str, *, landmark: str) -> None:
    """Require a real, positively identified capture to omit forbidden text."""
    if not capture.strip() or landmark not in capture:
        raise HarnessError("screen capture lacks the required nonempty landmark")
    if forbidden in capture:
        raise ProbeFailure(brief_id, f"screen without {forbidden!r}", capture)


def assert_no_windows(brief_id: str, windows: list[str]) -> None:
    """Require the tmux session to contain no residual worker windows."""
    if windows:
        raise ProbeFailure(brief_id, [], windows)
