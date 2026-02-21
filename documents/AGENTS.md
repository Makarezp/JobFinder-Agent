# AGENTS.md - The AI Manual

## 1. Codebase Map

### Backend (`app/`)
- **Ingress**: `app/api/` (Routes, Dependencies, Middleware).
- **Service**: `app/services/chat_service.py` (Graph orchestration, PDF parsing).
- **Agent**: `app/agent/` (Graph, Nodes, State, Schemas, Prompts).
- **Tools**: `app/tools/` (Adzuna API, Scraper).
- **Config**: `app/core/config.py` (Pydantic Settings).
- **Logging**: `app/core/logging.py` (Structured JSON, ContextVar, Timing).
- **Tests**: `tests/` (Unit & Integration).

### Frontend (`frontend/`)
- **Pages**: `frontend/src/app/` (Next.js App Router — pages and layouts).
- **API Client**: `frontend/src/core/api/` (fetch wrappers for backend REST endpoints).
- **State**: `frontend/src/core/store/` (Zustand stores).
- **Types**: `frontend/src/core/types/` (Shared TypeScript interfaces and types).

> The `core/` boundary is strict: presentation logic lives in `app/`, business/state logic lives in `core/`. Components in `app/` import from `core/`, never the reverse.

## 2. Workflows

### How to Add a New Backend Tool
1.  **Create File**: Add `app/tools/my_new_tool.py`.
2.  **Define Args**: Create a Pydantic model `MyToolArgs` with `Annotated` validators if input is flexible.
3.  **Implement**: Write the `@tool` decorated function.
    - **CRITICAL**: Return a `str` on error, do NOT raise exceptions.
4.  **Register**: Import in `app/agent/nodes.py` and add to `tools` list.

### How to Modify the Agent
1.  **Flow**: Edit `app/agent/graph.py` to change edges or conditional logic (`route_tools`).
2.  **Logic**: Edit `app/agent/nodes.py` to change prompt construction or tool invocation.
3.  **State**: Edit `app/agent/state.py` if you need to store new data across steps.

### How to Add a New Backend Route
1.  Add endpoint in `app/api/routes.py`.
2.  Inject `ChatService` via `ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]`.
3.  Never instantiate `ChatService` directly — always use `Depends()`.
4.  All routes must be under the `/api` prefix (e.g. `POST /api/chat`).

### How to Add a New Frontend Store Action
1.  Add the action to the relevant Zustand store in `frontend/src/core/store/`.
2.  The action calls a fetch wrapper from `frontend/src/core/api/` — never `fetch()` directly in components.
3.  Write a unit test in `*.test.ts` alongside the store file.

## 3. Gotchas (Known Pitfalls)

### LogRecord reserved attributes
Python's `logging.LogRecord` has built-in attributes (`filename`, `funcName`, `module`, `name`, `msg`, etc.). Never use these as keys in `extra={}` — it will raise `KeyError: "Attempt to overwrite 'filename' in LogRecord"`. Use prefixed names like `cv_filename` instead.

### Missing Return Types
Python functions (especially tests and `__init__`) often default to returning `None`, but `mypy --strict` requires explicit `-> None` annotation. Always include it.

### Pre-commit mypy vs direct mypy
The pre-commit hook runs mypy **per-file** (isolated resolution), while `mypy app/` runs on the full project. Starlette's `Request` class triggers `[type-arg]` errors only in per-file mode. Fix: use `# type: ignore[type-arg]` on `Request` params + `warn_unused_ignores = false` in `[tool.mypy]`.

### Test mocking strategy
Always patch dependencies at `app.api.dependencies.graph` — the single DI wiring point. Never patch deep internal paths like `app.services.chat_service.graph`. The DI layer exists specifically to make this easy.
