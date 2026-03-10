"""
Unit tests for snapshot_logging_utils:
- log_node_completed emits correct log fields
- log_node_completed handles usage_metadata=None safely
"""

import logging
from typing import Any

import pytest
from _pytest.logging import LogCaptureFixture
from langchain_core.messages import AIMessage

from app.core.logging import setup_logging
from app.core.node_logging_utils import log_node_completed
from app.core.snapshot_logging_utils import _compute_state_diff, log_state_snapshot


@pytest.fixture(autouse=True)
def configure_logging() -> None:
    """Ensure logging is configured for tests."""
    setup_logging(level=logging.INFO)


def _msg(record: Any) -> dict[str, Any]:
    """Extract the structlog event dict from a LogRecord."""
    msg = record.msg
    return msg if isinstance(msg, dict) else {}


def test_log_node_completed_emits_token_fields(caplog: LogCaptureFixture) -> None:
    """Token usage fields appear in the log record when usage_metadata is populated."""
    response = AIMessage(content="Here are some jobs.")
    response.usage_metadata = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}

    with caplog.at_level(logging.INFO, logger="app.core.node_logging_utils"):
        log_node_completed("main_chatbot", response)

    assert len(caplog.records) == 1
    msg = _msg(caplog.records[0])
    assert msg.get("input_tokens") == 100
    assert msg.get("output_tokens") == 20
    assert msg.get("total_tokens") == 120


def test_log_node_completed_emits_response_preview(caplog: LogCaptureFixture) -> None:
    """response_preview is included and truncated to 100 chars."""
    response = AIMessage(content="x" * 200)
    response.usage_metadata = {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60}

    with caplog.at_level(logging.INFO, logger="app.core.node_logging_utils"):
        log_node_completed("onboarding_chatbot", response)

    msg = _msg(caplog.records[0])
    assert len(msg.get("response_preview", "")) == 100


def test_log_node_completed_none_usage_metadata_does_not_raise(caplog: LogCaptureFixture) -> None:
    """usage_metadata=None is handled safely — no AttributeError raised."""
    response = AIMessage(content="Hello.")
    response.usage_metadata = None  # type: ignore[assignment]

    with caplog.at_level(logging.INFO, logger="app.core.node_logging_utils"):
        log_node_completed("main_chatbot", response)

    assert len(caplog.records) == 1
    msg = _msg(caplog.records[0])
    assert msg.get("input_tokens") is None
    assert msg.get("output_tokens") is None
    assert msg.get("total_tokens") is None


# ---------------------------------------------------------------------------
# _compute_state_diff (Ticket 10.6)
# ---------------------------------------------------------------------------


def test_compute_state_diff_detects_new_key() -> None:
    """New keys in new_state appear in the diff."""
    old: dict[str, Any] = {"messages": []}
    new: dict[str, Any] = {"messages": [], "search_attempts": 1}
    diff = _compute_state_diff(old, new)
    assert diff == {"search_attempts": 1}


def test_compute_state_diff_detects_modified_value() -> None:
    """Changed scalar values appear in the diff."""
    old: dict[str, Any] = {"search_attempts": 0}
    new: dict[str, Any] = {"search_attempts": 2}
    diff = _compute_state_diff(old, new)
    assert diff == {"search_attempts": 2}


def test_compute_state_diff_lists_only_appended_items() -> None:
    """Only newly appended list items are included, not the full list."""
    old_msg: dict[str, Any] = {"role": "human", "content": "Hi"}
    new_msg: dict[str, Any] = {"role": "ai", "content": "Hello"}
    old: dict[str, Any] = {"messages": [old_msg]}
    new: dict[str, Any] = {"messages": [old_msg, new_msg]}
    diff = _compute_state_diff(old, new)
    assert diff == {"messages": [new_msg]}


def test_compute_state_diff_unchanged_state_returns_empty() -> None:
    """Identical states produce an empty diff."""
    state: dict[str, Any] = {"messages": [], "search_attempts": 0}
    diff = _compute_state_diff(state, state)
    assert diff == {}


def test_log_state_snapshot_skips_empty_diff(caplog: LogCaptureFixture) -> None:
    """log_state_snapshot emits no log when diff is empty."""
    state: dict[str, Any] = {"messages": [], "search_attempts": 0}
    with caplog.at_level(logging.INFO, logger="app.core.snapshot_logging_utils"):
        log_state_snapshot(state, previous_state=state)
    assert len(caplog.records) == 0


def test_log_state_snapshot_emits_diff_event(caplog: LogCaptureFixture) -> None:
    """log_state_snapshot emits Graph State Mutated when diff is non-empty."""
    old: dict[str, Any] = {"search_attempts": 0}
    new: dict[str, Any] = {"search_attempts": 1}
    with caplog.at_level(logging.INFO, logger="app.core.snapshot_logging_utils"):
        log_state_snapshot(new, previous_state=old)
    assert len(caplog.records) == 1
    msg = caplog.records[0].msg
    event = msg.get("event") if isinstance(msg, dict) else caplog.records[0].message
    assert "Graph State Mutated" in str(event)


def test_log_node_completed_node_name_in_event(caplog: LogCaptureFixture) -> None:
    """The node name is included in the log event string."""
    response = AIMessage(content="Done.")
    response.usage_metadata = None  # type: ignore[assignment]

    with caplog.at_level(logging.INFO, logger="app.core.node_logging_utils"):
        log_node_completed("fetch_profile", response)

    msg = _msg(caplog.records[0])
    assert "fetch_profile" in msg.get("event", "")
