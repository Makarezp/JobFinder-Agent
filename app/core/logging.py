"""Structured logging with structlog and request correlation."""

import logging
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager

# ── ContextVar for request correlation ──────────────────────────────
from contextvars import ContextVar
from typing import Any

import structlog
from langsmith.run_helpers import get_current_run_tree
from structlog.types import EventDict, Processor, WrappedLogger

from app.core.config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


# ── Timing helper ───────────────────────────────────────────────────
@contextmanager
def log_timing(operation: str, logger: Any | None = None) -> Generator[None, None, None]:
    """Context manager that logs the duration of an operation in ms."""
    # Support both structlog loggers and standard library loggers
    _logger = logger or structlog.get_logger()
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000)
        if isinstance(_logger, logging.Logger):
            _logger.info(f"{operation} completed", extra={"duration_ms": duration_ms})
        else:
            _logger.info(f"{operation} completed", duration_ms=duration_ms)


# ── LangSmith trace ID processor ────────────────────────────────────
def add_langsmith_trace_id(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Structlog processor that injects the active LangSmith trace_id if present."""
    run_tree = get_current_run_tree()
    if run_tree is not None:
        event_dict["trace_id"] = str(run_tree.id)
    return event_dict


# ── Bootstrap ───────────────────────────────────────────────────────
def setup_logging(*, level: int | str | None = None) -> None:
    """Configure structlog to intercept standard library logging."""
    if level is None:
        level = settings.LOG_LEVEL.upper()

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        add_langsmith_trace_id,
    ]

    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    if settings.APP_ENV == "development":
        renderer: Processor = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # ── Console handler (excludes state snapshots) ───────────────────
    class _ExcludeSnapshotFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return record.name != "app.core.snapshot_logging_utils"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(_ExcludeSnapshotFilter())

    root_logger = logging.getLogger()
    root_logger.handlers = [h for h in root_logger.handlers if not (isinstance(h, logging.StreamHandler) and h.stream is sys.stdout)]
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # ── State snapshot file handler ──────────────────────────────────
    # Clear the file on every startup, then append-only during the session.
    settings.STATE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings.STATE_LOG_PATH.write_text("")

    file_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    file_handler = logging.FileHandler(settings.STATE_LOG_PATH, mode="a", encoding="utf-8")
    file_handler.setFormatter(file_formatter)

    state_logger = logging.getLogger("app.core.snapshot_logging_utils")
    state_logger.handlers.clear()
    state_logger.addHandler(file_handler)

    # ── Telemetry JSONL file handler ─────────────────────────────────
    settings.TELEMETRY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    telemetry_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )
    telemetry_handler = logging.FileHandler(settings.TELEMETRY_LOG_PATH, mode="a", encoding="utf-8")
    telemetry_handler.setFormatter(telemetry_formatter)
    logging.getLogger().addHandler(telemetry_handler)

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = True
