# AGENTS.md - The AI Manual

## 📌 Context Guidance
- **PERSONAS**: All AI interactions should begin with a persona assignment. Refer to **[PERSONAS.md](PERSONAS.md)** for your specific read-list.
- **HISTORY**: The `work_organisation/history/` folder is **OFF-LIMITS**. Do not read unless explicitly requested by name. Legacy designs *will* poison your context and lead to incorrect implementation.
- **TASKS**: `work_organisation/sprints/` and `work_organisation/bugs/` should only be read when actively working on a related ticket.

## 1. Codebase Map

### Backend (`app/`)
- **Ingress**: `app/api/` (Routes, Dependencies, Middleware, Schemas).
- **Service**: `app/services/chat_service.py` (Graph orchestration, PDF parsing, workspace routing).
- **Agent — Discovery**: `app/agent/discovery/` (graph, state). Implementation nodes & prompts live in `app/agent/main/`.
- **Agent — Profile**: `app/agent/profile/` (graph, state, fetch node). Implementation nodes & prompts live in `app/agent/onboarding/`.
- **Agent — Job Search**: `app/agent/job_search/` (self-contained subgraph, unchanged).
- **Agent — Shared**: `app/agent/schemas.py`, `app/agent/constants.py`, `app/agent/memory_schema.py`.
- **Tools**: `app/tools/` (JSearch API client, LangGraph memory tools).
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
4.  **Register**: Import in the appropriate nodes file and add to the `tools` list:
    - Discovery-facing tool → `app/agent/main/nodes.py`
    - Profile-facing tool → `app/agent/onboarding/nodes.py`

### How to Modify the Agent

The application runs two **isolated compiled graphs**. Choose the correct one for your change:

| Workspace | Graph file | Node file | State file |
| :--- | :--- | :--- | :--- |
| **Discovery** | `app/agent/discovery/graph.py` | `app/agent/main/nodes.py` | `app/agent/discovery/state.py` (`DiscoveryAgentState`) |
| **Profile** | `app/agent/profile/graph.py` | `app/agent/onboarding/nodes.py` | `app/agent/profile/state.py` (`ProfileAgentState`) |

1.  **Flow**: Edit the relevant `graph.py` to change edges or conditional routing.
2.  **Logic**: Edit the relevant nodes file (`main/nodes.py` or `onboarding/nodes.py`) to change prompt construction or tool invocation.
3.  **State**: Edit the relevant `state.py` if you need to store new data across steps. Remember: `DiscoveryAgentState` never holds `cv_raw_text`; `ProfileAgentState` never holds `search_attempts`.
4.  **Routing**: Workspace selection happens in `app/services/chat_service.py` (`_get_graph`). The `thread_id` is automatically suffixed with the workspace name to keep checkpoints isolated.

### How to Add a New Backend Route
1.  Add endpoint in `app/api/routes.py`.
2.  Define request/response Pydantic models in `app/api/schemas.py` — never inline them in `routes.py`.
3.  Inject `ChatService` via `ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]`.
4.  Never instantiate `ChatService` directly — always use `Depends()`.
5.  All routes must be under the `/api` prefix (e.g. `POST /api/chat`).

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
Always patch the graph dependencies at `app.api.dependencies` — the single DI wiring point. The two dependency functions are `get_discovery_graph` and `get_profile_graph`. Never patch deep internal paths like `app.services.chat_service._discovery_graph`. The DI layer exists specifically to make this easy.
