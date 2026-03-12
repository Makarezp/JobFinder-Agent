# Specification: Job Specialist Parallel Evaluation & State Separation (V1)

## 1. Overview
*   **Summary:** Refactoring the Discovery Agent's Job Specialist tool into a sub-graph that independently fetches and evaluates jobs in parallel. It will return concise, profile-aware analytical summaries to the Main Agent while exposing the full job descriptions separately for UI consumption via Graph State. Implementation details and persistence logic are deferred.
*   **Context:** The current monolithic approach overloads the Main Discovery Agent with massive raw JSearch payloads (1000+ words per job). This causes severe context window bloat persons . By isolating data retrieval and summarization, we construct a defensive boundary protecting the Main Agent's intelligence.

## 2. Functional Requirements
*   [ ] **Delegated Orchestration:** The Job Specialist must act as an independent subgraph that orchestrates fetching and evaluating jobs.
*   [ ] **Parallelized Evaluation:** The Job Specialist must evaluate retrieved jobs using an LLM in a chunked, parallelized manner to mitigate latency and limit the risk of an LLM dropping items (e.g., maximum batch size limits).
*   [ ] **Profile-Aware Summarization:** The evaluation LLM must generate a rigid, ~500-character summary for each job, synthesizing the job's essence, conditions, and limitations through the lens of the user's profile and preferences. Corporate boilerplate must be discarded.
*   [ ] **Data Blackboard Separation:**  Raw job descriptions (5,000+ characters) must be filtered into a dedicated graph state variable for frontend consumption, bypassing the Main Agent entirely.
*   [ ] **Context Shielding:** The Job Specialist must return *only* the Job IDs and the lightweight analytical summaries to the Main Discovery Agent's context window.

## 3. Verification & Acceptance Criteria
*   [ ] **Latency Protection:** The Job Specialist evaluates fetched jobs concurrently (e.g., via `asyncio.gather`), visibly reducing the time to first token compared to sequential processing.
*   [ ] **Context Integrity Validation:** The Main Discovery Agent receives a payload containing only Job IDs and summaries. Inspecting the LLM `SYSTEM_PROMPT` confirms that the full job descriptions do not bleed into the LLM's context.
*   [ ] **UI Data Delivery:** The Next.js frontend can access the full job descriptions through the API response via a dedicated state payload channel.
*   [ ] **Graceful Degradation:** If an LLM evaluation call drops items (e.g., 4 jobs sent, 3 summaries returned), the system gracefully processes the surviving summaries and drops the failed items without crashing the graph or halting execution.
