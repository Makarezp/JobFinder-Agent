# Discovery Agent Refactor: Hierarchical Specialist Architecture

## 1. The Core Objective
**Protect the Main Agent’s Context Window.**
The current monolithic "God Object" Discovery Agent is responsible for too much: parsing user intent, formulating exact JSON API schemas (JSearch), evaluating raw payloads, and writing summaries. This causes severe context bloat (1,000+ words per job), which degrades the LLM's persona, increases hallucination rates, and causes "Lost in the Middle" errors.

We will transition to a **Hierarchical Supervisor & Specialist Pattern** integrated with a **Data Blackboard (LangGraph Store)**. By isolating raw data parsing from the Main Agent, we preserve its "Tinder for Jobs" persona and improve system intelligence.

## 2. The Architectural Hierarchy

### A. The Supervisor (Main Discovery Agent)
*   **Role:** Empathy, routing, and conversation.
*   **Behavioral Change:** It no longer sees or processes raw job descriptions or JSON. It only formulates a high-level `intent` and dispatches it.
*   **New Input:** It receives back *only* 2-3 concise, analytical bullet points (e.g., "ID 123: 90% Match due to React/Typescript. Conflict: Requires on-call.") via a standard `ToolMessage`.

### B. The Job Specialist (Analytical Subgraph - V1 Iteration)
To ensure agile delivery, we will implement this refactor in two phases. **V1** will establish the core architectural boundary (Separation of Data vs. Context) using a simpler, parameter-driven parallel structure.

1.  **`fetch_jobs_node` (Tool/API):** Validates the Main Agent's `JobSpecialistInput`, calls JSearch for 10 jobs (Paging Size), deduplicates results, and applies `ProfileService` filtering to drop seen jobs.
2.  **`evaluate_jobs_node` (Parallel LLM Execution):**
    *   Takes the raw list of jobs and processes them in parallel using `asyncio.gather`.
    *   **Configurable Batching:** Driven by a system parameter (default `EVALUATION_BATCH_SIZE=4`). For a standard 10-job page, this chunks the data into arrays of `[4, 4, 2]`, firing 3 concurrent, extremely fast LLM calls perfectly balancing rate limits against LLM truncation risks.
    *   **The Task:** Passes the full descriptions + User Profile + Preferences. Prompts the LLM to extract the *essence, conditions, and limitations* into a rigid ~500-character JSON array, filtering out irrelevant corporate boilerplate.
    *   **Defensive Rule:** Catches JSON schemas that are shorter than the input batch. If 4 jobs go in but only 3 summaries come out, the pipeline safely drops the failed job rather than crashing the array mapping.
3.  **`finalize_payload_node` (State Router):** Splits the data paths to prevent context bloating (see below).

## 3. The Data Blackboard (The Context Shield)
To get the 5,000-word job descriptions to the Frontend without poisoning the Main Agent's context window, we utilize the LangGraph `BaseStore` (Checkpointer) as a data blackboard.

1.  **The Cache Write:** `finalize_payload_node` writes the massive `JobListing` JSON payloads into the LangGraph Store under a namespace like `(user_id, "cached_jobs", job_id)`.
2.  **The Main Agent Read:** The Main Agent is given a specific tool (`fetch_job_details(job_id)`). If the user asks for deep info on a specific job, this tool fetches the payload from the store and strips the 5,000-word text into a clean Markdown summary *before* returning it to the Agent's context array.
3.  **The Frontend Read:** We will create a new FastAPI endpoint (`GET /api/jobs/{job_id}`). When a user clicks "View Full Job" in the UI, Next.js calls this endpoint, which pulls the massive original payload straight from the LangGraph Store, completely bypassing the LLM.

## 4. Latency Mitigation Strategy
To prevent this multi-LLM pipeline from severely delaying the UI response, we employ strict System Economics:
*   **V1 Batch Limit Configuration:** By using dynamic chunking (`EVALUATION_BATCH_SIZE=4`), we achieve the industry-standard balance for LLM generation. Generating up to 2,000 characters of JSON output per batch (4 x 500 chars) is low-latency and protects against LLM memory/truncation bugs. Firing 3 parallel calls for 10 jobs avoids aggressive rate-limiting from standard API providers.
*   **Parallelization:** `evaluate_jobs_node` must execute its batches asynchronously using `asyncio.gather` and extremely fast LLMs (e.g., `gemini-1.5-flash` or `deepseek-chat`).
*   **Frontend UX:** The Next.js frontend should eventually be updated to consume LangGraph state streams (SSE) to show step-by-step progress ("Searching -> Analyzing Top Roles") rather than a static loading spinner.
