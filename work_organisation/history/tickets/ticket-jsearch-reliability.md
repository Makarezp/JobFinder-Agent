### Ticket 10.1: Refactor JSearch API Integration for Reliability and Non-US Search Quality done

#### Overview
The current JSearch integration is brittle for non-US searches, specifically due to over-filtering on `employment_types` and overly restrictive `date_posted=week` defaults. This ticket removes the unreliable `employment_types` filter and re-aligns the agent's prompt to use more robust semantic querying ("semantic filtering").

#### Implementation Steps
1. **[Backend - Schema]**: Modify `app/agent/schemas.py`.
    - Remove the `employment_types` field from the `JobSpecialistInput` Pydantic model.
    - Update the `query` field description to remove the advice against combining words and instead explicitly provide a semantic filtering example: `"GOOD: 'admin assistant London', 'Android Developer contract London', 'social media coordinator UK part-time'."`
    - Change the `date_posted` field default to `"month"` and update its description so it naturally defaults to looking at recent but not overly narrow timeframes.
2. **[Backend - Tool]**: Update `app/tools/jsearch_api.py`.
    - Remove the `employment_types` argument from the `jsearch_api_search` function signature.
    - Remove the logic that adds `employment_types` to the `params` dictionary.
3. **[Backend - Graph Logic]**: Update `app/agent/job_search/nodes.py`.
    - Update the `search_jobs` node to remove `employment_types` from the dictionary passed to `jsearch_api_search.invoke()`.
4. **[AI - Agent Prompt]**: Update `app/agent/main/prompts.py`.
    - Modify the `JOB_SEARCH_INSTRUCTIONS` inside `SYSTEM_PROMPT`:
        - **Instruction 2.2**: Explicitly instruct the agent to use the format `"[Role] jobs in [Location]"` for the `query` field.
        - **Semantic Filtering**: Direct the agent to include keywords like "contract", "part-time", or "permanent" directly in the `query` string (e.g., `"Android Developer contract London"`) instead of relying on structural filters.
        - **Pagination Heuristic**: Inform the agent that since the API returns max 10 results per page, if a search returns exactly 10 items, more likely exist on the next page. It can choose to call `job_specialist_tool` again with `page=2` if it needs more variety, but within its budget of `{max_search_attempts}` total searches.
        - **Date Range**: Recommend using `date_posted='month'` by default to avoid missing high-quality roles posted just outside the 7-day window.
5. **[Backend - Unit Tests]**: Update existing tests.
    - **`tests/unit/test_agent.py`**: Update any mocks of `JobSpecialistInput` to no longer expect or use `employment_types`.
    - **`tests/unit/test_job_specialist_nodes.py`**: Assert that `search_jobs` correctly invokes the tool without the `employment_types` parameter.

#### Explicit Constraints & Warnings
- **Contract Stability**: Because `JobSpecialistInput` is the `@tool` schema, removing `employment_types` will change the LLM's tool-calling signature.
- **Location Mapping**: Ensure the `country` parameter (re-introduced in a previous step) remains mandatory and is explicitly populated by the LLM based on the location.
- **Date Posted Default**: Ensure we explicitly change the Pydantic default for `date_posted` to `"month"` in `schemas.py`. The LLM Prompt (Step 4) and Schema default MUST reflect the exact same reality to prevent developer confusion.
- **Description Truncation**: Ensure the change does not affect the existing truncation logic for `description` (300 chars) and `full_description` (1,000 chars) in the tool.

#### Acceptance Criteria
- [Automated] Unit tests in `tests/unit/test_job_specialist_nodes.py` confirm that the `search_jobs` node successfully invokes the `jsearch_api_search` tool without a `employment_types` key.
- [Automated] Tests in `tests/unit/test_agent.py` confirm the agent successfully generates a `job_specialist_tool` call using the new schema and mandatory `country` field.
- [Manual] Verifying the `jsearch_api_search` tool call in the backend logs shows the `query` containing semantic keywords like "contract" when appropriate, and `employment_types` is absent from the URL parameters.
