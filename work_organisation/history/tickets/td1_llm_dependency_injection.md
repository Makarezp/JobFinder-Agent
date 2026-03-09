# Ticket TD-1: Inject LLM Instances via `get_compiled_graph()` Instead of Module-Level Globals

## Overview
Both `app/agent/main/nodes.py` (lines 31-37) and `app/agent/onboarding/nodes.py` (lines 28-34) instantiate `ChatGoogleGenerativeAI` at **module-level**. This means the LLM clients are created at **import time**, making them impossible to substitute without `patch()`-ing deep internal paths. This violates Design Principle #5 (Dependency Injection) and forces every test to use fragile patches like `patch("app.agent.main.nodes.main_llm")`.

**Why it matters**: The DI wiring point (`app/api/dependencies.py`) exists precisely to avoid this pattern. Fixing this makes all LLM-dependent tests simpler, safer, and consistent with the project's architectural standards.

## Current State (What exists today)

### `app/agent/main/nodes.py` (lines 30-37):
```python
# --- LLM initialization ---
llm = ChatGoogleGenerativeAI(
    model=settings.GEMINI_MODEL_NAME,
    temperature=0,
    google_api_key=settings.GEMINI_API_KEY,
)
main_llm = llm.bind_tools(main_tools)
```

### `app/agent/onboarding/nodes.py` (lines 27-34):
```python
# --- LLM initialization ---
llm = ChatGoogleGenerativeAI(
    model=settings.GEMINI_MODEL_NAME,
    temperature=0,
    google_api_key=settings.GEMINI_API_KEY,
)
onboarding_llm = llm.bind_tools(onboarding_tools)
```

### Tests currently patch deep internal paths:
- `tests/unit/test_agent.py` — `patch("app.agent.main.nodes.main_llm")` (lines 53, 130)
- `tests/unit/test_agent.py` — `patch("app.agent.onboarding.nodes.onboarding_llm")` (lines 75, 94, 149)
- `tests/unit/test_main_nodes.py` — `patch("app.agent.main.nodes.main_llm")` (line 216)
- `tests/unit/test_message_trimming.py` — `patch("app.agent.main.nodes.main_llm")` (lines 61, 80, 99, 115, 135)

## Implementation Steps

### 1. Create LLM factory in `app/agent/graph.py`

In `get_compiled_graph()` (line 119), construct both LLM instances **inside the function** and inject them into the node functions via `functools.partial`:

```python
def get_compiled_graph(checkpointer: Any, store: BaseStore) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Compiles the graph with the provided checkpointer and store."""
    profile_service = ProfileService(store)

    # --- LLM construction (single wiring point) ---
    base_llm = ChatGoogleGenerativeAI(
        model=settings.GEMINI_MODEL_NAME,
        temperature=0,
        google_api_key=settings.GEMINI_API_KEY,
    )
    bound_main_llm = base_llm.bind_tools(main_tools)
    bound_onboarding_llm = base_llm.bind_tools(onboarding_tools)

    builder = StateGraph(AgentState)

    # Nodes — inject LLMs via partial
    builder.add_node(
        MAIN_CHATBOT_NODE,
        functools.partial(main_chatbot, llm=bound_main_llm),
    )
    builder.add_node(
        ONBOARDING_CHATBOT_NODE,
        functools.partial(onboarding_chatbot, llm=bound_onboarding_llm),
    )
    # ... rest unchanged
```

### 2. Update `app/agent/main/nodes.py`

- **Delete** lines 30-37 (the module-level `llm` and `main_llm` globals).
- **Delete** the `from langchain_google_genai import ChatGoogleGenerativeAI` import.
- **Delete** the `from app.core.config import settings` import (if no longer used).
- **Delete** the `from app.agent.main.tools import main_tools` import (if only used for `bind_tools` — verify first; it IS also used in `route_main` indirectly via tool name checks, but tool names are string constants so this import may still be removable).
- **Add** an `llm` parameter to `main_chatbot`:

```python
@traceable
def main_chatbot(state: AgentState, llm: Any) -> dict[str, list[BaseMessage]]:
    """Main job-hunting agent node — uses structured profile and preferences."""
    # ... all existing logic unchanged, but replace `main_llm.invoke(all_messages)`
    # with `llm.invoke(all_messages)` on line 243.
```

> **Type hint**: Use `BaseChatModel` from `langchain_core.language_models` instead of `Any` for the `llm` parameter. Verify this type is compatible with `bind_tools()` return type — if not, use `RunnableSerializable` or keep `Any` with a `# TODO` comment.

### 3. Update `app/agent/onboarding/nodes.py`

- **Delete** lines 27-34 (the module-level `llm` and `onboarding_llm` globals).
- **Delete** the `from langchain_google_genai import ChatGoogleGenerativeAI` import.
- **Delete** the `from app.core.config import settings` import (if no longer used — check `check_onboarding_status`; it does NOT use `settings`, so safe to delete).
- **Add** an `llm` parameter to `onboarding_chatbot`:

```python
@traceable
def onboarding_chatbot(state: AgentState, llm: Any) -> dict[str, list[BaseMessage]]:
    """Onboarding agent node — builds user profile through conversation."""
    # ... all existing logic unchanged, but replace `onboarding_llm.invoke(all_messages)`
    # with `llm.invoke(all_messages)` on line 73.
```

### 4. Update `app/agent/graph.py` imports

Add the new imports needed:
```python
from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import settings
from app.agent.onboarding.tools import onboarding_tools  # already imported on line 37
from app.agent.main.tools import main_tools  # already imported on line 30
```

### 5. Update Tests

All test patches must change from deep internal paths to injecting mock LLMs directly:

**`tests/unit/test_agent.py`**:
- The graph fixture (`get_compiled_graph(checkpointer=MemorySaver(), store=InMemoryStore())`) already constructs the graph. After this refactor, the LLMs are created inside `get_compiled_graph`. To mock them in integration-style tests, patch at `app.agent.graph.ChatGoogleGenerativeAI` (the single wiring point) instead of patching each node module's global.
- Replace all `patch("app.agent.main.nodes.main_llm")` → `patch("app.agent.graph.ChatGoogleGenerativeAI")`.
- Replace all `patch("app.agent.onboarding.nodes.onboarding_llm")` → same.
- The mock must return a mock that has a `.bind_tools()` method returning another mock with `.invoke()`.

**`tests/unit/test_main_nodes.py`**:
- Line 216: Replace `patch("app.agent.main.nodes.main_llm")` → pass a mock LLM directly as the `llm` kwarg when calling `main_chatbot(state, llm=mock_llm)`. This is now trivial — no patching needed at all.

**`tests/unit/test_message_trimming.py`**:
- Lines 61, 80, 99, 115, 135: Same approach — call `main_chatbot(state, llm=mock_llm)` directly. All 5 test functions become patch-free.

## Explicit Constraints & Warnings

- **DO NOT** move tool registration (`main_tools`, `onboarding_tools`) into `get_compiled_graph`. The tool lists are static and correctly defined in their respective `tools.py` files. Only the LLM construction and `bind_tools()` call moves.
- **DO NOT** change the `ToolNode(tools=main_tools)` or `ToolNode(tools=onboarding_tools)` calls — these are already correct and unrelated to LLM injection.
- **DO NOT** change the function signatures of `route_main`, `route_onboarding`, `route_after_onboarding_tools`, `fetch_profile`, or `check_onboarding_status` — these functions do not use the LLM and are unaffected.
- **VERIFY** that `functools.partial(main_chatbot, llm=bound_main_llm)` works correctly with LangGraph's node invocation. LangGraph passes `state` as the first positional arg, and `functools.partial` injects keyword args. The `@traceable` decorator from LangSmith must be compatible with `partial`. If not, use a closure (lambda) instead.
- **KEEP** the `@traceable` decorator on both chatbot functions — do not remove it during refactoring.

## Acceptance Criteria

- [Automated] `tests/unit/test_main_nodes.py` calls `main_chatbot(state, llm=mock_llm)` directly — zero `patch()` calls for LLM mocking.
- [Automated] `tests/unit/test_message_trimming.py` calls `main_chatbot(state, llm=mock_llm)` directly — zero `patch()` calls for LLM mocking.
- [Automated] `tests/unit/test_agent.py` patches `app.agent.graph.ChatGoogleGenerativeAI` (single wiring point) — no deep path patches remain.
- [Automated] `grep -r "app.agent.main.nodes.main_llm" tests/` returns zero results.
- [Automated] `grep -r "app.agent.onboarding.nodes.onboarding_llm" tests/` returns zero results.
- [Automated] `grep -r "main_llm\|onboarding_llm" app/agent/main/nodes.py app/agent/onboarding/nodes.py` returns zero results (no module-level LLM globals remain).
- [Automated] All existing tests pass: `pytest` green, `mypy --strict` clean, `ruff check .` clean.
