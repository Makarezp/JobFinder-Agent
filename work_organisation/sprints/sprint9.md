``# Sprint 9: Contextual Workspaces

**Spec**: [contextual-workspaces.md](../spec/contextual-workspaces.md)
**Goal**: Transition from a monolithic dual-agent graph to isolated, workspace-specific agents (Discovery + Profile), routed at the service layer.

---

## Ticket 9.1: Extract Discovery Agent Graph - done

### Overview
Create a self-contained Discovery Agent as a standalone compiled LangGraph graph with its own state schema. This extracts the existing `main/` agent logic (nodes, prompts, tools) into a new `app/agent/discovery/` package with its own `DiscoveryAgentState` and `get_discovery_graph()` builder. The monolithic `graph.py` remains untouched — this ticket only **adds**, it does not delete or rewire anything.

### Implementation Steps

1. **[New File — `app/agent/discovery/__init__.py`]**: Create an empty `__init__.py`.

2. **[New File — `app/agent/discovery/state.py`]**: Define `DiscoveryAgentState(TypedDict)` with exactly these fields:
   ```python
   class DiscoveryAgentState(TypedDict):
       messages: Annotated[list[BaseMessage], operator.add]
       user_profile: dict[str, Any] | None
       preferences: dict[str, Any] | None
       search_attempts: int
       recent_decisions: NotRequired[list[dict[str, Any]]]
   ```
   - **No `onboarding_complete`** — routing is handled externally by `ChatService`.
   - **No `cv_raw_text`** — the Discovery Agent never processes CVs.
   - Add a docstring explaining that `user_profile`, `preferences`, and `recent_decisions` are hydrated from the LangGraph Store via `fetch_profile` on every turn.

3. **[New File — `app/agent/discovery/graph.py`]**: Create `get_discovery_graph(checkpointer, store) -> CompiledStateGraph` that builds the Discovery Agent graph.
   - Import the existing node functions from `app.agent.main.nodes`: `fetch_profile`, `main_chatbot`, `route_main`.
   - Import `main_tools` from `app.agent.main.tools`.
   - Import `call_job_specialist` from the **current** `app.agent.graph` (temporarily — it will be relocated in Ticket 9.3).
   - The graph topology is:
     ```
     START → fetch_profile → main_chatbot → [route_main] → main_tools → main_chatbot
                                           → [route_main] → job_specialist → main_chatbot
                                           → [route_main] → END
     ```
   - Wire `ProfileService(store)` into `call_job_specialist` via `functools.partial`, exactly as done in the current `get_compiled_graph()`.
   - Wire `store` into `fetch_profile` via `functools.partial`, exactly as done currently.
   - Use `DiscoveryAgentState` (not `AgentState`) as the state schema for `StateGraph`.
   - Compile with the provided `checkpointer` and `store`.

4. **[Update Constants — `app/agent/constants.py`]**: Add new node name constants for the discovery graph. These can initially reuse the same string values as the existing `MAIN_CHATBOT_NODE`, `MAIN_TOOLS_NODE`, etc. — they are just node labels within the graph. Add a comment noting these are for the standalone discovery graph:
   ```python
   # Discovery Agent Node Names
   DISCOVERY_FETCH_PROFILE_NODE: Final[str] = "fetch_profile"
   DISCOVERY_CHATBOT_NODE: Final[str] = "discovery_chatbot"
   DISCOVERY_TOOLS_NODE: Final[str] = "discovery_tools"
   DISCOVERY_JOB_SPECIALIST_NODE: Final[str] = "job_specialist_node"
   ```

5. **[Update Type Hints — `app/agent/main/nodes.py`]**: The node functions `fetch_profile`, `main_chatbot`, and `route_main` are currently typed with `state: AgentState`. Update them to `state: DiscoveryAgentState`:
   - Replace: `from app.agent.state import AgentState`
   - With: `from app.agent.discovery.state import DiscoveryAgentState`
   - Update all three function signatures: `fetch_profile(state: DiscoveryAgentState, ...)`, `main_chatbot(state: DiscoveryAgentState)`, `route_main(state: DiscoveryAgentState)`.
   - **Why now (not in 9.4)?** Without this change, `mypy` will fail when `StateGraph(DiscoveryAgentState)` adds nodes typed with `AgentState`. The monolithic graph in `graph.py` will still work because Python dicts are structurally compatible at runtime, and `graph.py` already uses `AgentState` which is a superset.

6. **[New Test — `tests/unit/test_discovery_graph.py`]**: Create a test file with these specific tests:
   - `test_discovery_graph_compiles`: Call `get_discovery_graph(checkpointer=MemorySaver(), store=InMemoryStore())`. Assert the returned object is not `None`.
   - `test_discovery_graph_has_correct_nodes`: Assert the compiled graph contains nodes `fetch_profile`, `discovery_chatbot` (or whatever name is used), `discovery_tools`, and `job_specialist_node`.
   - `test_discovery_graph_does_not_contain_onboarding_nodes`: Assert the graph does **not** contain `onboarding_chatbot` or `onboarding_tools` or `check_onboarding_status`.
   - `test_discovery_state_has_no_onboarding_fields`: Verify that `DiscoveryAgentState` does not have `onboarding_complete` or `cv_raw_text` as keys (use `DiscoveryAgentState.__annotations__`).

### Explicit Constraints & Warnings
- **DO NOT modify `app/agent/graph.py`**. The monolithic graph must continue to work.
- **DO NOT move or rename the `app/agent/main/` directory yet.** The rename to `discovery/` happens later (Ticket 9.3) when the monolith is deleted. For now, `discovery/graph.py` imports from `app.agent.main.*`.
- **DO NOT duplicate node functions.** `discovery/graph.py` imports `main_chatbot`, `fetch_profile`, `route_main` from `app.agent.main.nodes` — it does not copy them.
- **The `call_job_specialist` function currently lives in `app/agent/graph.py`.** Import it from there for now. It will be relocated in Ticket 9.3.
- **Updating type hints in `main/nodes.py` (step 5) is the one non-additive change in this ticket.** The monolithic `graph.py` compiles with `AgentState` (a superset of `DiscoveryAgentState`). Since Python TypedDicts are structurally typed, `DiscoveryAgentState` is compatible — the monolithic graph will still pass `mypy` and work at runtime.

### Acceptance Criteria
- [Automated] `test_discovery_graph_compiles` passes — the graph builds without error.
- [Automated] `test_discovery_graph_has_correct_nodes` passes — all expected nodes are present.
- [Automated] `test_discovery_graph_does_not_contain_onboarding_nodes` passes — no onboarding leakage.
- [Automated] `test_discovery_state_has_no_onboarding_fields` passes — state schema is clean.
- [Automated] `mypy app/agent/main/nodes.py` passes with no errors — type hints are consistent.
- [Automated] All existing tests in `tests/unit/test_agent.py` still pass — the monolithic graph is unaffected by the type hint change.

---

## Ticket 9.2: Extract Profile Agent Graph

### Overview
Create a self-contained Profile Agent as a standalone compiled LangGraph graph with its own state schema. This extracts the existing `onboarding/` agent logic (nodes, prompts, tools) into a new `app/agent/profile/` package with its own `ProfileAgentState` and a `get_profile_graph()` builder. The Profile Agent must hydrate its own state from the database at the start of each turn. The monolithic `graph.py` remains untouched — this ticket is entirely additive to avoid breaking existing flows before we test.

### Implementation Steps

1. **[New File — `app/agent/profile/__init__.py`]**: Create an empty `__init__.py`.

2. **[New File — `app/agent/profile/state.py`]**: Define `ProfileAgentState(TypedDict)` with exactly these fields:
   ```python
   class ProfileAgentState(TypedDict):
       messages: Annotated[list[BaseMessage], operator.add]
       user_profile: dict[str, Any] | None
       preferences: dict[str, Any] | None
       cv_raw_text: str | None
   ```
   - **No `onboarding_complete`** — routing is handled externally.
   - **No `search_attempts` or `recent_decisions`** — Profile Agent does not search for jobs.
   - Add a docstring explaining that this agent handles CV parsing, profile building, and preference capture.

3. **[Update Type Hints — `app/agent/onboarding/nodes.py`]**: The node functions `check_onboarding_status`, `onboarding_chatbot`, `route_onboarding`, and `route_after_onboarding_tools` currently use `AgentState`.
   - Update the import: `from app.agent.profile.state import ProfileAgentState` (instead of `AgentState`).
   - Change `state: AgentState` to `state: ProfileAgentState` in all function signatures.
   - **Why now?** Because `profile/graph.py` will use these nodes, and `mypy` will fail if their signatures don't match the new state class.

4. **[New File — `app/agent/profile/nodes.py`]**: Create a dedicated node to hydrate state for the Profile Agent upon entry:
   ```python
   import asyncio
   from typing import Annotated, Any
   import structlog
   from langchain_core.runnables import RunnableConfig
   from langgraph.prebuilt import InjectedStore
   from langgraph.store.base import BaseStore
   from app.agent.memory_schema import Preference, UserProfile
   from app.agent.profile.state import ProfileAgentState

   logger = structlog.get_logger(__name__)

   async def fetch_profile_data(state: ProfileAgentState, config: RunnableConfig, store: Annotated[BaseStore, InjectedStore]) -> dict[str, Any]:
       """Read user profile and preferences from Store and inject into state."""
       logger.info("Node Started: fetch_profile_data")
       user_id = config.get("configurable", {}).get("user_id", "default_user")

       profile_item, prefs_items = await asyncio.gather(
           store.aget((user_id, "profile"), "data"),
           store.asearch((user_id, "preferences")),
       )

       profile = UserProfile(**profile_item.value) if profile_item else UserProfile()

       preferences: dict[str, Any] = {}
       for item in prefs_items:
           if item.value:
               try:
                   pref = Preference(**item.value)
                   preferences[item.key] = pref.model_dump()
               except Exception:
                   logger.warning(f"Skipping invalid preference: {item.key}")

       return {
           "user_profile": profile.model_dump(),
           "preferences": preferences,
       }
   ```
   *Note: We don't fetch `recent_decisions` or inject system triggers here like the old discovery `fetch_profile` node did.*

5. **[Update Constants — `app/agent/constants.py`]**: Add new node name constants for the profile graph:
   ```python
   # Profile Agent Node Names
   PROFILE_FETCH_NODE: Final[str] = "fetch_profile_data"
   PROFILE_CHATBOT_NODE: Final[str] = "profile_chatbot"
   PROFILE_TOOLS_NODE: Final[str] = "profile_tools"
   ```

6. **[New File — `app/agent/profile/graph.py`]**: Create `get_profile_graph(checkpointer, store) -> CompiledStateGraph` that builds the Profile Agent graph.
   - Import `onboarding_chatbot`, `route_onboarding` from `app.agent.onboarding.nodes`.
   - Import `onboarding_tools` from `app.agent.onboarding.tools`.
   - Import `fetch_profile_data` from `app.agent.profile.nodes`.
   - The graph topology is:
     ```
     START → fetch_profile_data → profile_chatbot → [route_onboarding] → profile_tools → profile_chatbot
                                                  → [route_onboarding] → END
     ```
   - **Node mappings**: Add nodes with correct labels:
     - `builder.add_node(PROFILE_FETCH_NODE, fetch_profile_data)`
     - `builder.add_node(PROFILE_CHATBOT_NODE, onboarding_chatbot)`
     - `builder.add_node(PROFILE_TOOLS_NODE, ToolNode(tools=onboarding_tools))`
   - **Edges**:
     - Add edge from `START` to `PROFILE_FETCH_NODE`, and from `PROFILE_FETCH_NODE` to `PROFILE_CHATBOT_NODE`.
     - `route_onboarding` returns `"onboarding_tools_node"`. Use conditional edges: `builder.add_conditional_edges(PROFILE_CHATBOT_NODE, route_onboarding, {ONBOARDING_TOOLS_NODE: PROFILE_TOOLS_NODE, END: END})`
     - Loop back without ghosting: `builder.add_edge(PROFILE_TOOLS_NODE, PROFILE_CHATBOT_NODE)`. (If `finalize_profile` is called, the LLM will see the tool response and generate a natural confirmation message).
   - Compile using `ProfileAgentState` with the provided `checkpointer` and `store`.

7. **[New Test — `tests/unit/test_profile_graph.py`]**: Create tests for the new graph:
   - `test_profile_graph_compiles`: Call `get_profile_graph(MemorySaver(), InMemoryStore())` and assert compile succeeds.
   - `test_profile_graph_has_correct_nodes`: Assert graph has `fetch_profile_data`, `profile_chatbot`, `profile_tools`.
   - `test_profile_graph_does_not_contain_discovery_nodes`: Assert graph lacks `main_chatbot`, `job_specialist_node`, etc.
   - `test_profile_state_has_no_discovery_fields`: Verify `ProfileAgentState.__annotations__` doesn't have `search_attempts` or `recent_decisions`.

### Explicit Constraints & Warnings
- **DO NOT modify `app/agent/graph.py`**. The monolithic graph must continue to work.
- **DO NOT move or rename the `app/agent/onboarding/` directory yet.** The rename to `profile/` happens later.
- **DO NOT duplicate node functions.** `profile/graph.py` imports `onboarding_chatbot` and `route_onboarding` from `app.agent.onboarding.nodes` — it does not copy them.
- **Routing without Ghosting:** We explicitly do *not* terminate immediately after `PROFILE_TOOLS_NODE`. We loop back to `PROFILE_CHATBOT_NODE` so the LLM can acknowledge tool execution (like saving the profile) to the user.
- **Updating type hints in `onboarding/nodes.py` (step 3) is safe.** The monolithic `graph.py` compiles with `AgentState`, which has the same structure runtime-wise as `ProfileAgentState`.

### Acceptance Criteria
- [Automated] `test_profile_graph_compiles` passes — the graph builds without error.
- [Automated] `test_profile_graph_has_correct_nodes` passes — all expected nodes are present.
- [Automated] `test_profile_graph_does_not_contain_discovery_nodes` passes — no discovery/job search leakage.
- [Automated] `test_profile_state_has_no_discovery_fields` passes — state schema is clean.
- [Automated] `mypy app/agent/onboarding/nodes.py` passes with no errors — type hints are consistent.
- [Automated] All existing tests in `tests/unit/test_agent.py` still pass.

---

## Ticket 9.3: Wire Workspace Routing

### Overview
Refactor the backend to route chat requests to the correct agent graph based on a `workspace` property in the API payload. After this ticket, the application runs entirely on the two standalone graphs from Tickets 9.1 and 9.2. The monolithic `graph.py` is no longer invoked at runtime but is **not deleted yet** (that happens in Ticket 9.4).

### Implementation Steps

1. **[API Schema — `app/api/schemas.py`]**: Add a `workspace` field to `ChatRequest`:
   ```python
   from typing import Literal

   class ChatRequest(BaseModel):
       message: str
       workspace: Literal["discovery", "profile"] = "discovery"
   ```
   - Default to `"discovery"` for backward compatibility — existing callers that don't send `workspace` will get the Discovery Agent.
   - Use `Literal` to restrict to valid workspace names. Pydantic will return 422 for invalid values.

2. **[ChatService — `app/services/chat_service.py`]**: Refactor the constructor and routing:
   - **Change `__init__` signature** to accept two graphs instead of one:
     ```python
     def __init__(
         self,
         discovery_graph: CompiledStateGraph[Any],
         profile_graph: CompiledStateGraph[Any],
         store: BaseStore,
         profile_service: ProfileService,
     ) -> None:
         self._discovery_graph = discovery_graph
         self._profile_graph = profile_graph
         self._store = store
         self._profile_service = profile_service
     ```
   - **Add a private routing method**:
     ```python
     def _get_graph(self, workspace: str) -> CompiledStateGraph[Any]:
         if workspace == "profile":
             return self._profile_graph
         else:
             return self._discovery_graph
     ```
   - **Update `process_message`** signature to accept `workspace: str = "discovery"`:
     - Call `self._get_graph(workspace)` instead of `self._graph`.
     - Suffix the `thread_id` with the workspace name: `thread_id=f"{thread_id}_{workspace}"`. This gives mathematically isolated LangGraph memory checkpoints.
     - The `search_attempts: 0` input field should only be included when `workspace == "discovery"` (the Profile Agent's `ProfileAgentState` does not have this field).
     - The `cv_raw_text` field is irrelevant for discovery — do not include it.
   - **Update `process_cv`**:
     - Always use `self._profile_graph` (CV upload is always a Profile workspace action).
     - Suffix thread_id: `thread_id=f"{thread_id}_profile"`.
     - The inputs dict should not include `search_attempts` (Profile Agent state doesn't have it).
   - **Update `get_history`** signature to accept `workspace: str = "discovery"`:
     - Call `self._get_graph(workspace)` instead of `self._graph`.
     - Suffix thread_id: `thread_id=f"{thread_id}_{workspace}"`.

3. **[Dependencies — `app/api/dependencies.py`]**: Update the DI wiring:
   - **Add `get_discovery_graph` and `get_profile_graph`** dependency functions:
     ```python
     def get_discovery_graph(request: Request) -> CompiledStateGraph[Any]:
         return request.app.state.discovery_graph

     def get_profile_graph(request: Request) -> CompiledStateGraph[Any]:
         return request.app.state.profile_graph
     ```
   - **Update `get_chat_service`** to inject both graphs:
     ```python
     def get_chat_service(
         discovery_graph: Annotated[CompiledStateGraph[Any], Depends(get_discovery_graph)],
         profile_graph: Annotated[CompiledStateGraph[Any], Depends(get_profile_graph)],
         store: Annotated[BaseStore, Depends(get_store)],
     ) -> ChatService:
         return ChatService(discovery_graph, profile_graph, store, ProfileService(store))
     ```
   - **Delete** the old `get_graph` function (it referenced `app.state.graph` which will no longer exist).

4. **[Routes — `app/api/routes.py`]**: Pass `workspace` through to the service:
   - **`POST /api/chat`**: Pass `body.workspace` to `service.process_message(body.message, workspace=body.workspace)`.
   - **`POST /api/upload-cv`**: No change needed — `process_cv` always uses the profile graph internally.
   - **`GET /api/history`**: Add an optional `workspace` query parameter: `async def get_history(service: ChatServiceDep, workspace: str = "discovery")`. Pass it to `service.get_history(workspace=workspace)`.

5. **[App Startup — `app/main.py`]**: Build both graphs at startup:
   - **Replace** the single `get_compiled_graph` import with imports of both:
     ```python
     from app.agent.discovery.graph import get_discovery_graph
     from app.agent.profile.graph import get_profile_graph
     ```
   - **In the `lifespan` function**, replace:
     ```python
     # Old:
     graph = get_compiled_graph(checkpointer=checkpointer, store=store)
     app.state.graph = graph

     # New:
     app.state.discovery_graph = get_discovery_graph(checkpointer=checkpointer, store=store)
     app.state.profile_graph = get_profile_graph(checkpointer=checkpointer, store=store)
     ```
   - Delete the `app.state.graph` assignment. Delete the `from app.agent.graph import get_compiled_graph` import.

6. **[Update Test — `tests/unit/test_chat_service.py`]**: Update the `_make_service` helper and all tests to provide two graphs:
   - Update `_make_service` to pass `discovery_graph` and `profile_graph` kwargs:
     ```python
     def _make_service(store: InMemoryStore) -> ChatService:
         discovery_graph = _make_graph_mock([JOB_A, JOB_B])
         profile_graph = _make_graph_mock([])  # Profile agent never returns jobs
         profile_service = ProfileService(store=store)
         return ChatService(
             discovery_graph=discovery_graph,
             profile_graph=profile_graph,
             store=store,
             profile_service=profile_service,
         )
     ```
   - Update `test_process_message_no_jobs_does_not_call_add_pending` — it manually creates a `ChatService`; update its constructor call to match the new signature.
   - Update `test_get_history_filters_system_trigger` — it manually creates a `ChatService`; update its constructor call.
   - Add new test `test_process_message_routes_to_discovery_by_default`: Call `process_message("find jobs")` without a workspace param. Assert the discovery graph's `astream` was called (not the profile graph's).
   - Add new test `test_process_message_routes_to_profile`: Call `process_message("update my name", workspace="profile")`. Assert the profile graph's `astream` was called.
   - Add new test `test_process_cv_always_uses_profile_graph`: Call `process_cv(...)`. Assert the profile graph's `astream` was called regardless of any workspace parameter.

7. **[Update Test — `tests/integration/test_api_chat.py`]**: The integration test overrides `get_chat_service` via `app.dependency_overrides`. The mock service's `process_message` signature now accepts `workspace`, but since `process_message` is an `AsyncMock`, it automatically accepts any kwargs. **No changes needed** — verify this by running the existing tests.

### Explicit Constraints & Warnings
- **DO NOT delete `app/agent/graph.py` in this ticket.** The monolithic graph file still exists on disk but is no longer imported by any production code. Deletion happens in Ticket 9.4.
- **The `thread_id` suffix is the memory isolation mechanism.** `"default_user_session_discovery"` and `"default_user_session_profile"` are completely separate checkpoint timelines. If you forget the suffix, both workspaces will share the same conversation history.
- **The `search_attempts` field must NOT be included in the inputs dict when routing to the profile graph.** `ProfileAgentState` does not define this field. LangGraph will raise a `ValueError` if you pass fields not in the state schema.
- **The `ChatRequest.workspace` default is `"discovery"`.** This ensures backward compatibility — the existing frontend (which doesn't send `workspace` yet) will continue to work against the Discovery Agent without changes.
- **`process_cv` hardcodes the profile graph.** CV uploads are always a Profile workspace action. Do not route based on any workspace parameter.
- **The old `get_graph` function in `dependencies.py` must be deleted** — it references `app.state.graph` which no longer exists after the startup change.

### Acceptance Criteria
- [Automated] `test_process_message_routes_to_discovery_by_default` passes — default workspace is discovery.
- [Automated] `test_process_message_routes_to_profile` passes — explicit workspace routing works.
- [Automated] `test_process_cv_always_uses_profile_graph` passes — CV upload is always profile.
- [Automated] All existing `test_chat_service.py` tests pass with updated constructor calls.
- [Automated] All `tests/integration/test_api_chat.py` tests still pass — backward compatibility confirmed.
- [Manual] Start the backend (`uvicorn app.main:app --reload`). Send `POST /api/chat` with `{"message": "hello"}` (no workspace). Verify a 200 response. Send `POST /api/chat` with `{"message": "hello", "workspace": "profile"}`. Verify a 200 response. Send `POST /api/chat` with `{"message": "hello", "workspace": "invalid"}`. Verify a 422 validation error.

---

## Ticket 9.4: Delete Monolithic Graph & Clean Up Dead Code

### Overview
Remove the now-unused monolithic orchestrator (`app/agent/graph.py`) and shared state schema (`app/agent/state.py`). Relocate `call_job_specialist` and its helpers into the Discovery Agent package. Update all imports and type annotations across production and test code. After this ticket, the `app/agent/` directory has a clean structure with no orphan modules.

### Implementation Steps

1. **[Relocate — `call_job_specialist` into `app/agent/discovery/graph.py`]**: Move these three functions from `app/agent/graph.py` into `app/agent/discovery/graph.py`:
   - `_split_fresh_seen(results, seen_ids)` — pure helper
   - `_run_single_job_search(tool_call, profile_service)` — async helper
   - `call_job_specialist(state, profile_service)` — the node function

   These functions must be placed **above** `get_discovery_graph` in the file. Update the `state` type annotation in `call_job_specialist` from `AgentState` to `DiscoveryAgentState`. All other logic and imports remain identical. The required imports to add to `discovery/graph.py` are:
   - `asyncio`, `json` (for `_run_single_job_search` and `call_job_specialist`)
   - `cast` from `typing` (for `call_job_specialist`)
   - `AIMessage`, `ToolMessage` from `langchain_core.messages`
   - `JobListing`, `JobSpecialistInput` from `app.agent.schemas`
   - `job_search_graph` from `app.agent.job_search.graph`
   - `JobSpecialistState` from `app.agent.job_search.state`
   - `DEFAULT_USER_ID` from `app.agent.constants`
   - `ProfileService` from `app.services.profile_service`

   After the move, `get_discovery_graph` should reference the local `call_job_specialist` instead of importing it.

2. **[Delete — `app/agent/graph.py`]**: Delete the entire monolithic orchestrator file. After Ticket 9.3, no production code imports from it.

3. **[Delete — `app/agent/state.py`]**: Delete the shared `AgentState` TypedDict. It has been replaced by `DiscoveryAgentState` and `ProfileAgentState`.

4. **[Update — `app/agent/main/nodes.py`]**: Change the `AgentState` import to `DiscoveryAgentState`:
   - Replace: `from app.agent.state import AgentState`
   - With: `from app.agent.discovery.state import DiscoveryAgentState`
   - Update all function signatures that use `AgentState` → `DiscoveryAgentState`:
     - `fetch_profile(state: DiscoveryAgentState, ...)`
     - `main_chatbot(state: DiscoveryAgentState)`
     - `route_main(state: DiscoveryAgentState)`

5. **[Update — `app/agent/onboarding/nodes.py`]**: Change the `AgentState` import to `ProfileAgentState`:
   - Replace: `from app.agent.state import AgentState`
   - With: `from app.agent.profile.state import ProfileAgentState`
   - Update all function signatures that use `AgentState` → `ProfileAgentState`:
     - `check_onboarding_status(state: ProfileAgentState, ...)`
     - `onboarding_chatbot(state: ProfileAgentState)`
     - `route_onboarding(state: ProfileAgentState)`
     - `route_after_onboarding_tools(state: ProfileAgentState)`
   - Note: `check_onboarding_status` and `route_after_onboarding_tools` are now dead code (only used by the deleted monolithic graph). They can be left for now or deleted — the executing agent should leave them since `profile/graph.py` does not import them and they may serve as reference.

6. **[Prune Constants — `app/agent/constants.py`]**: Delete the following constants that were only used by the monolithic graph:
   - `CHECK_ONBOARDING_NODE` — only used in deleted `graph.py`
   - `ONBOARDING_COMPLETE_KEY` (if it exists) — same

   **Keep** the following (still actively used):
   - `ONBOARDING_CHATBOT_NODE` — used by `route_onboarding` in `onboarding/nodes.py`
   - `ONBOARDING_TOOLS_NODE` — used by `route_onboarding` return value and edge mapping
   - `FETCH_PROFILE_NODE` — used by `route_after_onboarding_tools` (may be pruned later)
   - `MAIN_CHATBOT_NODE`, `MAIN_TOOLS_NODE`, `JOB_SPECIALIST_NODE` — used if discovery graph references them
   - All discovery/profile node constants added in Tickets 9.1/9.2

7. **[Update Test — `tests/unit/test_agent.py`]**: This file tests both the monolithic graph and individual node functions. Split it:
   - **Delete** these tests (they test the monolithic orchestrator which no longer exists):
     - `test_agent_graph_initialization`
     - `test_agent_graph_has_correct_nodes`
     - `test_router_routes_to_onboarding`
     - `test_router_routes_to_main`
   - **Delete** the `graph` fixture (line 22-25) — it calls `get_compiled_graph`.
   - **Delete** imports of `get_compiled_graph`, `router` from `app.agent.graph`, and `AgentState` from `app.agent.state`.
   - **Keep** these tests (they test individual node functions and schemas, not the graph):
     - `test_main_chatbot_node_adds_system_prompt`
     - `test_onboarding_chatbot_uses_onboarding_prompt`
     - `test_onboarding_chatbot_includes_cv_raw_text`
     - `test_main_chatbot_handles_llm_exception`
     - `test_onboarding_chatbot_handles_llm_exception`
     - `test_job_specialist_input_valid_simple_query`
     - `test_job_specialist_input_valid_with_location_and_country`
   - **Remove** unused imports: `MemorySaver`, `InMemoryStore`, node constants only used in deleted tests.

8. **[Update Test — `tests/unit/test_loop_limits.py`]**: Line 9 imports `call_job_specialist` from `app.agent.graph`. Update:
   - Replace: `from app.agent.graph import call_job_specialist`
   - With: `from app.agent.discovery.graph import call_job_specialist`
   - Update the patch target on line 88: `patch("app.agent.graph.job_search_graph")` → `patch("app.agent.discovery.graph.job_search_graph")`.

9. **[Update Test — `tests/unit/test_job_specialist_nodes.py`]**: Line 7 imports `call_job_specialist` from `app.agent.graph`. Update:
   - Replace: `from app.agent.graph import call_job_specialist`
   - With: `from app.agent.discovery.graph import call_job_specialist`
   - Also replace: `from app.agent.state import AgentState`
   - With: `from app.agent.discovery.state import DiscoveryAgentState`
   - Update any type annotations or fixture state dicts from `AgentState` to `DiscoveryAgentState` if they are used directly. If only inline dicts are used (no `AgentState` annotation), delete the import entirely.
   - Update patch targets: any `patch("app.agent.graph....")` → `patch("app.agent.discovery.graph....")`.

10. **[Update Test — `tests/unit/test_seen_jobs.py`]**: Lines 104, 128, 151, 190, 213 each have local imports `from app.agent.graph import call_job_specialist`. Update all five:
    - Replace: `from app.agent.graph import call_job_specialist`
    - With: `from app.agent.discovery.graph import call_job_specialist`
    - Also update line 23: `from app.agent.state import AgentState` → `from app.agent.discovery.state import DiscoveryAgentState`, and update any references.
    - Update patch targets inside each test function: `patch("app.agent.graph.job_search_graph")` → `patch("app.agent.discovery.graph.job_search_graph")`.

### Explicit Constraints & Warnings
- **DO NOT delete `app/agent/main/` or `app/agent/onboarding/` directories.** These still contain the active node functions, prompts, and tools that both standalone graphs import. A future rename (main→discovery, onboarding→profile) is a separate cosmetic ticket.
- **The patch targets in tests MUST match the new module path.** If a test patches `"app.agent.graph.job_search_graph"` but the function now lives in `"app.agent.discovery.graph"`, the patch will silently do nothing and the test will hit the real (unmocked) code.
- **`check_onboarding_status` and `route_after_onboarding_tools` in `onboarding/nodes.py` are now dead code** — they were only called by the monolithic graph's edge wiring. They can be deleted, but leaving them is acceptable for now since they cause no harm and may serve as reference during the transition.
- **Run `ruff check .` after all changes** to catch any remaining import of `app.agent.graph` or `app.agent.state`.

### Acceptance Criteria
- [Automated] `ruff check .` reports zero errors — no dangling imports of deleted modules.
- [Automated] `mypy .` passes — all type annotations are consistent with the new state schemas.
- [Automated] All tests in `tests/unit/test_loop_limits.py` pass with updated import paths.
- [Automated] All tests in `tests/unit/test_job_specialist_nodes.py` pass with updated import paths.
- [Automated] All tests in `tests/unit/test_seen_jobs.py` pass with updated import and patch paths.
- [Automated] All remaining tests in `tests/unit/test_agent.py` pass (monolithic graph tests deleted, node/schema tests kept).
- [Automated] `pytest` full suite passes — no test references the deleted modules.
- [Manual] Verify `app/agent/graph.py` and `app/agent/state.py` no longer exist on disk.
- [Manual] Verify `app/agent/` directory structure matches:
  ```
  app/agent/
  ├── discovery/     ← graph.py, state.py, __init__.py
  ├── profile/       ← graph.py, state.py, nodes.py, __init__.py
  ├── main/          ← nodes.py, prompts.py, tools.py (still active)
  ├── onboarding/    ← nodes.py, prompts.py, tools.py (still active)
  ├── job_search/    ← unchanged subgraph
  ├── constants.py
  ├── memory_schema.py
  └── schemas.py
  ```

---

## Ticket 9.5: Thread Isolation in Chat Store

### Overview
Refactor the frontend chat API and Zustand store to support multiple isolated message threads. The backend routing is now based on the `workspace` parameter. The frontend must maintain separate state arrays for each workspace (`discovery` and `profile`) so that switching tabs does not clear or mix conversation histories.

### Implementation Steps

1. **[Types — `frontend/src/core/types/api.ts` (or equivalent)]**: Add a new `Workspace` type.
   ```typescript
   export type Workspace = "discovery" | "profile";
   ```

2. **[API — `frontend/src/core/api/chat.ts`]**: Update the fetch functions to accept `Workspace`:
   - `fetchHistoryRequest(workspace: Workspace = "discovery")`: Update the fetch URL to include the query parameter: `fetch(\`/api/history?workspace=${workspace}\`)`.
   - `sendMessageRequest(message: string, workspace: Workspace = "discovery")`: Update the payload to include the workspace: `body: JSON.stringify({ message, workspace })`.
   - `uploadCVRequest` remains unchanged (it utilizes `FormData` and is fundamentally a `profile` action on the backend).

3. **[Store — `frontend/src/core/store/useChatStore.ts`]**: Refactor the state shape and methods.
   - **Update `ChatState` interface**:
     ```typescript
     export interface ChatState {
       threads: Record<Workspace, ChatResponse[]>;
       isPending: Record<Workspace, boolean>;
       fetchHistory: (workspace: Workspace) => Promise<void>;
       sendMessage: (text: string, workspace: Workspace) => Promise<void>;
       uploadCV: (file: File) => Promise<void>;
     }
     ```
   - **Update default state** in the `create` function:
     ```typescript
     threads: { discovery: [], profile: [] },
     isPending: { discovery: false, profile: false },
     ```
   - **Update `fetchHistory(workspace)`**:
     - Use Zustand's functional updater to prevent race conditions: `set((state) => ({ isPending: { ...state.isPending, [workspace]: true } }))`.
     - Await `fetchHistoryRequest(workspace)`.
     - Set `threads`: `set((state) => ({ threads: { ...state.threads, [workspace]: history } }))`.
     - Clear pending state functionally: `set((state) => ({ isPending: { ...state.isPending, [workspace]: false } }))`.
   - **Update `sendMessage(text, workspace)`**:
     - Do optimistic UI update functionally: `set((state) => ({ threads: { ...state.threads, [workspace]: [...state.threads[workspace], optimisticMsg] } }))`.
     - Set pending functionally.
     - Await `sendMessageRequest(text, workspace)`.
     - Update targeted thread with actual response functionally.
     - **Error Handling:** In the `catch` block, explicitly push the error format `ChatResponse` payload into the correct `workspace` thread so failures are surfacing properly. Also functionally clear the `isPending` state.
     - Note: Keep the `useJobStore.getState().fetchDeck()` call exactly as it is.
   - **Update `uploadCV(file)`**:
     - Always target the `'profile'` workspace.
     - Do optimistic UI update on `state.threads['profile']` functionally.
     - Await `uploadCVRequest(file)`.
     - Update `'profile'` thread with the response functionally.
     - **Error Handling:** In the `catch` block, explicitly push the error message into the `profile` thread and functionally clear the `isPending` state.

4. **[Adapt UI — `frontend/src/components` & `app/page.tsx`]**:
   - Temporarily locate any existing component that references `useChatStore((s) => s.messages)` and update it to `useChatStore((s) => s.threads.discovery)` (and similarly for `isPending`).
   - Temporarily pass `"discovery"` to any `sendMessage` or `fetchHistory` calls originating from the UI.
   - *Note: Ticket 9.6 will introduce full tab-based routing. This temporary fix ensures the build succeeds and UI functions without errors immediately after this ticket.*

5. **[Update Tests — `frontend/src/core/store/useChatStore.test.ts`]**:
   - Rewrite assertions to check against `threads.discovery` or `threads.profile` instead of `messages`.
   - Update `fetchHistory` tests to supply a workspace and verify the specific thread array updates while the other does not.
   - Update `sendMessage` tests to assert against a supplied workspace thread.
   - Update `uploadCV` test to assert both the optimistic and final response update `threads.profile`.

### Explicit Constraints & Warnings
- **Race conditions:** Concurrent `fetchHistory` calls (e.g. fetching both tabs on mount) will overwrite each other's pending state if you use `set({ isPending: ...get().isPending })`. You **must** use the functional updater pattern `set((state) => ...)` for nested state modifications.
- **Do not build the visual tabs or new layout in this ticket.** This ticket is strictly about the underlying data structures, API communication, and ensuring compiler correctness. Ticket 9.6 will handle visual representation.
- Ensure the Zustand updates mutate nested objects properly using spread operators.

### Acceptance Criteria
- [Automated] `npm run build` succeeds (no TypeScript errors in components referencing the store).
- [Automated] All tests in `useChatStore.test.ts` pass with the updated thread-based data shape.
- [Automated] Tests inside `api/chat.test.ts` (if applicable) pass.
- [Manual] Run the Next.js dev server. Send a message. Verify the message appears in the UI and the Chrome Network tab shows the JSON payload includes `{"workspace": "discovery"}`.

---

## Ticket 9.6: Workspace Layout + Contextual UI

### Overview
Connect the frontend React components to the new workspace-aware Zustand store (from Ticket 9.5). Pass the active tab down to the `AdvisoryFeed` and `CommandCenter` so they display the correct thread and send messages to the correct backend agent. Implement contextual UI changes, such as hiding the CV upload button in the Discovery workspace.

### Implementation Steps

1. **[Update Component Props]**:
   - Next.js page `frontend/src/app/page.tsx` already has an `activeTab` state (`"discovery" | "profile"`).
   - Pass this state as a prop to both child components:
     ```tsx
     <AdvisoryFeed workspace={activeTab} />
     <CommandCenter workspace={activeTab} />
     ```
   - Update `useEffect` in `page.tsx` to prefetch both histories on mount:
     ```tsx
     useEffect(() => {
       setIsMounted(true);
       fetchHistory("discovery");
       fetchHistory("profile");
       fetchDeck();
     }, [fetchHistory, fetchDeck]);
     ```

2. **[Adapt `frontend/src/components/AdvisoryFeed.tsx`]**:
   - Accept the new prop: `export default function AdvisoryFeed({ workspace }: { workspace: "discovery" | "profile" })`.
   - Update the store selector to use the specific thread:
     ```tsx
     const messages = useChatStore((state) => state.threads[workspace]);
     const isPending = useChatStore((state) => state.isPending[workspace]);
     ```

3. **[Adapt `frontend/src/components/CommandCenter.tsx`]**:
   - Accept the new prop: `export default function CommandCenter({ workspace }: { workspace: "discovery" | "profile" })`.
   - Update `handleSend` to include the workspace:
     ```tsx
     const handleSend = () => {
       if (!inputText.trim() || isPending) return;
       sendMessage(inputText, workspace);
       setInputText("");
     };
     ```
   - Select the contextual pending state: `const isPending = useChatStore((state) => state.isPending[workspace]);`.
   - **Contextual UI — Placeholder Text**:
     Change the input `placeholder` dynamically based on the workspace:
     - Profile: `"Discuss your background or upload a CV..."`
     - Discovery: `"Ask Navigator to refine search..."`
   - **Contextual UI — Attach CV Button**:
     Only render the `<button>` and `<input type="file">` elements if `workspace === "profile"`. Do not render them in the Discovery workspace, as the Discovery agent does not handle CVs. Add conditional rendering `{"{"}workspace === "profile" && ( ... ){"}"}` around the attachment wrapper.

4. **[Adapt component tests]**:
   - If there are explicit tests for `AdvisoryFeed` or `CommandCenter`, update their renders to pass `workspace="discovery"` and update mocks accordingly.

### Explicit Constraints & Warnings
- Ensure the `useChatStore` selectors correctly target `state.threads[workspace]` rather than destructuring the entire `ChatState` root. This optimizes re-renders so the user doesn't experience unnecessary lag when the *other* workspace is updating.
- The `uploadCV` store method does not need a `workspace` parameter since it's hardcoded to the profile workspace (per Ticket 9.5).

### Acceptance Criteria
- [Automated] `npm run build` succeeds cleanly.
- [Automated] All frontend tests pass.
- [Manual] Run the app. Send a message in "Discovery". Switch to "Profile" — the message list should be empty (or show previous profile history). The input placeholder should change.
- [Manual] In "Discovery", the paperclip Attach icon is **hidden**. In "Profile", the paperclip icon is **visible** and works.



## Ticket 9.7: Update Project Documentation (AGENTS.md)

### Overview
With the transition from a monolithic agent architecture to Contextual Workspaces (isolated `discovery` and `profile` graphs), the central project documentation in `documents/AGENTS.md` is now outdated. This ticket updates the developer manual to reflect the new boundaries, mitigating future context poisoning for AI contributors.

### Implementation Steps

1. **[Update Codebase Map — `documents/AGENTS.md`]**:
   Locate the `### Backend (`app/`)` section and update the Agent bullet point.
   - Replace the single `app/agent/` entry with the new workspace sub-packages:
     - `app/agent/discovery/` (Discovery Agent: graph, state)
     - `app/agent/profile/` (Profile Agent: graph, state, nodes)
     - `app/agent/main/` and `app/agent/onboarding/` (Legacy/Implementation nodes)

2. **[Update "How to Modify the Agent" Workflow — `documents/AGENTS.md`]**:
   Locate the `### How to Modify the Agent` section. Rewrite it to account for the dual-graph architecture:
   - **Flow**: Specify that there are now two graphs: `app/agent/discovery/graph.py` and `app/agent/profile/graph.py`.
   - **Logic**: Specify that nodes are currently located in `app/agent/main/nodes.py` (for discovery) and `app/agent/onboarding/nodes.py` (for profile).
   - **State**: Explain that state schemas are separated into `app/agent/discovery/state.py` and `app/agent/profile/state.py`.

### Explicit Constraints & Warnings
- **Accuracy is Critical**: This document is aggressively read by AI personas. If the map explicitly states `app/agent/graph.py` instead of the new modular paths, the AI will try to patch non-existent files in future sprints.

### Acceptance Criteria
- [Manual] Review `documents/AGENTS.md` and verify "How to Modify the Agent" instructs developers/AIs to look in the newly created `discovery/` and `profile/` directories.
- [Manual] Verify the monolithic file references (`app/agent/graph.py`, `app/agent/state.py`) have been entirely removed.
