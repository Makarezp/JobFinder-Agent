# Memory System Architecture (v2)

## 1. Overview
The Memory System transforms the agent from a stateless bot into a **long-term career companion**. It enables the agent to:
1.  **Remember Identity:** Name, Role, and CV details.
2.  **Enforce Preferences:** Apply persistent constraints (e.g., "Remote only", "No Java") to every job search.
3.  **Self-Correction:** Allow users to update their profile and preferences through natural language.

---

## 2. Storage Backend

We use **LangGraph's `InMemoryStore`** — a key-value store that lives in the process memory. This was chosen for its tight integration with LangGraph's tool injection system (`InjectedStore`), eliminating the need for a separate database layer.

> **Note:** Data is ephemeral and resets on server restart. This is intentional for the current phase. A persistent backend (e.g., Redis, PostgreSQL via LangGraph's store interface) can be swapped in later without changing the tool or node code.

### Namespace Convention
Data is organized by `(user_id, collection)` tuples:

| Namespace              | Key      | Description                       |
| :--------------------- | :------- | :-------------------------------- |
| `(user_id, "profile")` | `"data"` | Singleton user profile.           |
| `(user_id, "preferences")` | `<key>` | One entry per preference (e.g., `"location"`, `"salary"`). |

---

## 3. Data Models (Pydantic)

All data read from and written to the store is validated through Pydantic models defined in `app/agent/memory_schema.py`.

### 3.1 `UserProfile`
A singleton model storing the user's core identity.

| Field     | Type           | Default | Description                                     |
| :-------- | :------------- | :------ | :---------------------------------------------- |
| `id`      | `int`          | `1`     | Primary identifier (always 1 for now).          |
| `name`    | `str \| None`  | `None`  | User's preferred name.                          |
| `role`    | `str \| None`  | `None`  | Target job title (e.g., "Senior Python Engineer"). |
| `cv_text` | `str \| None`  | `None`  | Raw text extracted from their uploaded CV.       |

### 3.2 `Preference`
A model for flexible job-search constraints.

| Field      | Type                      | Default  | Description                                     |
| :--------- | :------------------------ | :------- | :---------------------------------------------- |
| `key`      | `str`                     | Required | The setting name (e.g., "location", "salary").  |
| `value`    | `Any`                     | Required | The value (string, number, list, or boolean).   |
| `category` | `Literal["hard", "soft"]` | `"soft"` | `"hard"` = strict filter, `"soft"` = nice to have. |

---

## 4. Agent Integration

### 4.1 Tools (`app/tools/memory.py`)
The agent manages memory via three tools. Each receives the `store` automatically through LangGraph's `InjectedStore` mechanism — no global state.

1.  **`update_my_profile(name, role)`** — Updates user identity fields.
    - Usage: "My name is Alice and I'm a Senior dev."
2.  **`save_preference(key, value, category)`** — Saves a search constraint.
    - Usage: "I only want remote jobs." → `save_preference("location", "Remote", "hard")`
3.  **`delete_preference(key)`** — Removes a preference.
    - Usage: "Actually, I'm open to relocation." → `delete_preference("location")`

All tools include error handling with structured logging. On failure, a user-friendly error message is returned to the LLM.

### 4.2 Context Injection (`fetch_profile` node)
Before the `chatbot` node runs, a `fetch_profile` node reads the store and injects data into `AgentState`:
- `state["user_profile"]`: Dict of profile fields (from `UserProfile.model_dump()`).
- `state["preferences"]`: Dict of active preferences (from `Preference.model_dump()`).
- `state["cv_text"]`: Re-hydrated CV content from the profile, if present.

The store is injected into `fetch_profile` via `functools.partial` in the graph definition.

### 4.3 System Prompt
The system prompt is dynamically formatted with user context:
> "You are helping **{name}**, a **{role}**."
>
> **User Preferences (Constraints):**
> - location: Remote
> - salary: 120k

---

## 5. Dependency Injection

The store is created once in `app/agent/graph.py` and shared across the application via FastAPI's `Depends` system:

```
graph.py (creates InMemoryStore)
    ├── graph.compile(store=store)    → tools get store via InjectedStore
    ├── partial(fetch_profile, store) → node gets store via partial
    └── dependencies.py              → routes/services get store via Depends
```

| Consumer           | Injection Method                        |
| :----------------- | :-------------------------------------- |
| Memory tools       | `Annotated[BaseStore, InjectedStore]`   |
| `fetch_profile`    | `functools.partial(fetch_profile, store=store)` |
| Routes / Services  | `Depends(get_store)` from `dependencies.py` |

---

## 6. User Interface

### 6.1 Profile Page (`/profile`)
A read-only view of the agent's memory, visualizing:
- **Identity Card**: Name, current role, and confirmation of CV upload status.
- **Knowledge Base**: Active preferences categorized by "Hard Constraints" (Must-haves) and "Soft Preferences" (Nice-to-haves).

This ensures transparency — the user can always see exactly what the agent "knows" and "believes".

---

## 7. Verification
- **Unit Tests** (`tests/unit/test_memory_tools.py`):
    - Tests CRUD operations for profile and preferences using `InMemoryStore`.
    - Error-path tests using `FailingPutStore` / `FailingDeleteStore` subclasses.
- **Integration Tests** (`tests/integration/test_profile_routes.py`):
    - Verifies the `/profile` endpoint renders correctly with seeded data.
    - Uses FastAPI dependency overrides with `InMemoryStore`.
- **Manual Inspection**:
    - Visit `http://localhost:8000/profile` to inspect the agent's current memory state.
