# Specification: Interactive Optimizer Agent

## 1. Overview
*   **Summary:** Creation of a fully autonomous "Co-Pilot" testing framework and a specialized AI Agent Persona. The Optimizer Agent will autonomously read error logs, deduce JSearch API integration issues, implement prompt or logic rewrites directly into the codebase, and natively test these changes against the live FastAPI development server.
*   **Context:** The current prompt/agent debugging process is heavily manual. To speed up agentic evolution, we need a truly autonomous optimizer. The human user configures the user profile/preferences; the Optimizer Agent takes over to analyze failures, experiment with code modifications, and independently validate fixes without human bottlenecks.
*   **Primary Goal:** The ultimate objective is to optimize the **relevance and quality** of the job search results returned to the user. The Agent must focus on optimizing how the `JSearch` API is called, how the search queries and keywords are constructed by the LLM, and how parameters like `location`, `country`, and `job_requirements` are utilized to maximize the match between the user's CV/preferences and the returned jobs.

## 2. Functional Requirements

### Requirement A: The Testing Framework (Native Network Execution)
*   [ ] **Native Execution:** The Agent will NOT rely on specialized bash/Python helper scripts or wrappers. It must directly execute raw `curl` commands dynamically via the terminal (handling its own JSON escaping) or use native HTTP tools to interact with the FastAPI endpoints.
*   [ ] **Autonomous Environment Management:** The Agent MUST control its own test environment lifecycle. It is fully responsible for autonomously calling `curl -X DELETE http://localhost:8000/api/profile/reset-discovery` to clear the short-term memory cache cleanly between isolated experiments.

### Requirement B: Memory & Context Acquisition
*   [ ] **Machine-Readable Memory Log:** The Agent MUST maintain its running context, episodic memory, failed hypotheses, and successful prompt discoveries in a structured data format: `data/optimiser-memory.jsonl` (or `.json`). It may compile a human-readable `.md` report only at the end of its run.
*   [ ] Ensure the Optimizer Agent executes a `GET http://localhost:8000/api/profile` request (via `curl` or native API tool) prior to diagnosing any issues to perfectly understand the specific `cv_summary` and `preferences`.
*   [ ] Ensure the Optimizer Agent is instructed to use its native file search capabilities (e.g., `grep_search`, `view_file`) or native log extraction tools to analyze the structured `.jsonl` system execution logs.

### Requirement C: The Optimizer Persona (`SKILL.md`)
*   [ ] Create `.agent/skills/interactive-optimizer/SKILL.md` to formally define the `🧠 AI Optimizer` Persona.
*   [ ] The persona MUST rigidly define the **Autonomous Optimization Loop**:
    1. **Analyze:** Check user profile (`GET /api/profile`) and read system execution `.jsonl` logs for failures using native agent tools.
    2. **Hypothesize:** Document its thesis and expected log outcomes in `data/optimiser-memory.jsonl`.
    3. **Implement:** Directly modify the target codebase files (e.g., `app/agent/main/prompts.py` or tool definitions) using native file-editing tools.
    4. **Reset State:** Autonomously run `curl -X DELETE http://localhost:8000/api/profile/reset-discovery` to prepare for a clean test.
    5. **Execute:** Run native `curl` to `POST /api/chat` with the failing query to test the new code.
    6. **Verify:** Analyze the structured `.jsonl` logs appended during the test to observe JSearch interactions. Update the structured outcome in `data/optimiser-memory.jsonl` and repeat until the issue is resolved.

### Requirement D: Direct External API Analysis (JSearch)
*   [ ] **Direct API Validation:** The Agent MUST be able to execute direct `curl` requests to the external JSearch API to independently verify payload combinations before testing them against the FastAPI backend.
*   [ ] **Credential Extraction:** The Agent is authorized to read the local `.env` file to extract the `JSEARCH_API_KEY` necessary for authentication.
*   [ ] **API Literacy:** The `SKILL.md` persona must instruct the Agent to refer to the JSearch API specification (see Appendix A) for correct endpoint structure and query parameters.

## 3. Verification & Acceptance Criteria
*   [ ] The Agent successfully executes complex raw `curl` payloads directly via the terminal without requiring bash wrapper scripts.
*   [ ] A `data/optimiser-memory.jsonl` file correctly tracks the agent's experimental iterations in a structured, machine-readable format.
*   [ ] The Agent successfully clears the graph memory state autonomously using the HTTP `DELETE` endpoint between tests.
*   [ ] The Optimization Loop demonstrates the Agent directly modifying codebase files (prompts/tools) and autonomously validating the changes without requiring a Human-in-the-Loop pause.
*   [ ] The Agent demonstrates the ability to invoke the JSearch API directly via `curl` to debug third-party API behavior.

---

## Appendix A: JSearch API Reference

**Endpoint Example (`curl`)**:
```bash
curl --request GET \
	--url 'https://jsearch.p.rapidapi.com/search?query=Python%20developer%20in%20Texas%2C%20USA&page=1&num_pages=1' \
	--header 'x-rapidapi-host: jsearch.p.rapidapi.com' \
	--header 'x-rapidapi-key: YOUR_API_KEY_HERE'
```

**Query Parameters:**
*   **`query`** *(String, Required)*: Free-form jobs search query. Highly recommended to include job title and location. Examples: `web development jobs in chicago`, `marketing manager in new york via linkedin`.
*   **`page`** *(Number, Optional)*: Page to return (each page includes up to 10 results). Default: `1`. Allowed: `1-50`.
*   **`num_pages`** *(Number, Optional)*: Number of pages to return. Default: `1`. Allowed: `1-50`. *(Note: Each page returned consumes one request credit).*
*   **`country`** *(String, Optional)*: Country code to return job postings from. **Must be set to get jobs in a specific country**. (e.g., `country=de` for Berlin). Default: `us`.
*   **`language`** *(String, Optional)*: Language code. Leave empty to use primary language in the specified country.
*   **`location`** *(String, Optional)*: The location from which the search is made (Google's UULE parameter). e.g., `New York, United State`.
*   **`date_posted`** *(Enum, Optional)*: Find jobs posted within specific time. Default: `all`. Allowed: `all`, `today`, `3days`, `week`, `month`.
*   **`work_from_home`** *(Boolean, Optional)*: Only return work from home / remote jobs. Default: `false`.
*   **`employment_types`** *(String, Optional)*: Comma delimited list: `FULLTIME`, `CONTRACTOR`, `PARTTIME`, `INTERN`.
*   **`job_requirements`** *(String, Optional)*: Comma delimited list: `under_3_years_experience`, `more_than_3_years_experience`, `no_experience`, `no_degree`.
*   **`radius`** *(Number, Optional)*: Distance from location in km.
*   **`exclude_job_publishers`** *(String, Optional)*: Comma separated list of publishers to exclude. Example: `BeeBe,Dice`.
*   **`fields`** *(String, Optional)*: Comma separated list of job fields to include. By default all fields are returned.
