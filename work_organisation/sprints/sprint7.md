# Sprint 7: Search Quality & Reliability

## Goal
Address the structural search failures identified in production logs. The LLM is constructing overly complex, Boolean-operator-laden query strings (e.g., `"social media assistant or admin or customer service in St Albans"`) that return zero results from JSearch, causing the agent to burn all 3 loop-protection attempts and fail its core mandate. This sprint constrains the tool schema and system prompt to force the LLM to produce API-compatible, high-yield queries.

---

## Ticket 7.1: Backend — Constrain `JobSpecialistInput` Query Schema to Prevent Boolean Query Poisoning

### Overview
The LLM is exploiting the loosely described `query` field in `JobSpecialistInput` to encode complex Boolean logic into a single string (e.g., `"admin or social media or customer service in St Albans"`). The JSearch API does not support multi-term Boolean syntax; it treats the entire string as a natural-language phrase, which destroys result relevance and frequently returns zero results. This ticket surgically hardens the input schema and system prompt to enforce a single-role, single-location search pattern, and updates the prompt to guide multi-role exploration via sequential single-term calls.

### Implementation Steps

#### Step 1: Harden `JobSpecialistInput` in `app/agent/schemas.py`

**File**: `app/agent/schemas.py`

The current `query` field description is:
```python
query: str = Field(..., description="Google-style search query (e.g., 'python engineer in london').")
```

Replace it with a description that explicitly prohibits Boolean logic and co-mingling of role and location:
```python
query: str = Field(
    ...,
    description=(
        "A single, simple job title or role keyword. "
        "DO NOT use Boolean operators ('or', 'and', '|'). "
        "DO NOT combine multiple job titles in one query. "
        "DO NOT include the location in this field — location belongs at the end of the query string only if JSearch requires it. "
        "GOOD: 'admin assistant', 'social media coordinator', 'receptionist'. "
        "BAD: 'admin or social media or customer service', 'part time admin or receptionist in St Albans'."
    ),
)
```

All other fields (`date_posted`, `employment_types`, `remote_only`, `page`) remain unchanged.

#### Step 2: Update `JSearchApiArgs` in `app/tools/jsearch_api.py` to enforce location separation

**File**: `app/tools/jsearch_api.py`

The `JSearchApiArgs` schema is used by the raw tool layer (called internally by `search_jobs` node, not directly by the LLM). Its `query` field description should be updated in parallel to match the new schema narrative:

```python
query: str = Field(
    ...,
    description=(
        "A single, simple job title keyword. "
        "For location-scoped searches, append the location as a suffix: e.g., 'admin assistant St Albans'. "
        "DO NOT use Boolean 'or'/'and' operators. DO NOT combine multiple roles."
    ),
)
```

No functional change to the HTTP call is required.

#### Step 3: Update `SYSTEM_PROMPT` in `app/agent/main/prompts.py`

**File**: `app/agent/main/prompts.py`

1. Locate the **"JOB SEARCH INSTRUCTIONS"** section, specifically item `2. **Search Jobs:**`. The current text reads:
```
*   Craft a specific Google-style query (e.g., "senior react developer in london").
```

Replace that bullet point with the following expanded guidance:
```
*   Craft a **single, simple job title query** (e.g., "admin assistant St Albans", "social media coordinator London").
*   **CRITICAL — DO NOT use Boolean operators**: Never use 'or', 'and', or '|' in the query string. JSearch does not support Boolean syntax and will return zero results.
*   **ONE ROLE PER CALL**: If the user's profile suits multiple roles (e.g., admin, receptionist, social media), call `job_specialist_tool` **once per role** with a separate, simple query for each. Do not combine them in one call.
*   If searching by location, append the city/town directly to the role keyword: e.g., query="admin assistant St Albans".
```

2. Locate item `4. **Handling No Results:**`. The current text reads:
```
4.  **Handling No Results:**
    *   If a search returns no jobs, try **ONE** modified query (broader keywords,
        relaxed location, or different employment type).
    *   **STOP** after 3 total search attempts. Do NOT loop indefinitely.
    *   Call `final_answer` and explain what you tried and suggest alternatives.
```

Replace it with the following deterministic Fallback Strategy:
```
4.  **Handling Zero Results (The Fallback Strategy):**
    *   If `job_specialist_tool` returns zero results, you MUST analyze why before retrying.
    *   **Attempt 2 (Broaden the Role):** If your first query was highly specific (e.g., "bilingual social media coordinator St Albans"), make the role generic. Try just "social media St Albans" or "marketing St Albans". Remove adjectives.
    *   **Attempt 3 (Expand the Location):** If the generic role still fails, the location is too restrictive. Drop the specific town and use the nearest major city, or drop the location entirely and rely on the UI/user to filter later (e.g., "social media London" or just "social media").
    *   **STOP LIMIT:** You have a strict budget of 3 searches per conversation turn. If Attempt 3 fails, you MUST stop searching immediately.
    *   Call `final_answer` and explicitly tell the user: "I searched for X and Y in [Location], but couldn't find any matches right now. Would you be open to commuting to [Bigger City] or looking at [Adjacent Role]?"
```

The rest of the "JOB SEARCH INSTRUCTIONS" section (items 1 and 3) must remain **exactly** as written. Do not alter the handling of `fresh`/`seen` job deduplication or the filter lenses.

#### Step 4: Update the unit test for `JobSpecialistInput` in `tests/unit/test_agent.py`

**File**: `tests/unit/test_agent.py` (or `tests/unit/test_job_specialist_nodes.py` — check which file validates schema instantiation)

Add or update tests to assert the new field-level description is present and that the schema can still be instantiated correctly with simple single-role queries. Specifically:

- Assert `JobSpecialistInput(query="admin assistant", page=1)` is valid.
- Assert `JobSpecialistInput(query="receptionist St Albans", remote_only=False)` is valid.
- There is no runtime enforcement (Pydantic does not validate the content of `str` fields against descriptions), so these tests confirm the schema contract is not broken, not that Boolean strings are blocked.

> **Note**: Runtime rejection of Boolean queries is intentionally NOT implemented via Pydantic validators. Validation belongs in the system prompt contract (Step 3). Adding a `BeforeValidator` to reject "or"/"and" strings would break the agent's retry logic if the LLM makes a transient mistake — returning an error tool response is always preferable to raising an exception inside schema validation.

### Explicit Constraints & Warnings

- **DO NOT add a `location` field to `JobSpecialistInput`**: A separate `location` field was considered and rejected. JSearch's `/search` endpoint works best with a combined `"role city"` string. Splitting them into separate parameters would require reconstructing the query in `app/agent/job_search/nodes.py`, creating a hidden coupling between the schema and the tool internals. The current architecture is correct — location is simply appended to the `query` string by the LLM.

- **DO NOT add a Pydantic `@field_validator` to reject Boolean operators**: This creates a `ValidationError` exception path inside the LangGraph tool invocation. Per `CONVENTIONS.md`, tools MUST NOT raise exceptions for anticipated runtime errors — they must return descriptive strings. Blocking the LLM at schema validation time crashes the graph node, not the tool. The correct enforcement layer is the system prompt.

- **DO NOT change `job_specialist_tool` in `app/agent/main/tools.py`**: This is a phantom tool whose schema is `args_schema=JobSpecialistInput`. Its Python function signature must remain synchronized with `JobSpecialistInput`. Since only the `Field(description=...)` is changing (not the field names or types), the stub function body and signature require **no changes**.

- **DO NOT change `search_jobs` node in `app/agent/job_search/nodes.py`**: It reads `state["input"].query` and passes it verbatim to `jsearch_api_search`. This plumbing is correct and unchanged.

- **Typing**: After changes, run `mypy --strict app/agent/schemas.py app/agent/main/prompts.py app/tools/jsearch_api.py`. No type errors are expected since only `Field(description=...)` strings are modified.

### Acceptance Criteria

- **[Automated]** The new `JobSpecialistInput` unit tests pass, confirming the model instantiates properly with basic string queries.
- **[Manual — Regression]** Upload a CV for a user with multiple applicable roles (e.g., social media, admin, customer service). Ask the bot to find jobs. Verify via server logs that:
  - Each `jsearch_api_search` call uses a **single, clean role keyword** (e.g., `query='admin assistant London'`), never a Boolean string.
  - The agent makes **separate sequential calls** for different roles rather than one combined call.
  - `result_count` is greater than 0 for at least one search attempt.
  - Loop protection warning (`max search attempts reached`) does **not** fire.
- **[Manual — Regression]** Ask the bot to find "admin or receptionist jobs". Verify in logs that the LLM translates this into two separate `job_specialist_tool` calls rather than passing `"admin or receptionist"` as the query.

---

## Ticket 7.2: Backend — LangGraph Execution Resilience (LLM Fallback)

### Overview
Currently, if the LLM provider (Google Gemini) exhausts its SDK-level retries (e.g., repeating 503 or 429 errors), it throws an exception that crashes the LangGraph node (`main_chatbot` or `onboarding_chatbot`). While the `POST /api/chat` route catches this and returns a 200 OK with a generic error string, the *internal graph state* fails to checkpoint. This causes the system to completely drop the user's latest message from conversational memory. This ticket wraps the `llm.invoke()` calls inside the nodes with a `try/except` block to gracefully inject an AI fallback message, ensuring the state machine completes successfully and commits the interaction history to SQLite.

### Implementation Steps

#### Step 1: Wrap `onboarding_chatbot` in a strict Exception boundary

**File**: `app/agent/onboarding/nodes.py`

Locate the `onboarding_chatbot` function. Specifically, replace the `response = onboarding_llm.invoke(all_messages)` line:

```python
    try:
        response = onboarding_llm.invoke(all_messages)
        logger.debug("LLM Response", content=response.content)
        log_node_completed("onboarding_chatbot", response)
        return {"messages": [response]}
    except Exception as e:
        logger.error("LLM Execution Failed in onboarding_chatbot", error=str(e))
        # Protect the graph state: Fake an AI response explaining the failure cleanly.
        fallback_msg = AIMessage(
            content="I'm sorry, but my connection to the AI network is currently experiencing heavy load. Please give me a second and try your request again."
        )
        return {"messages": [fallback_msg]}
```

#### Step 2: Wrap `main_chatbot` in a strict Exception boundary

**File**: `app/agent/main/nodes.py`

Locate the `main_chatbot` function. Wrap the `response = main_llm.invoke(all_messages)` line similarly to prevent crashes in the primary execution path:

```python
    try:
        response = main_llm.invoke(all_messages)
        logger.debug("LLM Response", content=response.content)
        log_node_completed("main_chatbot", response)
        return {"messages": [response]}
    except Exception as e:
        logger.error("LLM Execution Failed in main_chatbot", error=str(e))
        # Protect the graph state: Fake an AI response explaining the failure cleanly.
        fallback_msg = AIMessage(
            content="I'm sorry, I'm having trouble connecting to my processing network right now due to high demand. Could you please try your request again in a moment?"
        )
        return {"messages": [fallback_msg]}
```

#### Step 3: Write Resilience Unit Tests

**File**: `tests/unit/test_agent.py`

Add two new tests using `@patch` to simulate LLM failures:
1. `test_main_chatbot_handles_llm_exception()`: Mock `app.agent.main.nodes.main_llm.invoke` to raise an `Exception`. Assert that `main_chatbot` returns `{"messages": [AIMessage(...)]}` with the fallback string.
2. `test_onboarding_chatbot_handles_llm_exception()`: Mock `app.agent.onboarding.nodes.onboarding_llm.invoke` to raise an `Exception`. Assert that `onboarding_chatbot` returns the fallback string.

### Explicit Constraints & Warnings

- **DO NOT alter `app/api/routes.py`**: The top-level `try/except` around `service.process_message()` in FastAPI must remain. It is the final safety net for totally unhandled infrastructural errors (e.g., database disconnections, threading issues). Ticket 7.2 specifically addresses *predictable LLM latency/quota failures* deep inside the graph.
- **DO NOT attempt to use LangGraph's native `RetryPolicy` inside the node configuration**: The Python Google GenAI SDK already implements exponential backoff. If it fails, the network is genuinely saturated. Forcing LangGraph to blindly retry a failing node will just hang the user's HTTP request for 60+ seconds. Failing fast with a polite message is the correct UX.

### Acceptance Criteria

- **[Automated]** The new resilience unit tests in `test_agent.py` pass, proving `main_chatbot` and `onboarding_chatbot` return `AIMessage` fallbacks when their internal `.invoke()` methods raise exceptions.
- **[Manual — Graph Integrity]** Disconnect from the internet (or temporarily corrupt your `GEMINI_API_KEY` in `.env`). Send a message "Find me Python jobs". The frontend should immediately render the fallback message ("I'm sorry, I'm having trouble connecting..."). Refresh the page. The user's query ("Find me Python jobs") and the fallback message MUST appear in the chat history, proving the LangGraph checkpointer was successfully invoked and state was preserved despite the LLM failure.
