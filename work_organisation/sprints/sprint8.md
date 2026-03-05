# Sprint 8: Agent Performance & Execution Correctness

## Goal
Fix four structural defects identified via production trace analysis that degrade response latency and cause silent execution failures. The highest-priority issue (Ticket 8.1) costs one full LLM round-trip and a required user re-prompt on every onboarding completion. Ticket 8.2 fixes a correctness bug where the LLM's parallel tool calls are silently dropped. Tickets 8.3 and 8.4 are lower-effort latency optimisations.

**Implementation order: 8.1 → 8.2 → 8.3 → 8.4** (8.4 depends on 8.1's trigger marker).

---

## Ticket 8.1: Backend — Fix "Ghost Start" After Onboarding Handoff — DONE

### Overview
After `finalize_profile` completes, the graph transitions to `FETCH_PROFILE_NODE → MAIN_CHATBOT_NODE`. The main chatbot sees the onboarding history, generates "I'll start looking now!" with **no tool calls**, and routes to `END`. The user must send a follow-up prompt to trigger the actual search. This ticket injects a synthetic trigger `HumanMessage` during the handoff so the main chatbot immediately begins searching, and filters it from the history returned to the frontend.

### Implementation Steps

1. **Add `_is_fresh_onboarding_handoff` helper in `app/agent/main/nodes.py`**:

   Add the following at the top of the file, after the existing imports:
   ```python
   from langchain_core.messages import HumanMessage, ToolMessage
   ```
   Then add the helper function:
   ```python
   def _is_fresh_onboarding_handoff(messages: list[BaseMessage]) -> bool:
       """
       Returns True when the most recent message in state is the ToolMessage
       emitted by finalize_profile (content contains "Onboarding complete").
       This is the signal that the graph has just transitioned from onboarding.

       NOTE: This relies on no intermediate node existing between
       ONBOARDING_TOOLS_NODE and FETCH_PROFILE_NODE in graph.py. If a node
       is ever inserted there, this detection will break silently.
       """
       if not messages:
           return False
       last = messages[-1]
       return isinstance(last, ToolMessage) and "Onboarding complete" in str(last.content)
   ```

2. **Inject a trigger message in `fetch_profile` in `app/agent/main/nodes.py`**:

   At the end of `fetch_profile`, replace the final `return` statement with:
   ```python
   patch: dict[str, Any] = {
       "user_profile": profile_dict,
       "preferences": preferences,
       "recent_decisions": recent_decisions,
   }

   current_messages: list[BaseMessage] = state.get(MESSAGES_KEY, [])  # type: ignore
   if _is_fresh_onboarding_handoff(current_messages):
       trigger = HumanMessage(
           content=(
               "[SYSTEM TRIGGER] Onboarding is now complete. "
               "The user's profile and preferences have been loaded above. "
               "Begin searching for matching jobs immediately using job_specialist_tool. "
               "Do NOT greet the user or ask clarifying questions — go straight to searching."
           )
       )
       patch["messages"] = [trigger]
       logger.info("Onboarding handoff detected: injecting search trigger into messages")

   return patch
   ```
   > **Note on the reducer**: `AgentState.messages` uses `operator.add` as its reducer (`state.py:12`). Assigning `patch["messages"] = [trigger]` appends the single `HumanMessage` to the existing list — it does **not** replace history.

3. **No graph topology change required**: The edge `FETCH_PROFILE_NODE → MAIN_CHATBOT_NODE` (`graph.py:133`) remains unchanged.

4. **Filter the trigger from `get_history` in `app/services/chat_service.py`**:

   In `get_history`, the `for msg in messages` loop begins at line 183. At the start of the loop body, before the existing `isinstance(msg, HumanMessage)` check, add a guard to skip system trigger messages:
   ```python
   for msg in messages:
       # Filter out internal system trigger messages — never expose to the frontend
       if isinstance(msg, HumanMessage) and str(msg.content).startswith("[SYSTEM TRIGGER]"):
           continue
       if isinstance(msg, HumanMessage):
           # ... existing logic unchanged
   ```

### Explicit Constraints & Warnings

- **The trigger must be a `HumanMessage`**: An `AIMessage` or `SystemMessage` would break the alternating Human/AI turn structure that Gemini expects. `HumanMessage` is the correct type for injected system directives in this architecture.
- **The `[SYSTEM TRIGGER]` prefix is a contract across tickets 8.1 and 8.4**: Ticket 8.4's `_strip_onboarding_messages` uses this prefix as the phase-boundary marker. Do not change the prefix string.
- **DO NOT modify `route_after_onboarding_tools` in `app/agent/onboarding/nodes.py`**: The routing to `FETCH_PROFILE_NODE` is already correct. This ticket only changes what happens after that routing decision.

### Acceptance Criteria

- **[Automated]** Add `test_fetch_profile_injects_trigger_on_handoff` in `tests/unit/test_main_nodes.py`:
  - Build a mock `AgentState` where `messages` ends with a `ToolMessage(content="Onboarding complete — handing off to job hunting agent.", tool_call_id="x")`.
  - Mock `store.aget` and `store.asearch` to return minimal valid values.
  - Call `fetch_profile(state, config, store)`.
  - Assert the returned dict contains a `"messages"` key with exactly one `HumanMessage` whose content starts with `"[SYSTEM TRIGGER]"`.
- **[Automated]** Add `test_fetch_profile_no_trigger_on_normal_turn` in `tests/unit/test_main_nodes.py`:
  - Build a mock `AgentState` where `messages` ends with a `HumanMessage(content="Find me Python jobs")`.
  - Assert the returned dict does **not** contain a `"messages"` key.
- **[Automated]** Add `test_get_history_filters_system_trigger` in `tests/unit/test_chat_service.py`:
  - Build a mock graph state whose `messages` list contains: `HumanMessage("Hi")`, `AIMessage("Hello")`, `HumanMessage("[SYSTEM TRIGGER] ...")`, `AIMessage("Here are jobs...")`.
  - Call `get_history`.
  - Assert the returned history list contains exactly **1** turn (the "Hi" / "Hello" pair — or the jobs turn paired with nothing), and that no turn has `user_message` starting with `"[SYSTEM TRIGGER]"`.
- **[Manual]** Complete a full onboarding flow (upload CV, answer preference questions). Verify in server logs that after `finalize_profile` executes, the **very next graph turn** includes a `job_specialist_tool` call — no intermediate "I'll start looking" AI message appears.

---

## Ticket 8.2: Backend — Fix Parallel `job_specialist_tool` Calls Being Silently Dropped — DONE

### Overview
When the main LLM emits an `AIMessage` with multiple `job_specialist_tool` entries in `tool_calls`, `call_job_specialist` in `graph.py` processes only `tool_calls[0]` and discards the rest. The LLM receives an AIMessage referencing N tool_call_ids but only 1 `ToolMessage` response — invalid per the Gemini API contract. This ticket fixes the node to execute all parallel calls concurrently, and fixes `route_main` to route on the *presence* of `job_specialist_tool` anywhere in `tool_calls` rather than only inspecting index 0.

### Known Limitation (document, do not fix)
If the LLM emits a mixed-type batch (e.g., `[job_specialist_tool, save_preference]` in one `AIMessage`), routing to `JOB_SPECIALIST_NODE` will cause the `save_preference` call to be silently dropped by that node (which only handles job searches). The system prompt must be the enforcement layer: it must instruct the LLM never to mix `job_specialist_tool` with other tools in a single response. Add the following line to the **"JOB SEARCH INSTRUCTIONS"** section of `app/agent/main/prompts.py`:
```
* **NEVER mix `job_specialist_tool` with other tools in a single response.** Call `job_specialist_tool` alone or call memory tools alone — never both in the same turn.
```
This documented limitation and the prompt constraint together are the accepted solution. No runtime splitting of mixed `AIMessage` tool_calls is implemented.

### Implementation Steps

1. **Extract per-call logic into `_run_single_job_search` helper in `app/agent/graph.py`**:

   Add `import asyncio` at the top of `app/agent/graph.py` if not already present.

   Add the following private helper above `call_job_specialist`:
   ```python
   async def _run_single_job_search(
       tool_call: dict[str, Any],
       profile_service: ProfileService,
   ) -> ToolMessage:
       """
       Execute one job_specialist_tool call through the job search subgraph.
       Always returns a ToolMessage — errors are caught and encoded as content strings.
       """
       tool_call_id = tool_call["id"]
       try:
           args = tool_call["args"]
           input_data = JobSpecialistInput(**args)
       except Exception as e:
           return ToolMessage(content=f"Error parsing input: {e}", tool_call_id=tool_call_id)

       subgraph_state: JobSpecialistState = {"input": input_data, "search_results": None}
       result = await job_search_graph.ainvoke(cast(Any, subgraph_state))
       results: list[JobListing] = result.get("search_results", [])

       seen_ids = await profile_service.get_seen_job_ids(DEFAULT_USER_ID)
       fresh = [r for r in results if r.id not in seen_ids]
       seen = [r for r in results if r.id in seen_ids]
       await profile_service.mark_jobs_seen(fresh, DEFAULT_USER_ID)

       fresh_payload = [r.model_dump() for r in fresh]
       seen_payload = [
           {"id": r.id, "title": r.title, "company": r.company, "location": r.location}
           for r in seen
       ]
       content = json.dumps({"fresh": fresh_payload, "seen": seen_payload}, indent=2)
       return ToolMessage(content=content, tool_call_id=tool_call_id)
   ```
   > **Note on the `seen_ids` race condition**: Two concurrent calls may both read the same `seen_ids` snapshot before either writes back, causing a job in both results to appear `fresh` twice. This is an accepted trade-off — minor duplication vs. sequential bottleneck. Do NOT add a mutex.

2. **Rewrite `call_job_specialist` in `app/agent/graph.py`**:

   Replace the entire function body with:
   ```python
   async def call_job_specialist(
       state: AgentState,
       profile_service: ProfileService,
   ) -> dict[str, Any]:
       messages = state["messages"]
       last_message = messages[-1]
       if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
           return {"messages": []}

       job_tool_calls = [
           tc for tc in last_message.tool_calls if tc["name"] == "job_specialist_tool"
       ]
       if not job_tool_calls:
           return {"messages": []}

       current_attempts = state.get("search_attempts", 0)

       tool_messages = await asyncio.gather(
           *[_run_single_job_search(tc, profile_service) for tc in job_tool_calls]
       )

       # Increment by 1 per batch (preserves "number of search rounds" semantics,
       # consistent with the loop protection threshold and the system prompt's
       # "3 total search attempts" instruction).
       return {
           "messages": list(tool_messages),
           "search_attempts": current_attempts + 1,
       }
   ```

3. **Fix `route_main` in `app/agent/main/nodes.py` to route on presence, not position**:

   Replace the current routing logic (lines 207–218) with:
   ```python
   def route_main(state: AgentState) -> str:
       """Route main agent output: tool calls, final_answer, or end."""
       messages = cast(list[BaseMessage], state.get(MESSAGES_KEY, []))
       ai_message = messages[-1] if messages else None

       if not (isinstance(ai_message, AIMessage) and ai_message.tool_calls):
           return str(END)

       tool_names = {tc["name"] for tc in ai_message.tool_calls}

       if FINAL_ANSWER_TOOL_NAME in tool_names:
           return str(END)

       if "job_specialist_tool" in tool_names:
           if state.get("search_attempts", 0) >= 3:
               logger.warning("Loop protection: max search attempts reached, forcing END")
               return str(END)
           return JOB_SPECIALIST_NODE

       return MAIN_TOOLS_NODE
   ```

4. **Update `app/agent/main/prompts.py`** — add the mixed-tool constraint as described in the Known Limitation section above.

### Explicit Constraints & Warnings

- **DO NOT use `asyncio.gather(return_exceptions=True)`**: `_run_single_job_search` already catches all errors internally and returns a `ToolMessage`. Using `return_exceptions=True` would require a second pass to convert `Exception` objects, adding unnecessary complexity.
- **`search_attempts` increments by 1 per batch, not per API call**: This preserves the existing semantic ("number of search rounds") that the system prompt's "3 total search attempts" instruction refers to. The loop protection threshold of `3` in `route_main` remains unchanged.
- **DO NOT change `job_search_graph.ainvoke`**: The subgraph is already async and safe for concurrent invocation.

### Acceptance Criteria

- **[Automated]** Add `test_call_job_specialist_processes_all_parallel_calls` in `tests/unit/test_job_specialist_nodes.py`:
  - Build an `AgentState` whose last message is a mock `AIMessage` with 3 `tool_calls`, all named `"job_specialist_tool"` with different queries.
  - Mock `job_search_graph.ainvoke` to return `{"search_results": []}`.
  - Mock `profile_service.get_seen_job_ids` to return `set()` and `profile_service.mark_jobs_seen` as a no-op.
  - Assert the returned `"messages"` list contains exactly **3** `ToolMessage` objects.
  - Assert `"search_attempts"` in the return dict equals `1` (one batch = one increment).
- **[Automated]** Add `test_call_job_specialist_single_call_unchanged` — same setup but with 1 tool_call. Assert 1 `ToolMessage` returned and `search_attempts` equals `1`.
- **[Automated]** Add `test_route_main_detects_job_specialist_at_any_position` in `tests/unit/test_main_nodes.py`:
  - Build an `AIMessage` with `tool_calls = [{"name": "save_preference", ...}, {"name": "job_specialist_tool", ...}]`.
  - Assert `route_main` returns `JOB_SPECIALIST_NODE` (not `MAIN_TOOLS_NODE`).
- **[Manual]** Trigger a job search for a user with multiple applicable roles. Inspect server logs. Confirm `job_search_graph.ainvoke` is called N times (once per LLM tool_call) and that N `ToolMessage` entries appear in the subsequent `main_chatbot` input.

---

## Ticket 8.3: Backend — Parallelise `fetch_profile` Store Reads

### Overview
`fetch_profile` makes three independent async reads from the LangGraph store sequentially: profile, preferences, and decisions. These have no data dependency between them and can be collapsed into a single `asyncio.gather` call, eliminating two serial round-trips on every agent turn.

### Implementation Steps

1. **Add `import asyncio` to `app/agent/main/nodes.py`** if not already present after Ticket 8.1.

2. **Replace the three sequential store reads in `fetch_profile`**:

   ```python
   # BEFORE
   namespace_profile = (user_id, "profile")
   profile_item = await store.aget(namespace_profile, "data")

   namespace_prefs = (user_id, "preferences")
   prefs_items = await store.asearch(namespace_prefs)

   decisions_items = await store.asearch((user_id, "decisions"))

   # AFTER
   namespace_profile = (user_id, "profile")
   namespace_prefs = (user_id, "preferences")
   namespace_decisions = (user_id, "decisions")

   profile_item, prefs_items, decisions_items = await asyncio.gather(
       store.aget(namespace_profile, "data"),
       store.asearch(namespace_prefs),
       store.asearch(namespace_decisions),
   )
   ```

   All subsequent processing of `profile_item`, `prefs_items`, and `decisions_items` remains **exactly** as written.

### Explicit Constraints & Warnings

- **This is a pure mechanical refactor**: Only the store read lines and namespace variable declarations change. Do not touch any data processing logic below them.
- **Do NOT use `asyncio.gather(return_exceptions=True)`**: A store read failure is an infrastructure failure per `DESIGN_PRINCIPLES.md` §4. It must propagate as an unhandled exception, not be silently swallowed.

### Acceptance Criteria

- **[Automated]** Add `test_fetch_profile_reads_store_concurrently` in `tests/unit/test_main_nodes.py`:
  - Mock `store.aget` and `store.asearch` as async functions.
  - After calling `fetch_profile`, assert `store.aget` was called exactly once with `((user_id, "profile"), "data")`.
  - Assert `store.asearch` was called exactly twice: once with `(user_id, "preferences")` and once with `(user_id, "decisions")`.
  - Assert the call order does not matter (both `asearch` calls exist regardless of which returned first).

---

## Ticket 8.4: Backend — Strip Onboarding History from Main Agent Context

### Overview
On every turn after onboarding, `main_chatbot` receives the full message history including the entire onboarding conversation (CV text, preference-saving tool pairs, multi-turn Q&A). This data is already extracted and persisted to the store. Feeding it to the LLM inflates input token counts (~4,000+ surplus tokens per turn) and risks the model anchoring on stale context. This ticket adds a semantic filter in `main_chatbot` that strips all messages prior to the `[SYSTEM TRIGGER]` marker injected by Ticket 8.1.

**Dependency: Ticket 8.1 must be implemented first.** Without the `[SYSTEM TRIGGER]` marker, `_strip_onboarding_messages` returns the full list unchanged (safe fallback), but the token-reduction benefit does not activate.

### Implementation Steps

1. **Add `_strip_onboarding_messages` helper in `app/agent/main/nodes.py`**:

   ```python
   def _strip_onboarding_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
       """
       Remove all messages that predate the onboarding-to-main-agent handoff.
       The handoff is marked by the first HumanMessage whose content starts with
       '[SYSTEM TRIGGER]'. If no such marker exists (e.g., direct entry without
       onboarding, or Ticket 8.1 not yet deployed), the full list is returned unchanged.

       NOTE: trim_messages(..., start_on="human") runs after this filter. The
       [SYSTEM TRIGGER] HumanMessage will be the first message in the stripped list,
       satisfying the start_on="human" constraint. If this ticket is ever reverted
       without also reverting Ticket 8.1, the first post-strip message may be an
       AIMessage, which trim_messages would discard.
       """
       for i, msg in enumerate(messages):
           if isinstance(msg, HumanMessage) and str(msg.content).startswith("[SYSTEM TRIGGER]"):
               return messages[i:]
       return messages
   ```

2. **Apply the filter in `main_chatbot` in `app/agent/main/nodes.py`**, immediately before the existing `trim_messages` call (line ~167):

   ```python
   # Add this line immediately before the existing trim_messages call:
   messages = _strip_onboarding_messages(messages)

   trimmed_messages = trim_messages(
       messages,
       max_tokens=160_000,
       strategy="last",
       token_counter=len,
       include_system=False,
       allow_partial=False,
       start_on="human",
   )
   ```
   The `messages` variable reassigned here is the local variable from line 141 (`messages = state[MESSAGES_KEY]`). Reassigning it locally does **not** mutate graph state.

### Explicit Constraints & Warnings

- **DO NOT apply this filter in `onboarding_chatbot`**: The onboarding agent requires full history. This filter is exclusively for `main_chatbot`.
- **The filter runs before `trim_messages`, not instead of it**: `trim_messages` remains as the absolute character-count ceiling. The onboarding strip is a semantic filter that runs first.
- **History persistence is unaffected**: This only modifies the local `messages` variable before LLM invocation. The full history remains in the LangGraph checkpointer.
- **Revert order matters**: If this ticket is ever reverted, Ticket 8.1 must also be reverted or the `[SYSTEM TRIGGER]` marker must be preserved — otherwise `trim_messages` with `start_on="human"` may discard the first real AI message after stripping.

### Acceptance Criteria

- **[Automated]** Add `test_strip_onboarding_messages_removes_pre_trigger` in `tests/unit/test_main_nodes.py`:
  - Build: `[HumanMessage("Hi"), AIMessage("Hello"), HumanMessage("[SYSTEM TRIGGER] ..."), AIMessage("Searching...")]`.
  - Call `_strip_onboarding_messages(messages)`.
  - Assert the result contains exactly the last 2 messages (starting from the trigger).
- **[Automated]** Add `test_strip_onboarding_messages_passthrough_no_trigger`:
  - Build a list with no trigger marker.
  - Assert the returned list is identical to the input.
- **[Automated]** Add `test_main_chatbot_strips_onboarding_with_trigger` in `tests/unit/test_main_nodes.py`:
  - Build a full message list: several onboarding messages, then `HumanMessage("[SYSTEM TRIGGER] ...")`, then 2 post-onboarding messages.
  - Mock `main_llm.invoke` to capture the `all_messages` argument passed to it.
  - Call `main_chatbot(state)`.
  - Assert no message in the captured `all_messages` predates the trigger. This test **will fail** if Ticket 8.1 is absent, enforcing the dependency.
- **[Manual]** After completing onboarding, send 2 search messages. In LangSmith traces, inspect `input_tokens` on `main_chatbot`. The CV text (~2,000 tokens) and onboarding tool-call turns (~1,500 tokens) should not appear in the second search turn's context.
