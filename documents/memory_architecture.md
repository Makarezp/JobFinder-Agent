# Memory System Architecture (v1)

## 1. Overview
The Memory System transforms the agent from a stateless bot into a **long-term career companion**. It enables the agent to:
1.  **Remember Identity:** Name, Role, and CV details.
2.  **Enforce Preferences:** Apply persistent constraints (e.g., "Remote only", "No Java") to every job search.
3.  **Self-Correction:** Allow users to update their profile and preferences through natural language.

---

## 2. Data Models (SQLite)

We use a local SQLite database (`data/user_memory.db`) with two primary tables.

### 2.1 User Profile (`profile` table)
A singleton table (enforced by `id=1`) storing the user's core identity.

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | INTEGER | Primary Key, always 1. |
| `name` | TEXT | User's preferred name. |
| `role` | TEXT | Target job title (e.g., "Senior Python Engineer"). |
| `cv_text` | TEXT | Raw text extracted from their uploaded CV. |
| `updated_at` | TIMESTAMP | Last modification time. |

### 2.2 Preferences (`preferences` table)
A Key-Value store for flexible constraints.

| Field | Type | Description |
| :--- | :--- | :--- |
| `key` | TEXT | Primary Key (e.g., "location", "salary", "tech_stack"). |
| `value` | JSON | The value (string, number, or list). JSON typed for flexibility. |
| `category` | TEXT | "hard" (strict filter) or "soft" (preference). |
| `updated_at` | TIMESTAMP | Last modification time. |

---

## 3. Agent Integration

### 3.1 Tools
The agent manages memory via three dedicated tools:

1.  **`update_my_profile(name, role)`**
    - usage: "My name is Alice and I'm a Senior dev."
2.  **`save_preference(key, value, category)`**
    - usage: "I only want remote jobs." -> `save_preference("location", "remote", "hard")`
3.  **`delete_preference(key)`**
    - usage: "Actually, I'm open to relocation." -> `delete_preference("location")`

### 3.2 Context Injection (`fetch_profile` node)
Before the `chatbot` node runs, a `fetch_profile` node reads the DB and injects data into `AgentState`:
- `state["user_profile"]`: Dict of profile fields.
- `state["preferences"]`: Dict of active preferences.

### 3.3 System Prompt
The system prompt is dynamically formatted with this context:
> "You are helping **{name}**, a **{role}**."
>
> **User Preferences (Constraints):**
> - location: Remote
> - salary: 120k

---

## 4. Verification
- **Automated Tests**: `tests/verify_memory.py` validates persistence and CRUD operations.
- **Manual Inspection**: `scripts/inspect_memory.py` prints the current database state.
