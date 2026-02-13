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
- Use standard `logging` library.
- Format: `logger = logging.getLogger(__name__)`.
