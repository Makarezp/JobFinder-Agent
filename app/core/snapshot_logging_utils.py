from typing import Any

import structlog

logger = structlog.get_logger(__name__)

SENSITIVE_KEYS = {
    "signature",
    "__gemini_function_call_thought_signatures__",
}


def sanitize_payload(data: Any, max_string_length: int | None = None) -> Any:
    """
    Recursively sanitizes the payload by removing sensitive keys.
    Also converts LangChain messages to dicts for cleaner logging.
    Optionally truncates long strings.
    """
    if isinstance(data, dict):
        return {k: sanitize_payload(v, max_string_length) for k, v in data.items() if k not in SENSITIVE_KEYS}
    elif isinstance(data, list):
        return [sanitize_payload(item, max_string_length) for item in data]
    elif isinstance(data, str):
        if max_string_length and len(data) > max_string_length:
            return f"{data[:max_string_length]}... <truncated>"
        return data
    elif hasattr(data, "model_dump"):
        # Pydantic v2 / LangChain objects
        return sanitize_payload(data.model_dump(), max_string_length)
    elif hasattr(data, "dict"):
        # Pydantic v1
        return sanitize_payload(data.dict(), max_string_length)
    else:
        return data


def log_state_snapshot(state: dict[str, Any], truncate_keys: list[str] | None = None, max_string_length: int = 500) -> None:
    """
    Logs a snapshot of the current state to the dedicated state log file.
    Truncates specified keys to avoid noise.
    """
    snapshot = state.copy()
    truncate_keys = truncate_keys or []

    for key in truncate_keys:
        if key in snapshot and snapshot[key]:
            val_len = len(str(snapshot[key]))
            snapshot[key] = f"<truncated string of length {val_len}>"

    sanitized_snapshot = sanitize_payload(snapshot, max_string_length=max_string_length)
    logger.info("Graph State Update", extra={"state_snapshot": sanitized_snapshot})
