import logging
import time

import pytest
import structlog
from _pytest.logging import LogCaptureFixture

from app.core.logging import log_timing, setup_logging
from app.core.logging_utils import sanitize_payload


@pytest.fixture(autouse=True)
def configure_logging() -> None:
    """Ensure logging is configured for tests."""
    setup_logging(level=logging.INFO)


def test_sanitize_payload() -> None:
    """Verify that sensitive keys are redacted from payloads."""
    dirty_payload = {
        "messages": [
            {
                "content": "Hello",
                "additional_kwargs": {
                    "__gemini_function_call_thought_signatures__": "SECRET_SIGNATURE",
                    "other": "value",
                },
            },
            {"extras": {"signature": "SECRET_SIGNATURE_2", "public_info": "ok"}},
        ],
        "top_level_signature": "signature",
        "nested_dict": {"deep_list": [{"signature": "hidden"}, {"safe": "safe"}]},
    }

    sanitized = sanitize_payload(dirty_payload)

    # Assertions
    assert "signature" not in sanitized["messages"][1]["extras"]
    assert "public_info" in sanitized["messages"][1]["extras"]
    assert "__gemini_function_call_thought_signatures__" not in sanitized["messages"][0]["additional_kwargs"]
    assert "other" in sanitized["messages"][0]["additional_kwargs"]

    # Check deeper nesting
    assert "signature" not in sanitized["nested_dict"]["deep_list"][0]


def test_log_timing_structlog(caplog: LogCaptureFixture) -> None:
    """Verify log_timing works with structlog loggers."""
    logger = structlog.get_logger("test_structlog")

    with caplog.at_level(logging.INFO):
        with log_timing("structlog_op", logger):
            time.sleep(0.001)

    assert len(caplog.records) == 1
    assert "structlog_op completed" in caplog.records[0].message
    # structlog output might be formatted differently in caplog depending on processor setup,
    # but the message should be there.


def test_log_timing_stdlib(caplog: LogCaptureFixture) -> None:
    """Verify log_timing works with standard library loggers."""
    logger = logging.getLogger("test_stdlib")

    with caplog.at_level(logging.INFO):
        with log_timing("stdlib_op", logger):
            time.sleep(0.001)

    assert len(caplog.records) == 1
    assert "stdlib_op completed" in caplog.records[0].message
    assert getattr(caplog.records[0], "duration_ms", None) is not None


def test_logging_interception(caplog: LogCaptureFixture) -> None:
    """Verify standard library logs are intercepted and formatted."""
    stdlib_logger = logging.getLogger("test_interception")

    with caplog.at_level(logging.INFO):
        stdlib_logger.info("Stdlib info message", extra={"foo": "bar"})

    assert len(caplog.records) == 1
    assert "Stdlib info message" in caplog.records[0].message
    assert getattr(caplog.records[0], "foo", None) == "bar"


def test_debug_log_level(caplog: LogCaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify debug logs are captured when LOG_LEVEL is DEBUG."""
    # We need to re-setup logging to pick up the new level
    from app.core import config

    monkeypatch.setattr(config.settings, "LOG_LEVEL", "DEBUG")
    setup_logging(level="DEBUG")

    logger = structlog.get_logger("test_debug")

    with caplog.at_level(logging.DEBUG):
        logger.debug("Test Debug Log", status="visible")

    assert len(caplog.records) == 1
    assert len(caplog.records) == 1

    # structlog might pass a dict or a formatted string as the message
    msg = caplog.records[0].msg
    if isinstance(msg, dict):
        assert msg["event"] == "Test Debug Log"
        assert msg["status"] == "visible"
    else:
        # Fallback to string checks if formatted
        log_str = caplog.records[0].message
        assert "Test Debug Log" in log_str
        assert "visible" in log_str
