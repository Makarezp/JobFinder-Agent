# Backend Architecture Overview

## Purpose
High-level technical overview of the CVviewer backend for AI agents and developers.

## Technology Stack
- **Language**: Python 3.11+
- **Web Framework**: FastAPI (Async)
- **Agent Framework**: LangGraph (Orchestration & State Management)
- **LLM**: LangChain + Google Gemini (`gemini-flash-latest`)
- **Browser Automation**: Crawl4AI (Headless Scraping)
- **Frontend**: HTMX + Jinja2 (SSR) + Tailwind CSS
- **Logging**: `python-json-logger` (Structured JSON)

## Component Map

### Ingress Layer (`app/api/`)
- **`routes.py`** — HTTP endpoints (`/chat`, `/upload-cv`, `/profile`). No business logic.
- **`dependencies.py`** — FastAPI DI wiring: `get_chat_service()` builds `ChatService(graph=graph)`.
- **`middleware.py`** — `RequestIdMiddleware`: assigns `request_id` (ContextVar), logs request timing, sets `X-Request-ID` header.

### Service Layer (`app/services/`)
- **`chat_service.py`** — Orchestrates graph invocation. Receives `graph` via constructor (DI). Handles PDF parsing, result extraction, and injects `request_id` into LangGraph config metadata for LangSmith correlation.

### Agent Layer (`app/agent/`)
- **`graph.py`** — `StateGraph` definition with `MemorySaver` persistence.
- **`nodes.py`** — `chatbot` (LLM invocation) and `tool_node` (tool execution).
- **`state.py`** — `AgentState` TypedDict (`messages`, `cv_text`, `scraped_content`).
- **`schemas.py`** — `AgentResponse`, `JobListing` (structured output).
- **`prompts/agent_prompts.py`** — System prompt.

### Tools (`app/tools/`)
- **`adzuna_api.py`** — Adzuna REST API search (official API).
- **`scraper.py`** — Generic web page text extraction via Crawl4AI.

### Infrastructure (`app/core/`)
- **`config.py`** — `Settings` (Pydantic Settings, loads `.env`).
- **`logging.py`** — `setup_logging()`, `request_id_var` (ContextVar), `RequestIdFilter`, `log_timing()`.

## Data Flow
1. **HTTP Request** → `RequestIdMiddleware` assigns `request_id` ContextVar
2. **Route** → FastAPI `Depends()` injects `ChatService` with graph
3. **ChatService** → builds LangGraph config with `metadata.request_id` and `tags`, invokes graph
4. **Agent Graph** → LLM → tool calls → structured `AgentResponse`
5. **Response** → Jinja2 template renders HTML fragment (HTMX swap)

## Observability
- **Structured JSON logs** with `request_id` correlation across all layers
- **Timing** via `log_timing()` on graph invocations and API calls
- **LangSmith** traces tagged with `request_id` via config metadata
