# CVviewer (AI Scraper Bot)

**"The Tinder for Jobs" Agent** - An AI companion that finds, filters, and recommends jobs based on your actual preferences.

## 🚀 Quick Start

### Backend (FastAPI)

1.  **Clone & Install**:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e ".[dev]"
    pre-commit install
    ```

2.  **Configure**:
    - Copy `.env.example` to `.env`
    - Add your `GEMINI_API_KEY` and `ADZUNA_APP_ID`/`ADZUNA_APP_KEY`.

3.  **Run**:
    ```bash
    source .venv/bin/activate
    uvicorn app.main:app --reload
    ```
    Backend API available at `http://localhost:8000`.

### Frontend (Next.js)

1.  **Install**:
    ```bash
    cd frontend
    npm install
    ```

2.  **Run**:
    ```bash
    npm run dev
    ```
    Visit `http://localhost:3000` to use the app.

> **Note**: Both backend and frontend must be running concurrently. The Next.js dev server proxies all `/api/*` requests to the FastAPI backend on port 8000.

## 📚 Documentation

Detailed documentation is available in the `documents/` directory:

| Document | Audience | Description |
| :--- | :--- | :--- |
| **[AGENTS.md](documents/AGENTS.md)** | 🤖 **AI Agents** | **READ THIS FIRST**. Project internal map, workflows, and "How-To" guides. |
| **[CONVENTIONS.md](documents/CONVENTIONS.md)** | 🤖 & 👨‍💻 | Strict rules for Typing, Error Handling, and Testing. |
| **[domain.md](documents/domain.md)** | 🧠 **Context** | Business logic, glossary, and the "Soul" of the project. |
| **[architecture.md](documents/architecture.md)** | 🏗️ **Architects** | Technical stack, data flow, and component diagrams. |
| **[DESIGN_PRINCIPLES.md](documents/DESIGN_PRINCIPLES.md)** | 📐 **Engineers** | SOLID, Clean Architecture, and abstract system rules. |

## 🛠️ Development

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

## 🤝 Committing

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
│   └── tools/            # Adzuna API, Scraper
├── frontend/             # Next.js frontend
│   └── src/
│       ├── app/          # Next.js App Router (pages, layout)
│       └── core/         # Business logic boundary
│           ├── api/      # API client functions
│           ├── store/    # Zustand state management
│           └── types/    # Shared TypeScript types
├── tests/                # Python backend tests
└── documents/            # Project documentation
```

## Status
**Phase 2: React Native Migration**
- Sprint 0 (In Progress): Next.js scaffold, Backend JSON API refactor, Zustand store.
- Sprint 1: Stitch design system integration.
- Sprint 2: Full agent chat UI.
- Sprint 3: Interactivity loop (Pass/Pursue feedback).
