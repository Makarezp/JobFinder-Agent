# Sprint V1: Job Specialist Parallel Summarization & State Separation

**Source Spec:** `work_organisation/spec/job_specialist_v1_plan.md`
**Review:** `work_organisation/sprints/review_sprint_v1_defensive_architect.md`
**Branch:** `migration-v2`

## Owner Decisions (Binding)

These decisions were made during the defensive architect review and are **non-negotiable**. The implementing agent MUST follow them.

1. The Job Specialist is a **summarizer, NOT an evaluator**. No `pass_filter`. No keep/drop decisions. The Discovery Agent retains full authority over which jobs to present.
2. The AI-generated summary **replaces the `description` field** on `JobListing`. No new `summary` field. The schema is unchanged.
3. `full_description` cap increases from 1,000 → **5,000 characters**.
4. `full_description` is the **ONLY field stripped** from Discovery Agent context. All other `JobListing` fields flow through the ToolMessage.
5. Dedup happens in `_run_single_job_search` **BEFORE subgraph invocation**. Fresh-only jobs enter the pipeline.
6. LLM instantiation uses **lazy singleton** `_get_summary_llm()`.
7. Prompt templating uses **LangChain `ChatPromptTemplate`** — no manual `.format()`.
8. `with_structured_output` is used as-is. Both Gemini and DeepSeek support it.
9. `num_pages=1` override inside `fetch_jobs`. Whatever the API returns is summarized — no hard cap.
10. State fields use `dict[str, Any]` — pragmatic choice for LangGraph TypedDict serialization.
11. No backward compatibility required. App is not released. Clean break.
12. `job_payloads` contains **ALL jobs** — no pass/fail gating.
13. Configurable LLM timeout: `SUMMARY_LLM_TIMEOUT = 30.0` with `asyncio.wait_for`.

## Dependency Graph

```
Ticket 1 (Schemas + full_desc cap) ──┬──► Ticket 2 (fetch_jobs)
                                      │
                                      ├──► Ticket 3 (Summary prompt + helpers)
                                      │         │
                                      │         ▼
                                      ├──► Ticket 4 (summarize_jobs_parallel) ◄── Ticket 2
                                      │         │
                                      │         ▼
                                      └──► Ticket 5 (finalize_state) ◄────────── Ticket 4
                                                │
                                                ▼
                                      Ticket 6 (Integration: graph wiring,
                                                call_job_specialist, ChatService,
                                                prompt update)
                                                │
                                                ▼
                                      Ticket 7 (End-to-end tests & manual verification)
```

---

## Ticket 1: Schema Foundation — New Pydantic Models, State Updates & Description Cap - done

### Overview
Create the new Pydantic schemas, update existing state TypedDicts, increase the `full_description` cap, and add new constants. This is the foundation every other ticket depends on — no logic changes, just data shapes and configuration.

### Implementation Steps

1. **New Pydantic Model — `app/agent/schemas.py`**:
   Add `JobSummary` and `JobSummaryBatch` models after the existing `AgentResponse` class:
   ```python
   class JobSummary(BaseModel):
       """Single job summary result from the LLM."""
       job_id: str = Field(..., description="The id of the summarized JobListing.")
       description: str = Field(..., description="A ~500-character profile-aware analytical summary covering Essence, Conditions, and Limitations. This replaces the raw JSearch snippet.")

   class JobSummaryBatch(BaseModel):
       """Structured output schema enforced on the summary LLM via with_structured_output."""
       summaries: list[JobSummary] = Field(..., description="One summary per job in the input batch.")
   ```

2. **Update `JobSpecialistState` — `app/agent/job_search/state.py`**:
   The state currently has 2 fields (`input`, `search_results`). Expand it to carry data through the pipeline:
   ```python
   from typing import Any, NotRequired, TypedDict

   from app.agent.schemas import JobListing, JobSpecialistInput


   class JobSpecialistState(TypedDict):
       input: JobSpecialistInput
       user_profile: dict[str, Any] | None          # NEW — injected by caller
       preferences: dict[str, Any] | None            # NEW — injected by caller
       search_results: list[JobListing] | None
       summaries: NotRequired[list[dict[str, Any]]]   # NEW — output of summarize node
       job_payloads: NotRequired[list[dict[str, Any]]]  # NEW — full payloads for UI
       tool_message_content: NotRequired[str]          # NEW — lightweight content for ToolMessage
   ```

3. **Update `DiscoveryAgentState` — `app/agent/discovery/state.py`**:
   Add a single new field to hold job payloads that bypass the LLM context:
   ```python
   job_payloads: NotRequired[list[dict[str, Any]]]
   ```
   This field is written by `call_job_specialist` and read by `ChatService._parse_agent_result`. It is **never** included in any system prompt or LLM context.

4. **Increase `full_description` cap — `app/tools/jsearch_api.py`**:
   Change line 16:
   ```python
   _FULL_DESCRIPTION_MAX_CHARS = 5_000  # was 1_000
   ```
   This is a prerequisite for the summarizer LLM to produce useful analytical descriptions.

5. **New constants — `app/agent/constants.py`**:
   Add:
   ```python
   SUMMARY_BATCH_SIZE: Final[int] = 4
   STAGED_JOBS_KEY: Final[str] = "job_payloads"
   SUMMARY_LLM_TIMEOUT: Final[float] = 60.0
   ```

6. **Tests — `tests/unit/test_schemas.py` (NEW FILE)**:
   - Assert `JobSummary` accepts valid data (`job_id="abc", description="text"`) and rejects missing `job_id`.
   - Assert `JobSummaryBatch` round-trips through `.model_dump()` / `model_validate()`.
   - Assert `JobSummary` has NO `pass_filter` field — `JobSummary(job_id="x", description="y", pass_filter=True)` should raise `ValidationError` (extra fields forbidden).

### Explicit Constraints & Warnings
- **Do NOT modify any node logic, graph wiring, or service code in this ticket.** This is schemas, state, constants, and the description cap only.
- **Do NOT remove any existing fields** from `JobSpecialistState` or `DiscoveryAgentState`. Only add new ones.
- `NotRequired` is used for all new fields so that existing callers that don't provide them continue to work without changes.
- `JobSummaryBatch.summaries` uses `list[JobSummary]`, not `list[dict]`. This is critical because `with_structured_output` needs nested Pydantic models to enforce the schema.
- **There is NO `pass_filter` field anywhere.** The pipeline summarizes, it does not evaluate or filter.

### Acceptance Criteria
- [Automated] `tests/unit/test_schemas.py` passes: `JobSummary`, `JobSummaryBatch` construct, validate, and round-trip correctly. Extra field `pass_filter` is rejected.
- [Automated] All existing tests in `tests/unit/test_job_specialist_nodes.py` and `tests/unit/test_main_nodes.py` continue to pass without modification.
- [Automated] `tests/unit/test_jsearch_api.py` passes (if it asserts on truncation length, update the expected cap to 5,000).

---

## Ticket 2: `fetch_jobs` — Refactor `search_jobs` + Cap + `num_pages` Override - done

### Overview
Refactor the existing `search_jobs` node into `fetch_jobs`. After this ticket, `fetch_jobs` is a standalone function called directly by `_run_single_job_search` — it is NOT a graph node (the subgraph will be a 2-node pipeline: `summarize_jobs_parallel` → `finalize_state`).

### Implementation Steps

1. **Rename & Refactor — `app/agent/job_search/nodes.py`**:
   - Rename `search_jobs` to `fetch_jobs`.
   - The function signature stays `def fetch_jobs(state: JobSpecialistState) -> dict[str, Any]:`.
   - **Override `num_pages=1`** in the `jsearch_api_search.invoke()` call, regardless of what the LLM provided in `input_data.num_pages`. This keeps the fetch predictable (~10 results).
   - Return `{"search_results": listings}` as before. No cap — whatever the API returns is summarized.

2. **Remove from graph — `app/agent/job_search/graph.py`**:
   The graph file is **not updated in this ticket**. It still has the old `search_jobs` node reference. That will be completely rewritten in Ticket 6.

   Alternatively, if the rename breaks the graph import, update the import to `fetch_jobs` and keep the single-node graph temporarily. The graph will be replaced in Ticket 6 anyway.

3. **Update existing tests — `tests/unit/test_job_specialist_nodes.py`**:
   - Rename all references from `search_jobs` to `fetch_jobs` in imports and function calls.
   - Update the import line: `from app.agent.job_search.nodes import fetch_jobs`.
   - Add `test_fetch_jobs_overrides_num_pages_to_one`: Mock `jsearch_api_search`. Create state with `input_data.num_pages=5`. Assert the `invoke()` call received `num_pages` as `"1"` (JSearch params are strings), not `"5"`.
   - Add `test_fetch_jobs_returns_all_api_results`: Mock `jsearch_api_search` to return 15 raw results. Assert `result["search_results"]` has all 15 entries (no cap applied).

### Explicit Constraints & Warnings
- **Do NOT move dedup logic into this function.** Deduplication requires async `ProfileService` access. `fetch_jobs` is synchronous. Dedup happens in `_run_single_job_search` (Ticket 6).
- **`num_pages` is overridden to 1 inside `fetch_jobs`**, not removed from `JobSpecialistInput`. The schema field remains for potential future use, but this function always sends `1` to the API. Whatever the API returns is passed through — no cap.
- The rename from `search_jobs` → `fetch_jobs` will break `tests/unit/test_job_specialist_nodes.py` — the test file must be updated in this same ticket.

### Acceptance Criteria
- [Automated] `test_fetch_jobs_overrides_num_pages_to_one` passes: `num_pages=5` in input → `"1"` sent to API.
- [Automated] `test_fetch_jobs_returns_all_api_results` passes: 15 raw results → 15 `JobListing` objects returned.
- [Automated] All other tests in `test_job_specialist_nodes.py` pass after the rename.

---

## Ticket 3: Summary Prompt & Formatting Helpers

### Overview
Write the LLM prompt template that powers the `summarize_jobs_parallel` node. This prompt takes a batch of job listings plus the user's profile and preferences, and produces structured `JobSummaryBatch` output. The LLM **summarizes** — it does NOT evaluate or filter. This ticket is prompt engineering only — no nodes, no LLM instantiation.

### Implementation Steps

1. **New file — `app/agent/job_search/prompts.py`**:
   Create `SUMMARY_PROMPT` using LangChain `ChatPromptTemplate`:
   ```python
   from langchain_core.prompts import ChatPromptTemplate

   SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
       ("system", """You are a job listing analyst. Your task is to produce a concise, profile-aware analytical description for each job listing.

   **USER PROFILE:**
   {user_profile}

   **USER PREFERENCES:**
   {preferences}

   **INSTRUCTIONS:**
   For each job, produce:
   - `job_id`: Echo the `id` from the input exactly.
   - `description`: A ~500-character analytical summary covering:
     - **Essence**: What the role is and what the company does.
     - **Conditions**: Salary, location, contract type, remote availability.
     - **Limitations**: Any potential mismatches with the user's profile or preferences. Flag uncertainties rather than making definitive judgements.

   **RULES:**
   - Produce EXACTLY one summary per input job. Do not skip any.
   - If a job's description is truncated or sparse, summarize what is available — do NOT penalize the job.
   - If no user profile or CV is available, focus on Essence and Conditions only.
   - You are a summarizer, NOT a filter. Do NOT make keep/drop decisions. Describe limitations factually — the user's agent will decide what to present.
   - Keep each description close to 500 characters. Do not exceed 700."""),
       ("human", "{jobs_json}"),
   ])
   ```

   The template has three placeholders: `{user_profile}`, `{preferences}`, `{jobs_json}`. `ChatPromptTemplate` handles brace escaping — no manual `.format()` needed.

2. **Helper functions — `app/agent/job_search/prompts.py`**:
   ```python
   def format_profile_for_summary(profile: dict[str, Any] | None) -> str:
       """Format user profile dict into a string for the summary prompt."""

   def format_preferences_for_summary(preferences: dict[str, Any] | None) -> str:
       """Format preferences dict into a [WANT]/[AVOID] string for the summary prompt."""
   ```
   These are independent implementations — do NOT import from `app.agent.main.nodes`.

   `format_profile_for_summary`:
   - `None` → `"No profile information available."`
   - Otherwise: include `Name`, `Role`, `CV Summary` if present.

   `format_preferences_for_summary`:
   - `None` or empty dict → `"No preferences set."`
   - Otherwise: `"- [WANT] Remote only"`, `"- [AVOID] No Java"` lines based on `sentiment` field.

3. **Tests — `tests/unit/test_summary_prompt.py` (NEW FILE)**:
   - Assert `format_profile_for_summary(None)` returns `"No profile information available."`.
   - Assert `format_profile_for_summary({"name": "Alice", "role": "Backend Engineer", "cv_summary": "5 years Python"})` includes all three values.
   - Assert `format_preferences_for_summary({"remote": {"key": "remote", "label": "Remote only", "sentiment": "positive"}, "no_java": {"key": "no_java", "label": "No Java", "sentiment": "negative"}})` produces strings containing `[WANT] Remote only` and `[AVOID] No Java`.
   - Assert `format_preferences_for_summary(None)` returns `"No preferences set."`.
   - Assert `SUMMARY_PROMPT` is a `ChatPromptTemplate` instance.
   - Assert the prompt's `input_variables` include `user_profile`, `preferences`, and `jobs_json`.

### Explicit Constraints & Warnings
- **Do NOT create any LLM instances or call any LLM in this ticket.** Prompt text and formatting helpers only.
- **Use `ChatPromptTemplate.from_messages()`** — NOT `str.format()`. This avoids brace-escaping issues with JSON examples in the prompt text.
- The formatting helpers must NOT import from `app.agent.main.nodes` — they are independent implementations within the `job_search` package.
- The prompt must explicitly tell the LLM to return **exactly one summary per input job** and to echo the `job_id` from the input. This is critical for error-handling in Ticket 4.
- **The prompt must NOT instruct the LLM to make pass/fail decisions.** It summarizes. It describes limitations factually. The Discovery Agent decides.

### Acceptance Criteria
- [Automated] `tests/unit/test_summary_prompt.py` passes: all formatting edge cases and template checks.
- [Manual] Read the `SUMMARY_PROMPT` text and confirm: no `pass_filter` language, no "exclude" or "drop" instructions, covers Essence/Conditions/Limitations, handles truncated descriptions, handles missing profile.

---

## Ticket 4: `summarize_jobs_parallel` — Batched LLM Summarization with Timeout

### Overview
Implement the summarization node that chunks job listings into batches of `SUMMARY_BATCH_SIZE` (4), fires parallel LLM calls via `asyncio.gather`, and writes structured summaries into the subgraph state. Each batch call is wrapped with a configurable timeout.

### Implementation Steps

1. **Lazy singleton LLM — `app/agent/job_search/nodes.py`**:
   ```python
   from langchain_core.language_models import BaseChatModel
   from app.core.llm import get_active_model
   from app.agent.schemas import JobSummaryBatch

   _summary_llm: BaseChatModel | None = None

   def _get_summary_llm() -> BaseChatModel:
       global _summary_llm
       if _summary_llm is None:
           _summary_llm = get_active_model(temperature=0).with_structured_output(JobSummaryBatch)
       return _summary_llm
   ```
   This defers LLM instantiation to first call, preventing import-time side effects during test collection.

2. **Chunking helper — `app/agent/job_search/nodes.py`**:
   ```python
   def _chunk_listings(listings: list[JobListing], size: int) -> list[list[JobListing]]:
       """Split listings into sub-lists of `size`."""
       return [listings[i : i + size] for i in range(0, len(listings), size)]
   ```

3. **Single-batch summarization — `app/agent/job_search/nodes.py`**:
   ```python
   async def _summarize_batch(
       batch: list[JobListing],
       profile: dict[str, Any] | None,
       preferences: dict[str, Any] | None,
   ) -> list[dict[str, Any]]:
   ```
   - Builds the prompt using `SUMMARY_PROMPT.format_messages(...)` with `format_profile_for_summary(profile)`, `format_preferences_for_summary(preferences)`, and `json.dumps([j.model_dump() for j in batch])`.
   - Calls `await _get_summary_llm().ainvoke(messages)`.
   - Validates the result: if `len(result.summaries) != len(batch)`, log a warning and return only the summaries that have a `job_id` matching one of the batch's IDs. Drop mismatches silently.
   - Wrap the entire call in a `try/except Exception` — on failure, log the error and return an empty list (the batch is dropped, not the whole pipeline).
   - Return `[s.model_dump() for s in result.summaries]`.

4. **Node function — `app/agent/job_search/nodes.py`**:
   ```python
   async def summarize_jobs_parallel(state: JobSpecialistState) -> dict[str, Any]:
   ```
   - Read `search_results`, `user_profile`, `preferences` from state.
   - If `search_results` is empty or `None`, return `{"summaries": []}`.
   - Chunk the listings using `_chunk_listings(search_results, SUMMARY_BATCH_SIZE)`.
   - Fire all chunks in parallel with timeout:
     ```python
     async def _timed_batch(chunk: list[JobListing]) -> list[dict[str, Any]]:
         try:
             return await asyncio.wait_for(
                 _summarize_batch(chunk, profile, prefs),
                 timeout=SUMMARY_LLM_TIMEOUT,
             )
         except asyncio.TimeoutError:
             logger.warning("Summary batch timed out", batch_size=len(chunk))
             return []

     results = await asyncio.gather(*[_timed_batch(chunk) for chunk in chunks])
     ```
   - Flatten: `all_summaries = [s for batch_result in results for s in batch_result]`.
   - Log: `"Node Completed: summarize_jobs_parallel"`, `summary_count=len(all_summaries)`, `input_count=len(search_results)`.
   - Return `{"summaries": all_summaries}`.

5. **Tests — `tests/unit/test_job_specialist_nodes.py`** (extend existing file):
   - `test_chunk_listings_even_split`: 8 items, size 4 → 2 chunks of 4.
   - `test_chunk_listings_remainder`: 10 items, size 4 → chunks of [4, 4, 2].
   - `test_chunk_listings_empty`: 0 items → empty list.
   - `test_summarize_jobs_parallel_empty_results`: state with `search_results=[]` returns `{"summaries": []}`.
   - `test_summarize_jobs_parallel_calls_llm_per_chunk`: Mock `_get_summary_llm()` to return a mock whose `.ainvoke` returns valid `JobSummaryBatch`. Provide 10 jobs. Assert `ainvoke` was called 3 times (batches of 4, 4, 2).
   - `test_summarize_batch_handles_llm_exception`: Mock LLM `.ainvoke` to raise `Exception`. Assert `_summarize_batch` returns `[]`.
   - `test_summarize_batch_handles_count_mismatch`: Mock LLM returns 3 summaries for a batch of 4. Assert only the 3 with valid matching `job_id`s are returned.
   - `test_summarize_batch_handles_timeout`: Mock LLM `.ainvoke` to hang (use `asyncio.sleep(60)`). Assert the batch returns `[]` after timeout (not hang forever).

### Explicit Constraints & Warnings
- **Use `_get_summary_llm()` lazy singleton** — do NOT instantiate at module level. In tests, patch `app.agent.job_search.nodes._get_summary_llm`.
- **Do NOT use `.invoke()` (synchronous).** The node is `async` and must use `await .ainvoke()`.
- **The node must never raise.** Any LLM failure or timeout is caught and results in dropped summaries, not a graph crash. This follows the project's "Observation over exception" design principle (`DESIGN_PRINCIPLES.md` §4).
- **Do NOT wire this node into the graph yet.** Graph changes happen in Ticket 6.
- **There is NO `pass_filter` in `JobSummary`.** The summaries contain `job_id` and `description` only.
- **Wrap each batch with `asyncio.wait_for(..., timeout=SUMMARY_LLM_TIMEOUT)`** — handle `asyncio.TimeoutError` the same as other exceptions.

### Acceptance Criteria
- [Automated] All 8 new tests in `tests/unit/test_job_specialist_nodes.py` pass.
- [Automated] Existing tests in the same file still pass.
- [Automated] `mypy` passes on `app/agent/job_search/nodes.py`.

---

## Ticket 5: `finalize_state` — Merge Summaries & Separate UI/Context Data

### Overview
Implement the final node in the Job Specialist pipeline. It merges AI-generated descriptions back into `JobListing` objects (overwriting the raw JSearch snippet), then separates the heavy UI payload (`full_description` included) from the lightweight LLM context (`full_description` stripped). ALL jobs flow to both outputs — no filtering.

### Implementation Steps

1. **Node function — `app/agent/job_search/nodes.py`**:
   ```python
   def finalize_state(state: JobSpecialistState) -> dict[str, Any]:
   ```
   - Read `search_results` and `summaries` from state.
   - If `search_results` is `None`/empty or `summaries` is empty, return:
     ```python
     {"job_payloads": [], "tool_message_content": json.dumps({"jobs": [], "note": "No jobs found."})}
     ```
   - Build a lookup: `summary_by_id = {s["job_id"]: s["description"] for s in summaries}`.
   - **Merge descriptions:** For each job in `search_results`:
     - If the job's `id` has a matching summary, overwrite `job.description` with the AI-generated text.
     - If no matching summary (LLM dropped it), keep the original raw snippet.
     - Call `job.model_dump()` to get the full dict.
   - **`job_payloads` (for UI):** List of ALL merged `JobListing` dicts. Contains `full_description` (up to 5,000 chars) and `apply_link`. ALL jobs, no filtering.
   - **`tool_message_content` (for LLM):** JSON string of the same jobs but with `full_description` key **removed** from each entry:
     ```json
     {
       "jobs": [
         {
           "id": "abc123",
           "title": "Senior Python Dev",
           "company": "Acme Corp",
           "location": "London, UK",
           "salary": "$80k-$100k/YEAR",
           "description": "AI-generated ~500-char analytical description...",
           "apply_link": "https://..."
         }
       ],
       "note": "Summarized 8 jobs."
     }
     ```
     This is what the Discovery Agent sees in its ToolMessage. It contains **no `full_description`** — that's the only field stripped.
   - Log: `"Node Completed: finalize_state"`, `staged_count=len(job_payloads)`, `summarized_count=sum(1 for j in job_payloads if j["id"] in summary_by_id)`.
   - Return `{"job_payloads": job_payloads, "tool_message_content": tool_message_content}`.

2. **Tests — `tests/unit/test_job_specialist_nodes.py`** (extend existing file):
   - `test_finalize_state_merges_ai_descriptions`: Provide 3 search results and 3 summaries. Assert:
     - `job_payloads` has 3 entries (ALL jobs, no filtering).
     - Each `job_payloads[i]["description"]` matches the AI-generated text, not the raw snippet.
     - Each `job_payloads[i]` contains `full_description` and `apply_link`.
   - `test_finalize_state_tool_message_strips_full_description`: Assert:
     - `tool_message_content` is valid JSON.
     - Parsed JSON has 3 entries under `"jobs"`.
     - Each entry has `id`, `title`, `company`, `location`, `salary`, `description`, `apply_link`.
     - The string `"full_description"` does NOT appear anywhere in `tool_message_content`.
   - `test_finalize_state_keeps_raw_snippet_on_summary_miss`: Provide 3 search results but only 2 summaries. Assert the job without a matching summary retains its original `description`.
   - `test_finalize_state_empty_search_results`: `search_results=[]` → `job_payloads=[]`, `tool_message_content` contains `"No jobs found."`.
   - `test_finalize_state_empty_summaries`: `search_results` has jobs but `summaries=[]` → ALL jobs still appear in both outputs with their original descriptions intact.

### Explicit Constraints & Warnings
- **ALL jobs go to both outputs.** There is no pass/fail gating. No `pass_filter`. Every job that enters `finalize_state` exits in both `job_payloads` and `tool_message_content`.
- **`job_payloads` contains FULL `JobListing.model_dump()` data** — including `full_description` and `apply_link`. This is the data that reaches the frontend.
- **`tool_message_content` must NEVER contain `full_description`.** This is the ONLY field stripped. All other fields (`id`, `title`, `company`, `location`, `salary`, `description`, `apply_link`) ARE included.
- When summaries are missing (LLM failure, timeout, or count mismatch from Ticket 4), the job keeps its original raw snippet — it is NOT dropped.
- **Do NOT wire this node into the graph yet.** That happens in Ticket 6.

### Acceptance Criteria
- [Automated] All 5 new tests in `tests/unit/test_job_specialist_nodes.py` pass.
- [Automated] `json.loads(result["tool_message_content"])` succeeds in every test (valid JSON).
- [Automated] No test's `tool_message_content` contains the substring `"full_description"`.
- [Automated] `job_payloads` in every test DOES contain `full_description` for each entry.

---

## Ticket 6: Integration — Graph Wiring, `call_job_specialist`, ChatService, Prompt Update

### Overview
Wire everything together. This ticket builds the 2-node subgraph, restructures `_run_single_job_search` to handle fetch + dedup externally before subgraph invocation, updates `call_job_specialist` to propagate `job_payloads`, updates `ChatService` to read staged jobs from state, and updates the main agent's system prompt.

### Implementation Steps

1. **Wire the 2-node subgraph — `app/agent/job_search/graph.py`**:
   Replace the entire file with a 2-node pipeline:
   ```python``
   import structlog
   from langgraph.graph import END, START, StateGraph

   from app.agent.job_search.nodes import summarize_jobs_parallel, finalize_state
   from app.agent.job_search.state import JobSpecialistState

   logger = structlog.get_logger(__name__)

   SUMMARIZE_NODE = "summarize_jobs_parallel"
   FINALIZE_NODE = "finalize_state"

   workflow = StateGraph(JobSpecialistState)
   workflow.add_node(SUMMARIZE_NODE, summarize_jobs_parallel)
   workflow.add_node(FINALIZE_NODE, finalize_state)
   workflow.add_edge(START, SUMMARIZE_NODE)
   workflow.add_edge(SUMMARIZE_NODE, FINALIZE_NODE)
   workflow.add_edge(FINALIZE_NODE, END)

   job_search_graph = workflow.compile()
   ```
   `fetch_jobs` is NOT a graph node. It is called directly by `_run_single_job_search`.

2. **Restructure `_run_single_job_search` — `app/agent/discovery/graph.py`**:
   This function now handles fetch + dedup BEFORE subgraph invocation. The flow:
   ```
   1. Call fetch_jobs() directly → get capped list[JobListing]
   2. Get seen_ids from ProfileService
   3. Apply _split_fresh_seen → fresh list, seen list
   4. Mark fresh jobs as seen via ProfileService
   5. Invoke 2-node subgraph with fresh-only jobs → get job_payloads + tool_message_content
   6. Append seen jobs as minimal identity entries to tool_message_content
   7. Return ToolMessage + job_payloads
   ```

   Updated signature:
   ```python
   async def _run_single_job_search(
       tool_call: Any,
       profile_service: ProfileService,
       user_profile: dict[str, Any] | None,
       preferences: dict[str, Any] | None,
   ) -> tuple[ToolMessage, list[dict[str, Any]]]:
   ```
   Returns a tuple: the `ToolMessage` for the LLM AND the list of `job_payloads` dicts for the UI.

   Key changes from current implementation:
   - Import and call `fetch_jobs` directly: `fetch_result = fetch_jobs({"input": input_data, "search_results": None, "user_profile": None, "preferences": None})`.
   - Dedup on the `fetch_result["search_results"]` using `_split_fresh_seen` and `profile_service.mark_jobs_seen`.
   - Build subgraph initial state with fresh-only jobs:
     ```python
     subgraph_state: JobSpecialistState = {
         "input": input_data,
         "search_results": fresh,
         "user_profile": user_profile,
         "preferences": preferences,
     }
     ```
   - Invoke `job_search_graph.ainvoke(cast(Any, subgraph_state))`.
   - Read `result.get("job_payloads", [])` and `result.get("tool_message_content", "")`.
   - If there are `seen` jobs, append them as minimal identity entries to the `tool_message_content` JSON (parse → add `"seen"` key → re-serialize). This preserves the existing behavior where the Discovery Agent knows about seen jobs.
   - Build `ToolMessage(content=tool_message_content, tool_call_id=...)`.
   - Return `(tool_message, job_payloads)`.

3. **Update `call_job_specialist` — `app/agent/discovery/graph.py`**:
   - Read `user_profile` and `preferences` from `state` and pass them to `_run_single_job_search`.
   - Collect `(tool_message, job_payloads)` tuples from all parallel search results.
   - Aggregate staged jobs into a flat list:
     ```python
     all_tool_messages: list[ToolMessage] = []
     all_job_payloads: list[dict[str, Any]] = []

     results = await asyncio.gather(*[
         _run_single_job_search(tc, profile_service, user_profile, preferences)
         for tc in job_tool_calls_to_run
     ])

     for tool_msg, job_payloads in results:
         all_tool_messages.append(tool_msg)
         all_job_payloads.extend(job_payloads)

     tool_messages.extend(all_tool_messages)

     return {
         "messages": tool_messages,
         "search_attempts": current_attempts + 1,
         "job_payloads": all_job_payloads,
     }
     ```
   - Remove the old `_run_single_job_search` implementation that built `{"fresh": ..., "seen": ...}` JSON directly.

4. **Update `ChatService._parse_agent_result` — `app/services/chat_service.py`**:
   Read `job_payloads` from the result state. When present, use it as the job data source instead of `final_answer` tool args:
   ```python
   job_payloads = result.get("job_payloads", [])
   if job_payloads:
       jobs = job_payloads
   ```
   The profile workspace never produces `job_payloads`, so the existing `final_answer` extraction path remains as the fallback for non-discovery conversations.

5. **Update Main Agent Prompt — `app/agent/main/prompts.py`**:
   Replace the "Filter & Present Results" section (current lines 69-107). The main agent now receives pre-summarized analytical descriptions instead of raw JSearch snippets. Replace with:
   ```
   3.  **Review & Present Results:**
       *   The `job_specialist_tool` returns jobs with AI-generated analytical descriptions.
       *   Each job includes: id, title, company, location, salary, description (AI-summarized),
           and apply_link. The `description` field covers Essence, Conditions, and Limitations.
       *   **You decide which jobs to present.** Review the descriptions and apply the two lenses:
           - **Lens 1 — CV Fit**: Does the role match the user's seniority, tech stack, and domain?
           - **Lens 2 — Preferences & Salary**: Does the job align with [WANT]/[AVOID] preferences?
       *   If all descriptions look truncated or sparse, do not penalize — present them with a note.
       *   **YOU MUST** call `final_answer` to present results.
       *   Populate `jobs` with the full job objects that passed your review.
       *   Populate `text_response` with a conversational summary. If jobs were excluded,
           briefly note why.
   ```
   The key change: the Discovery Agent still does the CV Fit and Preferences evaluation, but on AI-summarized descriptions (~500 chars) instead of raw JSearch snippets (300 chars). It has full authority to keep or drop.

6. **Update existing tests**:
   - `tests/unit/test_job_specialist_nodes.py`: The `_make_state` helper needs `user_profile` and `preferences` keys (set to `None`).
   - `tests/unit/test_chat_service.py`: Add `test_parse_agent_result_prefers_job_payloads`: Result dict with both `final_answer` jobs and `job_payloads`. Assert `_parse_agent_result` returns the staged jobs.
   - `tests/unit/test_chat_service.py`: Add `test_parse_agent_result_falls_back_without_job_payloads`: Result dict without `job_payloads` behaves as before (profile workspace path).

### Explicit Constraints & Warnings
- **`fetch_jobs` is called directly in `_run_single_job_search`**, NOT as a graph node. The subgraph is 2 nodes: `summarize_jobs_parallel` → `finalize_state`.
- **Dedup happens BEFORE subgraph invocation.** Only fresh jobs enter the summarization pipeline. No LLM tokens wasted on seen jobs.
- **`job_payloads` flows through `DiscoveryAgentState`** but is NEVER formatted into any prompt. If you see it in a prompt string, that is a critical bug.
- **Do NOT remove `_split_fresh_seen` or `mark_jobs_seen`.** They remain, called from `_run_single_job_search`.
- **`_run_single_job_search` now returns a tuple** `(ToolMessage, list[dict])`, not just a `ToolMessage`. This requires updating `call_job_specialist`'s aggregation logic.
- **No backward compatibility logic.** The old `{"fresh": ..., "seen": ...}` ToolMessage format is gone. Clean break.

### Acceptance Criteria
- [Automated] `tests/unit/test_chat_service.py::test_parse_agent_result_prefers_job_payloads` passes.
- [Automated] `tests/unit/test_chat_service.py::test_parse_agent_result_falls_back_without_job_payloads` passes.
- [Automated] All existing tests in `test_job_specialist_nodes.py`, `test_main_nodes.py`, and `test_chat_service.py` pass.
- [Manual] Start the backend (`uvicorn app.main:app --reload`). Send a chat message like "Find me Python developer jobs in London". Verify in the server logs:
  1. `Node Started: search_jobs` / `Node Completed: fetch_jobs` appears with `result_count <= 10`.
  2. `Node Completed: summarize_jobs_parallel` appears with `summary_count`.
  3. `Node Completed: finalize_state` appears with `staged_count`.
  4. The API response JSON contains `jobs` with AI-generated `description`, `full_description` (up to 5,000 chars), and `apply_link`.

---

## Ticket 7: End-to-End Tests & Manual Verification

### Overview
Write integration-level tests that verify the complete pipeline from `_run_single_job_search` through the 2-node subgraph and back. Verify that the frontend receives correct data, that `full_description` is stripped from LLM context, and that dedup works correctly.

### Implementation Steps

1. **New integration test — `tests/integration/test_job_specialist_pipeline.py` (NEW FILE)**:

   - `test_pipeline_produces_job_payloads_with_full_data`:
     Mock `jsearch_api_search` to return 5 raw jobs (with `full_description` up to 5,000 chars). Mock `_get_summary_llm()` to return valid `JobSummaryBatch`. Assert:
     - The `job_payloads` has 5 entries (ALL jobs, no filtering).
     - Each entry has `full_description` and `apply_link`.
     - Each entry's `description` is the AI-generated text, not the raw JSearch snippet.

   - `test_pipeline_tool_message_strips_only_full_description`:
     Same setup. Parse the `tool_message_content` JSON. Assert:
     - The string `"full_description"` does NOT appear anywhere in `tool_message_content`.
     - Each job in the parsed JSON DOES have `id`, `title`, `company`, `location`, `salary`, `description`, `apply_link`.

   - `test_pipeline_handles_llm_summary_failure_gracefully`:
     Mock `_get_summary_llm().ainvoke` to raise `Exception("LLM down")`. Assert:
     - The pipeline does NOT crash.
     - `job_payloads` contains ALL 5 jobs (with original raw descriptions as fallback).

   - `test_pipeline_handles_llm_timeout`:
     Mock `_get_summary_llm().ainvoke` to `asyncio.sleep(60)`. Assert:
     - The pipeline does NOT hang.
     - Completes within `SUMMARY_LLM_TIMEOUT + 5` seconds.
     - `job_payloads` contains ALL jobs with original descriptions.

   - `test_pipeline_passes_all_api_results`:
     Mock `jsearch_api_search` to return 15 raw jobs. Assert that `job_payloads` has all 15 entries — pipeline does not cap results.

   - `test_pipeline_dedup_excludes_seen_jobs`:
     Pre-populate `ProfileService` seen jobs with 3 IDs. Mock `jsearch_api_search` to return 10 jobs including those 3 IDs. Assert:
     - `job_payloads` contains exactly 7 entries (fresh only).
     - `tool_message_content` includes a `"seen"` section with the 3 seen job identities.

2. **Update existing integration test — `tests/integration/test_job_specialist.py`**:
   Review and update any assertions that depend on the old `ToolMessage` format (`{"fresh": [...], "seen": [...]}`). The new format is `{"jobs": [...], "seen": [...], "note": "..."}`.

3. **Manual verification checklist** (include as comments in the test file header):
   ```
   # Manual Verification Checklist:
   # 1. Start backend: uvicorn app.main:app --reload
   # 2. Start frontend: cd frontend && npm run dev
   # 3. Upload a CV (any PDF) → verify profile is created
   # 4. Send: "Find me senior Python developer jobs in London"
   # 5. Check Network tab: POST /api/chat response has jobs[] with full data
   #    - description should be AI-generated (~500 chars), not the raw JSearch snippet
   #    - full_description should be up to 5,000 chars
   # 6. Check server logs: summarize_jobs_parallel and finalize_state log start/complete
   # 7. Check server logs: ToolMessage content has job objects WITHOUT full_description
   # 8. Send: same query again → verify dedup (seen jobs not in job_payloads)
   # 9. Click a job card → verify apply_link works
   ```

### Explicit Constraints & Warnings
- **All integration tests must mock external I/O** (JSearch API, LLM calls). Do NOT hit real APIs. Mock `app.tools.jsearch_api.jsearch_api_search` and `app.agent.job_search.nodes._get_summary_llm`.
- **Do NOT mock the graph itself** — let it run through the real 2-node pipeline. Only mock the leaf I/O.
- When checking that `tool_message_content` excludes `full_description`, use substring assertions (`assert "full_description" not in content`).
- **No `pass_filter` anywhere** — if any test references pass/fail filtering, that is a bug.
- When testing LLM failure/timeout, assert that ALL jobs still appear in `job_payloads` with their original descriptions. Graceful degradation means no data loss.

### Acceptance Criteria
- [Automated] All 6 new integration tests pass.
- [Automated] All existing tests across `tests/unit/` and `tests/integration/` pass (full regression).
- [Manual] Complete the 9-step manual verification checklist above. All steps pass without error.

---

## Review Checklist (from Defensive Architect Review)

- [x] No mention of `pass_filter` anywhere in the sprint.
- [x] No mention of `JobEvaluation` or `evaluate` — all renamed to `JobSummary` / `summarize`.
- [x] No separate `summary` field — AI output goes into `description`.
- [x] `_FULL_DESCRIPTION_MAX_CHARS = 5_000` is an explicit step (Ticket 1, Step 4).
- [x] `tool_message_content` includes all `JobListing` fields except `full_description`.
- [x] `job_payloads` includes ALL jobs (no pass/fail gating).
- [x] Dedup strategy is singular: before subgraph, in `_run_single_job_search`.
- [x] LLM uses `_get_summary_llm()` lazy singleton, not module-level instance.
- [x] Prompt uses `ChatPromptTemplate`, not `.format()`.
- [x] `num_pages` overridden to 1. No hard cap — all API results are summarized.
- [x] `SUMMARY_LLM_TIMEOUT` in constants, `asyncio.wait_for` wrapping batch calls.
- [x] No backward compatibility logic — clean break.
- [x] Profile workspace fallback in `_parse_agent_result` preserved (workspace routing, not compat).
