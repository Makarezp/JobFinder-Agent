# AI Scraper Bot

A production-ready AI Chatbot with FastAPI, LangGraph, and HTMX, capable of scraping websites and searching for jobs.

## Features
-   **Web Scraping**: Extract content from websites using `crawl4ai`.
-   **Job Search**: Search for jobs on LinkedIn, Indeed, Glassdoor, and ZipRecruiter using `python-jobspy`.
-   **Agentic Workflow**: Uses LangGraph for orchestrating complex tasks.

## Setup & Installation

This project uses `pyproject.toml` for dependency management. It is crucial to install dependencies correctly to avoid import errors.

### 1. Create a Virtual Environment (Optional but Recommended)
If you don't already have a `.venv`, create one:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install Dependencies
**CRITICAL:** Install the project in editable mode. This ensures all dependencies listed in `pyproject.toml` are installed into your active virtual environment.

```bash
# Make sure your virtual environment is activated!
# You should see (.venv) in your terminal prompt.

pip install -e .
```

If you encounter issues, you can try forcing a reinstall:
```bash
pip install --force-reinstall -e .
```

## Running the Application

Start the FastAPI server:
```bash
uvicorn app.main:app --reload
```

## Development

### Linting & Formatting

This project uses **Ruff** for fast linting and formatting, and **Pre-commit** to enforce quality checks before every commit.

1.  **Install Development Dependencies**:
    ```bash
    pip install -e ".[dev]"
    ```

2.  **Install Pre-commit Hooks**:
    ```bash
    pre-commit install
    ```
    This ensures that linting runs automatically when you `git commit`.

3.  **Run Checks Manually**:
    To check for errors:
    ```bash
    ruff check .
    ```
    To auto-fix errors:
    ```bash
    ruff check --fix .
    ```
    To format code:
    ```bash
    ruff format .
    ```

### Type Checking

This project enforces strict type checking using **Mypy**.

1.  **Run Type Checks**:
    ```bash
    mypy .
    ```

2.  **Guidelines for AI Agents & Developers**:
    -   **Strict Typing**: All new functions and methods **MUST** have type hints for arguments and return values.
    -   **No `Any`**: Avoid using `Any` unless absolutely necessary.
    -   **Pydantic Models**: Use Pydantic models for data validation and schema definitions.
    -   **TypedDict**: When using `TypedDict`, ensure keys are string literals or use `Final` constants to avoid Mypy errors.
    -   **Ignore Comments**: Use `# type: ignore` sparingly and only when a valid reason exists (e.g., library constraints).
