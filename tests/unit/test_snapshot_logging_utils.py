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


def test_log_node_completed_node_name_in_event(caplog: LogCaptureFixture) -> None:
    """The node name is included in the log event string."""
    response = AIMessage(content="Done.")
    response.usage_metadata = None  # type: ignore[assignment]

    with caplog.at_level(logging.INFO, logger="app.core.node_logging_utils"):
        log_node_completed("fetch_profile", response)

    msg = _msg(caplog.records[0])
    assert "fetch_profile" in msg.get("event", "")
