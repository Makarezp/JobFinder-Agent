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

