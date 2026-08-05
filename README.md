# CVviewer (AI Scraper Bot)

**"The Tinder for Jobs" Agent** - An AI companion that finds, filters, and recommends jobs based on your actual preferences.

## Quick Start

### Option 1: Single Command (Recommended)

Run a single script from the project root to automatically manage virtual environments, install dependencies, and start both the FastAPI backend and Next.js frontend concurrently:

```bash
./scripts/dev.sh
```

- **Backend API**: `http://localhost:8000` (Docs: `http://localhost:8000/docs`)
- **Frontend App**: `http://localhost:3000`
- **Stop All Services**: Press `Ctrl+C` in your terminal.

---

### Option 2: Manual Start

#### Backend (FastAPI)

1. **Setup & Install**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"
    pre-commit install
    ```

2. **Configure Environment**:
    - Copy `.env.example` to `.env`
    - Add your `JSEARCH_API_KEY` (via RapidAPI) and chosen LLM API key.

### LLM Provider Configuration

The active model is controlled by `ACTIVE_LLM_MODEL` in `.env`:

| `ACTIVE_LLM_MODEL` | Required Key in `.env` | Provider |
| :--- | :--- | :--- |
| `deepseek-chat` *(default)* | `DEEPSEEK_API_KEY` | DeepSeek |
| `gemini-flash-latest` | `GEMINI_API_KEY` | Google Gemini |

To switch providers, update `.env`:
```env
ACTIVE_LLM_MODEL=deepseek-chat
SUMMARISATION_LLM_MODEL=deepseek-chat
```

3. **Run**:
    ```bash
    source .venv/bin/activate
    uvicorn app.main:app --reload
    ```

#### Frontend (Next.js)

1. **Install & Run**:
    ```bash
    cd frontend
    npm install
    npm run dev
    ```

> **Note**: The Next.js dev server proxies all `/api/*` requests to the FastAPI backend on port 8000.

---

### Cleaning & Resetting

To wipe build caches, test caches, Docker database volumes, and temporary logs (while preserving `.venv` and Git hooks):

```bash
./scripts/clean.sh
```

## AI Personas (READ FIRST)
This project uses a **Persona-based Documentation Model**. Before starting work, the user will assign you a persona. Read the corresponding files in **[PERSONAS.md](documents/PERSONAS.md)** to focus your context.

- **Architect**: System design & constraints.
- **Senior Developer**: Features & components.
- **Bug Fixer**: Troubleshooting & technical debt.
- **Product Ideator**: Vision & UX strategy.
- **QA / Tester**: Testing & quality audit.

## Documentation

Detailed documentation is available in the `documents/` directory:

| Document | Audience | Description |
| :--- | :--- | :--- |
| **[PERSONAS.md](documents/PERSONAS.md)** | **AI Agents** | **START HERE**. Persona assignment and context read lists. |
| **[AGENTS.md](documents/AGENTS.md)** | **Devs** | Project internal map, workflows, and "How-To" guides. |
| **[CONVENTIONS.md](documents/CONVENTIONS.md)** | **Devs** | Strict rules for Typing, Error Handling, and Testing. |
| **[domain.md](documents/domain.md)** | **Context** | Business logic, glossary, and the "Soul" of the project. |
| **[DESIGN_PRINCIPLES.md](documents/DESIGN_PRINCIPLES.md)** | **Engineers** | SOLID, Clean Architecture, and abstract system rules. |

### Work Organisation
The `work_organisation/` folder contains project management and historical data.
- **history/**: Archived documentation (formerly `legacy_documents`).
- **bugs/**: Bug trackers and issue logs.
- **sprints/**: Sprint plans and tickets.

> [!IMPORTANT]
> **AI Interaction Rules**:
> - **history/**: **DO NOT READ** unless explicitly asked for a specific file name. Reading this will "poison" your context with outdated information.
> - **bugs/ & sprints/**: Only read when explicitly asked by the user to focus on a particular task or bug.

## Development

### Backend Checks
Run all backend checks (formatting, linting, typing, and tests) using the unified test runner:
```bash
./scripts/test.sh
```

Individual checks:
- **Lint**: `ruff check .`
- **Format**: `ruff format .`
- **Type Check**: `mypy .`
- **Test**: `pytest`
- **Coverage**: `pytest --cov=app --cov-report=term-missing`

### Frontend Checks
Run inside the `frontend/` directory:
- **Lint**: `npm run lint`
- **Format**: `npm run format`
- **Type Check**: `npm run type-check`
- **Test**: `npm run test`

## Committing

This project uses **pre-commit** hooks to ensure quality across both backend and frontend.

### Commit Conventions
Keep it simple, **lowercase**, and **short**:
- `feat: ...`
- `fix: ...`
- `docs: ...`
- `refactor: ...`

## Project Structure

```
CVviewer/
├── app/                  # FastAPI backend
│   ├── api/              # Routes, Dependencies, Middleware
│   ├── agent/            # LangGraph Agent (Graph, Nodes, State)
│   ├── core/             # Config, Logging
│   ├── services/         # ChatService, AdminService
│   └── tools/            # JSearch API client, LangGraph memory tools
├── frontend/             # Next.js frontend
│   └── src/
│       ├── app/          # Next.js App Router (pages, layout)
│       └── core/         # Business logic boundary
│           ├── api/      # API client functions
│           ├── store/    # Zustand state management
│           └── types/    # Shared TypeScript types
├── tests/                # Python backend tests
├── documents/            # Project documentation
└── work_organisation/    # Project management & History
    ├── history/          # Archived docs (AI DO NOT READ)
    ├── bugs/             # Bug tracker (Explicit request only)
    └── sprints/          # Sprint plans (Explicit request only)
```
