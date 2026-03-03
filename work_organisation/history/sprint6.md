# Sprint 6: JSearch Migration & Architecture Simplification

## Goal
Replace the multi-hop job discovery pipeline (Adzuna + Crawl4AI) with a single-pass API query using JSearch. This migration consolidates data fetching, removes the fragile scraping step, protects the LLM context window, and significantly simplifies the LangGraph state machine.

---

## Schema Mapping (JSearch -> Internal JobListing)
The RapidAPI JSearch `GET /search` endpoint returns rich data. We will map it as follows to our backend `JobListing` payload (which the frontend `Job` interface expects):

| `id` | `job_id` | Stable identifier |
| `title` | `job_title` | |
| `company` | `employer_name` | |
| `location` | `job_city`, `job_state`, `job_country` | Combine into a string (e.g., "Chicago, IL, US") |
| `company` | `employer_name` | |
| `location` | `job_city`, `job_state`, `job_country` | Combine into a string (e.g., "Chicago, IL, US") |
| `salary` | `job_min_salary`, `job_max_salary`, `job_salary_period` | Format as "£X - £Y per YEAR" or similar. Fallback to `job_salary`. |
| `description` | `job_description` (Snippet) | Slice the first 300 chars for the feed preview. |
| `full_description`| `job_description` (Full) | The complete text required by the Agent to evaluate fit. Defensive: Cap at 10,000 characters to prevent context window overflow. |
| `apply_link` | `job_apply_link` | Fallback to `apply_options[0].apply_link`. |

## Defensive Architecture Considerations
- **Context Window Protection**: The `job_description` can be extraordinarily long. If left unbounded, 10 jobs could easily consume 100k+ tokens, degrading LLM reasoning and increasing latency. We will enforce a strict truncation limit (e.g., 10,000 chars per description) in the tool layer before it reaches the Graph State.
- **Pagination Safety**: By default, the tool must enforce `page=1` and `num_pages=1`. The LLM agent should not be permitted to fetch more than 10 jobs at a time to prevent state ballooning.
- **Graph Simplification**: The `Scrape` / `Inspect` node and tool (Crawl4AI) must be aggressively completely removed. The state schema (`JobSpecialistState` / `AgentState`) must be collapsed to only have `search_results`.
- **Fast-fail Infrastructure**: The JSearch API uses RapidAPI (Rate limits, 50x errors). The tool wrapper must catch `httpx` exceptions and return string error descriptions so the agent graph can gracefully fail or retry, adhering to the project's strict `CONVENTIONS.md`.

---

## Ticket 6.1: Backend — JSearch API Tool Integration ✅ DONE

### Overview
Implement the `jsearch_api_search` tool to fetch real-time job listings in a single HTTP request, mapping the RapidAPI response to the internal `JobListing` schema. To protect the LLM context window during Phase 1, descriptions will be strictly truncated.

### Implementation Steps
1. **Infrastructure**: Add `JSEARCH_API_KEY=841d8deb12mshec88cb417ee4eedp1ea6a7jsn594bf90cf4a1` to the `Settings` model in `app/core/config.py` and to the `.env` file.
2. **Tool Input Schema Refactor**: Define `JSearchApiArgs(BaseModel)` in `app/tools/jsearch_api.py`. The LLM arguments change significantly because JSearch uses a Google-like search paradigm:
   - Replace `what` and `where` string parameters with a single `query: str` parameter (e.g., "software engineer in london").
   - Replace `max_days_old: int` with `date_posted: str` (Enum: `"all"`, `"today"`, `"3days"`, `"week"`, `"month"`).
   - Replace individual boolean flags (`full_time`, `part_time`, `contract`) with an `employment_types: str` parameter (Comma separated list of `FULLTIME`, `CONTRACTOR`, `PARTTIME`, `INTERN`).
   - Add `remote_only: bool` (maps to JSearch `work_from_home`).
   - Add `page: int = Field(default=1)` parameter to allow the agent to paginate if initial results do not meet salary/fit requirements.
   - *CRITICAL*: Remove `salary_min` and `sort_by`. The JSearch `/search` endpoint natively sorts by relevance (Google's algorithm) and does not natively support pre-filtering by salary minimums via query params.
3. **Tool Creation**: Create `app/tools/jsearch_api.py`. Define and export the `@tool("jsearch_api_search", args_schema=JSearchApiArgs)` `jsearch_api_search`.
   - Explicitly use `httpx.Client()` to send a `GET` request to `https://rapidapi.com/letscrape-6zs-bbpfn7rc9/api/jsearch/search` (or the exact OpenWeb Ninja URL: `https://api.openwebninja.com/jsearch/search`).
   - Include the API key in the headers as required by the documentation (`x-api-key`).
4. **Schema Mapping (Return Value)**: The tool must parse the response `data` array and map it to a list of `JobListing` dictionaries.
   - `id` -> `job_id`
   - `title` -> `job_title`
   - `company` -> `employer_name`
   - `location` -> combine `job_city`, `job_state`, `job_country` (e.g., "Chicago, IL, US")
   - `salary` -> format using `job_min_salary`, `job_max_salary`, `job_salary_period`. Fallback to `job_salary` or `None`.
   - `description` -> slice the first 300 characters of `job_description`.
   - `full_description` -> the raw `job_description`. **Crucially, slice this to a maximum of 1,000 characters.**
   - `apply_link` -> `job_apply_link`.

### Explicit Constraints & Warnings
- **Context Protection**: You MUST slice `full_description` to exactly **1,000 characters**. Failure to do so will cause catastrophic context window overflow.
- **Pagination Safety**: Force `num_pages=1` in the RapidAPI request payload. Allow the agent to control `page` via the tool input, but do not allow bulk fetching of multiple pages in a single call.
- **Error Handling**: Catch `httpx.RequestError` and `httpx.HTTPStatusError`. Do NOT raise exceptions. Log them and return a descriptive tool error string.

### Acceptance Criteria
- [Automated] Create `tests/unit/test_jsearch_api.py`. Mock `httpx.Client.get` to return a sample RapidAPI JSearch response. Assert the `jsearch_api_search` tool correctly translates this into a list of valid `JobListing` dictionary objects, properly concatenating location, handling missing salary fields, and enforcing the 1000-character truncation on `full_description`.
- [Manual] Run the tool locally. It successfully returns jobs and the `full_description` is cleanly truncated at 1000 chars.

---

## Ticket 6.2: Backend — Schema Simplification (JobListing) ✅ DONE

### Overview
With JSearch providing sufficient description data immediately, the separation between `JobSummary` and `JobDetail` is obsolete. We will simplify the Pydantic schemas to utilize a single `JobListing` source of truth.

### Implementation Steps
1. **Schema Refactor**: Modify `app/agent/schemas.py`.
   - Delete the `JobSummary` and `JobDetail` Pydantic classes entirely.
   - Modify the `JobListing` class to act as the single source of truth. Ensure it includes `full_description: str | None = Field(None, ...)`.
   - Clean up `JobSpecialistInput`. Remove `mode`, `url`, and `summary_context`. It ONLY needs the search parameters now (e.g., `query`, `location`, `page`).
2. **State Refactor for Subgraph**: Modify `app/agent/job_search/state.py`.
   - Update `JobSpecialistState` to ONLY contain `input: JobSpecialistInput` and `search_results: list[JobListing] | None`.
   - Delete the `inspect_result` field.
3. **Frontend Sync**: Verify `frontend/src/core/types/api.ts` matches this `JobListing` shape (it already has `full_description: string | null`, so ensure backend aligns).

### Explicit Constraints & Warnings
- **Backend/Frontend Contract**: Do not alter `id`, `title`, `company`, `location`, `salary`, `description`, or `apply_link` in `JobListing`. The frontend STRICTLY relies on these fields.
- **Typing Integrity**: Ensure all locations previously importing `JobSummary` (e.g., state or history parsing) are updated to expect `JobListing`.

### Acceptance Criteria
- [Automated] Update any existing test fixtures in `tests/` that constructed `JobSummary` or `JobDetail` to construct `JobListing` instead. Verify `pytest` runs correctly.

---

## Ticket 6.3: Backend — Subgraph Simplification & Routing Refactor ✅ DONE

### Overview
Instead of deleting the `job_search` subgraph, we will simplify it to act as a deterministic boundary for the new `jsearch_api_search` tool. We will also relocate infinite loop protection to the main graph router, ensuring the agent cannot spiral out of control.

### Implementation Steps
1. **Tool Replacement**: Edit `app/agent/job_search/nodes.py`.
   - Remove `adzuna_api_search` and `scrape_website` tools.
   - Import and use `jsearch_api_search`.
   - The `search_jobs` node should now call `jsearch_api_search`.
   - The `inspect_job` node is obsolete and should be deleted, as JSearch returns the descriptions immediately.
2. **Subgraph Routing Simplification**: Edit `app/agent/job_search/graph.py`.
   - Remove the `INSPECT_NODE` and the internal router.
   - The subgraph now simply routes from `START` to `SEARCH_NODE` to `END`.
3. **Main Graph Routing & Loop Protection**: Edit `app/agent/graph.py` and `app/agent/main/nodes.py`.
   - The `call_job_specialist` node in `main/nodes.py` must be maintained to pass data to the subgraph.
   - *CRITICAL*: Implement strict infinite loop protection in the `route_main` function (in `app/agent/main/nodes.py`).
   - Add a `search_attempts` counter to `AgentState` or inspect the trajectory to ensure the `job_specialist_tool` is not called more than 3 times in a single session. If the limit is reached, `route_main` MUST return `END` (or force a response to the user), completely blocking further subgraph traversal.
4. **Aggressive Deletion (Legacy Code)**:
   - Delete `app/tools/adzuna_api.py`.
   - Delete `app/tools/scraper.py`.

### Explicit Constraints & Warnings
- **Do not delete the Subgraph**: The `app/agent/job_search/` directory and its state management must remain intact to preserve the architectural boundary for Phase 2 (LLM Evaluation Node).
- **Loop Protection MUST be Routing-Level**: Do not try to solve infinite loops by returning error strings from the tool. The `route_main` function must deterministicly halt execution.

### Acceptance Criteria
- [Automated] Refactor `tests/unit/test_loop_limits.py` to verify the `search_attempts` loop protection at the `route_main` level successfully halts the agent after 3 attempts.
- [Automated] `pytest` runs without referencing the deleted Adzuna or Scraper tools.
- [Manual] Ask the bot "Find me Python jobs". The LangSmith/log trace shows a traversal into the `job_search` subgraph, a single tool call to `jsearch_api_search`, and a clean return to the main agent.

---

## Ticket 6.4: Backend — System Prompt Rewrite & Post-Migration Cleanup

### Overview
The current `SYSTEM_PROMPT` in `app/agent/main/prompts.py` contains a hardcoded multi-step "SEARCH → FILTER → INSPECT → ANALYZE → SURFACE" protocol using `mode="search"` and `mode="inspect"`. These parameters no longer exist in `JobSpecialistInput` after the 6.2 schema refactor. Additionally, the phantom `job_specialist_tool` in `tools.py` has a stale function signature and docstring from the Adzuna era, and `domain.md` still references deleted systems.

### Implementation Steps

#### Step 1: Fix `job_specialist_tool` signature and docstring (cleanup) ✅ DONE
**File**: `app/agent/main/tools.py`

The tool is a phantom tool (legitimate LangGraph pattern) — the stub exists to give the LLM a schema via `args_schema=JobSpecialistInput`, and execution is intercepted by `route_main` → `call_job_specialist`. The pattern is correct, but the Python function signature still lists old Adzuna parameters (`mode`, `location`, `country`, `salary_min`, `url`, etc.) and the docstring describes the deleted `mode="inspect"` flow.

Replace the `job_specialist_tool` function. The signature must match `JobSpecialistInput`:

```python
@tool(args_schema=JobSpecialistInput)
def job_specialist_tool(
    query: str,
    date_posted: str = "all",
    employment_types: str | None = None,
    remote_only: bool = False,
    page: int = 1,
) -> str:
    """
    Delegates job search to the Job Specialist Agent.
    Returns a list of job listings with titles, companies, locations,
    salaries, descriptions (truncated to 1,000 characters), and apply links.
    """
    return "Job Specialist invoked."
```

Remove the `from typing import Any` import if it becomes unused after this change.

#### Step 2: Rewrite `SYSTEM_PROMPT`
**File**: `app/agent/main/prompts.py`

1. **Delete** the "Job Surfacing Protocol (MANDATORY)" section entirely.
2. **Delete** all references to `mode="search"`, `mode="inspect"`, and the SEARCH→FILTER→INSPECT→ANALYZE→SURFACE pipeline.
3. **Replace** the "JOB SEARCH INSTRUCTIONS" section with:

```
**JOB SEARCH INSTRUCTIONS:**
1.  **Analyze the User's Request & Profile:**
    *   Use the structured profile above (skills, experience, domain) to inform your search.
    *   Do NOT use generic terms like "Software Engineer" if more specific terms
        (e.g., "Android Developer", "Kotlin", "React Native") are available in the profile.

2.  **Search Jobs:**
    *   **YOU MUST** use `job_specialist_tool` to find jobs.
    *   Craft a specific Google-style query (e.g., "senior react developer in london").
    *   Use `date_posted`, `employment_types`, and `remote_only` filters when
        the user's preferences or request imply them.
    *   The tool returns job listings including a truncated description (up to 1,000
        characters). Evaluate fit based on this snippet — do not penalize a job solely
        because its description appears incomplete.

3.  **Present Results:**
    *   **YOU MUST** call the `final_answer` tool to present results.
    *   Populate `text_response` with a helpful, conversational summary.
    *   Populate `jobs` with the structured job data returned by the specialist.
    *   For each job, write a concise 2-3 sentence `description` summarizing why it
        matches the user. Ensure `apply_link` is included exactly as returned.

4.  **Handling No Results:**
    *   If a search returns no jobs, try **ONE** modified query (broader keywords,
        relaxed location, or different employment type).
    *   **STOP** after 3 total search attempts. Do NOT loop indefinitely.
    *   Call `final_answer` and explain what you tried and suggest alternatives.
```

**Keep unchanged**: USER PROFILE / ACTIVE PREFERENCES / RECENT USER FEEDBACK template variables, and MEMORY INSTRUCTIONS.

#### Step 3: Update `domain.md`
**File**: `documents/domain.md`

- **Glossary**: Remove `Adzuna` and `Crawl4AI` entries. Add `JSearch` (RapidAPI-based job search aggregator).
- **Business Rules**: Remove "Deep Scraping" section. Replace with a note that JSearch returns descriptions directly (truncated to 1,000 chars). Remove the Adzuna-specific "Remote Work" instruction.

### Explicit Constraints & Warnings
- **Do NOT change `call_job_specialist` in `graph.py`**: It correctly parses `JobSpecialistInput` from tool call args. No changes needed.
- **Do NOT change `route_main`**: Loop protection is already correct (3-attempt limit).
- **The `job_specialist_tool` function body remains a stub**: It returns a static string because execution is intercepted by the graph router. This is the intended phantom tool pattern.
- **Typing**: After changes, run `mypy --strict app/agent/main/tools.py app/agent/main/prompts.py`.

### Acceptance Criteria
- [Automated] `mypy --strict` passes on `app/agent/main/tools.py`.
- [Automated] `ruff check` and `ruff format` pass on all modified files.
- [Automated] Existing tests in `tests/` pass without modification.
- [Manual] Ask the bot "Find me Python jobs in London". Verify via logs/LangSmith that:
  - The LLM calls `job_specialist_tool` with `query=` (no `mode` argument).
  - Results are surfaced via `final_answer`.
  - No `mode="inspect"` hallucination occurs.
