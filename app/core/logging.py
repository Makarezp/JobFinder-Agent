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
from structlog.types import EventDict, Processor

from app.core.config import settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def add_request_id_from_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add request_id to the event dict if present in context."""
    return event_dict


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

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # ── State snapshot file handler ──────────────────────────────────
    # Clear the file on every startup, then attach a JSON file handler
    # exclusively to the snapshot_logging_utils logger so that
    # "Graph State Update" events go to file only (not console).
    settings.STATE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    settings.STATE_LOG_PATH.open("w").close()

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
    state_logger.addHandler(file_handler)
    state_logger.propagate = False

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = True
