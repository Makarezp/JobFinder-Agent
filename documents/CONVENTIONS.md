# CONVENTIONS.md - The Rules

## 1. Coding Standards
- **Strict Typing**:
  - **Backend**: All code must pass `mypy --strict`. No `Any` unless unavoidable. All functions must have return types.
  - **Frontend**: All code must pass `tsc --noEmit`. Avoid `any` at all costs. Prefer interfaces over types for public APIs.
- **Pydantic / TS Interfaces**: Use Pydantic models for backend exchange and corresponding TypeScript interfaces in `frontend/src/core/types/`.
- **Input Sanitization**: Use `Annotated[T, BeforeValidator(ensure_string)]` for flexible LLM inputs (handling list vs string ambiguity).

## 2. Error Handling (CRITICAL)
- **Tools**:
    - **MUST NOT** raise exceptions for anticipated runtime errors (e.g., HTTP 404, Parse Error).
    - **MUST** log the error using `logger.error`.
    - **MUST** return a descriptive error string (e.g., "Error: Failed to scrape URL...").
    - *Reason*: Raising exceptions crashes the Agent's graph execution. Returning a string allows the LLM to read the error and try a different approach.

## 3. Testing
- **Backend (Pytest)**:
    - **Mocking**: Unit tests MUST mock external services (LLM, Adzuna API).
    - **Async**: Use `@pytest.mark.asyncio`.
    - **Coverage**: Aim for >80%. Run `pytest --cov=app`.
- **Frontend (Vitest)**:
    - **Isolated Logic**: All business logic in `src/core/` must have companion `.test.ts` files.
    - **Mocking**: Use `vi.mock()` for API modules and `vi.fn()` for global fetch.
    - **Store Tests**: Test Zustand stores via `getState()` specifically for state transitions.

## 4. Logging
- **Library**: Use `structlog`: `logger = structlog.get_logger(__name__)`.
- **Mandatory Tracing**:
    - Every **Tool** execution and **Graph Node** run **MUST** log its start and completion.
    - **Start**: Log inputs/arguments (redacted if verbose).
    - **End**: Log outputs/results (truncated to 500 chars if large).
- **Timing**: Wrap significant operations (external API calls, DB ops) with `with log_timing("operation_name", logger):`.
- **Request ID**: Automatically injected. No manual handling needed.
- **Structured Data**: Pass context as keyword arguments. e.g. `logger.info("event", user_id=123)`.
