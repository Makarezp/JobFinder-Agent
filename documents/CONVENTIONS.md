# CONVENTIONS.md - The Rules

## 1. Coding Standards
- **Strict Typing**: All code must pass `mypy --strict`. No `Any` unless absolutely unavoidable.
- **Pydantic**: Use Pydantic models for all data exchange, configuration, and tool arguments.
- **Input Sanitization**: Use `Annotated[T, BeforeValidator(ensure_string)]` for flexible LLM inputs (handling list vs string ambiguity).

## 2. Error Handling (CRITICAL)
- **Tools**:
    - **MUST NOT** raise exceptions for anticipated runtime errors (e.g., HTTP 404, Parse Error).
    - **MUST** log the error using `logger.error`.
    - **MUST** return a descriptive error string (e.g., "Error: Failed to scrape URL...").
    - *Reason*: Raising exceptions crashes the Agent's graph execution. Returning a string allows the LLM to read the error and try a different approach.

## 3. Testing
- **Mocking**: Unit tests (`tests/unit`) MUST mock external services (LLM, Adzuna API, Crawl4AI).
- **Async**: Use `@pytest.mark.asyncio` for async test functions.
- **Fixtures**: Use `conftest.py` for shared fixtures (if available).

## 4. Logging
- Use standard `logging` library: `logger = logging.getLogger(__name__)`.
- **Structured JSON**: All logs emit JSON via `python-json-logger`. Setup lives in `app/core/logging.py`.
- **Request correlation**: Every log line includes `request_id` (injected via `RequestIdFilter` from a `ContextVar`). No manual passing needed.
- **Timing**: Wrap slow operations with `log_timing("operation_name", logger)` context manager.
- **Extra fields**: Use `extra={}` for structured data, but **never** use Python LogRecord reserved names (`filename`, `funcName`, `module`, `name`, `msg`). Prefix with context instead (e.g., `cv_filename`).
