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


def _compute_state_diff(old_state: dict[str, Any], new_state: dict[str, Any]) -> dict[str, Any]:
    """
    Computes a shallow/semi-deep delta between two state dicts.
    - New keys: included in full.
    - Changed scalar values: included.
    - Lists: only newly appended items (new[len(old):]) are included.
    - Unchanged keys: omitted.
    """
    diff: dict[str, Any] = {}
    for key, new_val in new_state.items():
        old_val = old_state.get(key)
        if key not in old_state:
            diff[key] = new_val
        elif isinstance(new_val, list) and isinstance(old_val, list):
            appended = new_val[len(old_val) :]
            if appended:
                diff[key] = appended
        elif new_val != old_val:
            diff[key] = new_val
    return diff


def log_state_snapshot(
    state: dict[str, Any],
    truncate_keys: list[str] | None = None,
    max_string_length: int = 500,
    previous_state: dict[str, Any] | None = None,
) -> None:
    """
    Logs a snapshot of the current state to the dedicated state log file.
    If previous_state is provided, only the diff is logged. Empty diffs are skipped.
    """
    truncate_keys = truncate_keys or []

    if previous_state is not None:
        diff = _compute_state_diff(previous_state, state)
        if not diff:
            return
        for key in truncate_keys:
            if key in diff and diff[key]:
                val_len = len(str(diff[key]))
                diff[key] = f"<truncated string of length {val_len}>"
        sanitized = sanitize_payload(diff, max_string_length=max_string_length)
        logger.info("Graph State Mutated", extra={"state_diff": sanitized})
    else:
        snapshot = state.copy()
        for key in truncate_keys:
            if key in snapshot and snapshot[key]:
                val_len = len(str(snapshot[key]))
                snapshot[key] = f"<truncated string of length {val_len}>"
        sanitized_snapshot = sanitize_payload(snapshot, max_string_length=max_string_length)
        logger.info("Graph State Update", extra={"state_snapshot": sanitized_snapshot})
