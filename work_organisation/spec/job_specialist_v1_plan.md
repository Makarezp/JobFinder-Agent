# Sprint V1: Job Specialist Parallel Evaluation & State Separation

## 1. Goal
Refactor the Job Specialist subgraph (`app/agent/job_search/graph.py`) to prevent the Main Discovery Agent from suffocating on large context payloads. We will achieve this by isolating the heavy job data into a graph state variable and returning only 500-character, AI-generated analytical summaries to the Main Agent.

## 2. Architecture: The 4-Node Pipeline

The current monolithic tool call will be replaced by a defined LangGraph pipeline inside the Job Specialist.

### Node 1: `fetch_jobs`
*   **Action:** Executes the JSearch API search based on the Main Agent's parameters.
*   **Post-processing:** Deduplicates jobs and uses `ProfileService` to filter out jobs the user has already seen.
*   **Passes down:** Up to 10 raw `JobListing` objects to the next node.

### Node 2: `evaluate_jobs_parallel`
*   **Action:** Triggers an `asyncio.gather` map-reduce LLM evaluation.
*   **Configurable Batching:** Defined by `EVALUATION_BATCH_SIZE=4`. A standard 10-job array is chunked into `[4, 4, 2]`, firing 3 parallel network calls.
*   **LLM Task:** Evaluates the sub-batches against the `UserProfile` and `Preferences`. Uses `with_structured_output` to enforce a rigid JSON schema.
*   **Output:** Generates a ~500-character "Essence, Conditions, and Limitations" profile-aware summary for each job.
*   **Error Handling:** If an LLM returns fewer summaries than the chunk size (e.g., skips an element), the pipeline catches the mismatch and safely drops the failed items rather than crashing.

### Node 3: `finalize_state`
*   **Action:** Decouples the UI payload from the LLM Context.
*   **Data Blackboard (Graph State):** Writes the massive, original 5,000-word `JobListing` JSON payloads into a dedicated dictionary in the `DiscoveryAgentState` (e.g., `staged_jobs_for_ui`). This state field is passed directly to the frontend API response but is **never** included in the Main Agent's `SYSTEM_PROMPT` or context window.
*   **Context Shield (ToolMessage):** Packages *only* the Job IDs and the 500-character analytical summaries into the LangGraph `ToolMessage` array returned to the Main Agent.
*(Note: Permanent persistence of these jobs across chat sessions will be handled in a later iteration).*

## 3. Required Schema Updates
*   **`DiscoveryAgentState`:** Add `staged_jobs_for_ui: NotRequired[dict[str, Any]]` to hold the heavy payloads.
*   **`JobSpecialistState`:** MUST be updated to support the parallel execution arrays and the new State Router pathways.
*   **Evaluation Pydantic Model:** Create a new structured schema (e.g., `JobSummaryResponse`) containing an array of `[id, summary]` to enforce the LLM's output format during the `asyncio.gather` phase.
