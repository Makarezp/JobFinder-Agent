# AGENTS.md - The AI Manual

## 1. Quick Links
- **Tech Stack & Architecture**: [architecture.md](architecture.md)
- **Business Logic & Glossary**: [domain.md](domain.md)
- **Coding Rules**: [CONVENTIONS.md](CONVENTIONS.md)

## 2. Codebase Map
- **Logic**: `app/agent/` (Graph, Nodes, State).
- **Tools**: `app/tools/` (Adzuna, Scrapers).
- **API**: `app/api/` (Routes).
- **Config**: `app/core/config.py` (Pydantic Settings).
- **Tests**: `tests/` (Unit & Integration).

## 3. Workflows

### How to Add a New Tool
1.  **Create File**: Add `app/tools/my_new_tool.py`.
2.  **Define Args**: Create a Pydantic model `MyToolArgs` with `Annotated` validators if input is flexible.
3.  **Implement**: Write the `@tool` decorated function.
    - **CRITICAL**: Return a `str` on error, do NOT raise exceptions.
4.  **Register**: Import in `app/agent/nodes.py` and add to `tools` list.

### How to Modify the Agent
1.  **Flow**: Edit `app/agent/graph.py` to change edges or conditional logic (`route_tools`).
2.  **Logic**: Edit `app/agent/nodes.py` to change prompt construction or Tool invocation.
3.  **State**: Edit `app/agent/state.py` if you need to store new data across steps.

### How to Run Tests
- **Unit**: `./.venv/bin/pytest tests/unit`
- **Integration**: `./.venv/bin/pytest tests/integration` (Requires `.env` with API keys).
