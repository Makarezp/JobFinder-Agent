# Backend Architecture Overview

## Purpose
This document provides a high-level technical overview of the `CVviewer` (Agentic Job Companion) backend. It serves as an entry point for AI agents and developers to understand the system's structure, components, and data flow.

## Technology Stack
- **Language**: Python 3.11+
- **Web Framework**: FastAPI (Async)
- **Agent Framework**: LangGraph (Orchestration & State Management)
- **LLM Integration**: LangChain + Google Gemini (`gemini-flash-latest`)
- **Browser Automation**: Crawl4AI (Headless Scraping)
- **Frontend**: HTMX + Jinja2 (Server-Side Rendering, minimal JS) using Tailwind CSS (via CDN/static) or similar.
- **Database (Planned)**: SQLite + SQLModel (Async)

## System Architecture

### 1. The Core Application (`app/main.py`)
- **Entry Point**: Initializes the `FastAPI` application.
- **Middleware**: Handles CORS, Static Files, Templates.
- **Router**: Includes API routes from `app/api/`.

### 2. The Agent Brain (`app/agent/`)
- **Graph (`graph.py`)**: Defines the LangGraph workflow (`StateGraph`).
    - **Persistence**: Uses `MemorySaver` to maintain conversation history across requests.
    - **Routing (`route_tools`)**: Conditional logic to switch between `chatbot` and `tools` nodes.
- **Nodes (`nodes.py`)**: Implementation of graph nodes.
    - `chatbot`: Invokes the LLM with tool definitions.
    - `tool_node`: Executes tool calls.
- **State (`state.py`)**: TypedDict defining the agent's shared memory (`messages`, `cv_text`, `scraped_content`).
- **Prompts (`prompts/agent_prompts.py`)**: Stores the `SYSTEM_PROMPT` and other instructional text for the LLM.
- **Schemas (`schemas.py`)**: Pydantic models (e.g., `AgentResponse`, `JobListing`) for structured output parsing.

### 3. Tools Capability (`app/tools/`)
- **Adzuna Scraper (`adzuna.py`)**: Uses `Crawl4AI` to scrape job listings (Phase 1 focus).
- **Adzuna API (`adzuna_api.py`)**: Official API integration (fallback/alternative).
- **General Scraper (`scraper.py`)**: Generic web page text extraction for analysis.

### 4. Configuration (`app/core/`)
- **Settings (`config.py`)**: Manages environment variables using Pydantic Settings (`.env`).
    - Keys: `GEMINI_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`.

## Data Flow
1.  **User Request**: HTML interaction (HTMX) or API call triggers a route in `app/api/routes.py`.
2.  **Route Handler**:
    - Instantiates or retrieves the `graph`.
    - Invokes `graph.invoke` or `graph.stream` with the initial state (user message + optional `cv_text`).
3.  **Agent Execution**:
    - **Chatbot Node**: LLM processes input using `SYSTEM_PROMPT` and `cv_text` (if available), decides to call a tool or reply.
    - **Router**: Directs flow based on LLM output.
    - **Tool Node**: Executes the requested tool (e.g., `scrape_website`, `adzuna_search`).
4.  **Response**:
    - The LLM streams back a structured response (validated by `AgentResponse` schema).
    - Final answer is returned to the user (JSON or rendered HTML fragment).

## Current Development Phase (Phase 1: The Interactive Headhunter)
- **Focus**: Building a conversational agent that acts as a real-time scout.
- **Key Changes**:
    - Enhancing LangGraph agent to handle complex queries.
    - Improving `adzuna.py` tool for better compatibility with LLM (structured output).
    - Refining the Chat UI (HTMX) for better interaction loop.
