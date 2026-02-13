"""Structured logging with request correlation and timing."""

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from pythonjsonlogger.json import JsonFormatter

# ── ContextVar for request correlation ──────────────────────────────
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Injects the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()  # type: ignore[attr-defined]
        return True


# ── Timing helper ───────────────────────────────────────────────────
@contextmanager
def log_timing(operation: str, logger: logging.Logger | None = None) -> Generator[None, None, None]:
    """Context manager that logs the duration of an operation in ms."""
    _logger = logger or logging.getLogger(__name__)
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000)
        _logger.info("%s completed", operation, extra={"duration_ms": duration_ms})


# ── Bootstrap ───────────────────────────────────────────────────────
def setup_logging(*, level: int = logging.INFO) -> None:
    """Configure structured JSON logging with request-id correlation."""
    handler = logging.StreamHandler()

    formatter = JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(request_id)s %(message)s",
        rename_fields={"asctime": "timestamp", "name": "logger", "levelname": "level"},
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)
    root.addFilter(RequestIdFilter())
