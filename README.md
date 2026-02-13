# CVviewer (AI Scraper Bot)

**"The Tinder for Jobs" Agent** - An AI companion that finds, filters, and recommends jobs based on your actual preferences.

## 🚀 Quick Start

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
    # IMPORTANT: Always activate the virtual environment first!
    source .venv/bin/activate
    uvicorn app.main:app --reload
    ```
    Visit `http://localhost:8000` to chat.

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

- **Lint**: `ruff check .`
- **Format**: `ruff format .`
- **Type Check**: `mypy .`
- **Test**: `./.venv/bin/pytest`

## 🤝 Committing

This project uses **pre-commit** hooks to ensure quality. When you run `git commit`, it will automatically run:
- **Ruff** (Linting & Formatting)
- **Mypy** (Type Checking)

### Commit Conventions
Keep it simple, **lowercase**, and **short**:
- `feat: ...`
- `fix: ...`
- `docs: ...`
- `refactor: ...`

## Status
**Phase 1: The Interactive Headhunter**
- Active: Adzuna Search, Gemini Agent, HTMX UI.
- Next: SQLite Persistence, Cron Jobs.
