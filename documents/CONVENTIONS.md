# CONVENTIONS.md - The Rules

## 1. Coding Standards
- **Strict Typing**: All code must pass `mypy --strict`. No `Any` unless absolutely unavoidable. All functions **MUST** have return type annotations, including `-> None`.
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
- **Coverage**: Aim for >80% coverage. Run `pytest --cov=app` to verify.

## 4. Logging
- **Library**: Use `structlog`: `logger = structlog.get_logger(__name__)`.
- **Mandatory Tracing**:
    - Every **Tool** execution and **Graph Node** run **MUST** log its start and completion.
    - **Start**: Log inputs/arguments (redacted if verbose).
    - **End**: Log outputs/results (truncated to 500 chars if large).
- **Timing**: Wrap significant operations (external API calls, DB ops) with `with log_timing("operation_name", logger):`.
- **Request ID**: Automatically injected. No manual handling needed.
- **Structured Data**: Pass context as keyword arguments. e.g. `logger.info("event", user_id=123)`.
