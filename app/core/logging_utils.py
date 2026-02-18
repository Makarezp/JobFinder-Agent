from typing import Any

import structlog

logger = structlog.get_logger(__name__)

SENSITIVE_KEYS = {
    "signature",
    "__gemini_function_call_thought_signatures__",
}


def sanitize_payload(data: Any) -> Any:
    """
    Recursively sanitizes the payload by removing sensitive keys.
    Also converts LangChain messages to dicts for cleaner logging.
    """
    if isinstance(data, dict):
        return {k: sanitize_payload(v) for k, v in data.items() if k not in SENSITIVE_KEYS}
    elif isinstance(data, list):
        return [sanitize_payload(item) for item in data]
    elif hasattr(data, "model_dump"):
        # Pydantic v2 / LangChain objects
        return sanitize_payload(data.model_dump())
    elif hasattr(data, "dict"):
        # Pydantic v1
        return sanitize_payload(data.dict())
    else:
        return data


def log_state_snapshot(logger: Any, state: dict[str, Any], truncate_keys: list[str] | None = None) -> None:
    """
    Logs a snapshot of the current state, truncating specified keys to avoid noise.
    """
    snapshot = state.copy()
    truncate_keys = truncate_keys or []

    for key in truncate_keys:
        if key in snapshot and snapshot[key]:
            val_len = len(str(snapshot[key]))
            snapshot[key] = f"<truncated string of length {val_len}>"

    sanitized_snapshot = sanitize_payload(snapshot)
    logger.info("Graph State Update", extra={"state_snapshot": sanitized_snapshot})
