# Sprint V2: Search Ledger — Persistent Search Memory

**Branch:** `migration-v2`
**Status:** ARCHIVED — declared landed by Sprint V3 on 2026-08-08.

## Owner Decisions (Binding)

1. The Search Ledger is a **flat log** — one entry per search executed. No deduplication, no hashing, no similarity matching.
2. The **LLM is the decision-maker**. It reads the ledger and decides whether to skip, paginate, or re-run a query. No programmatic dedup logic.
3. `has_more` is derived from `results_count >= FETCH_NUM_PAGES * 10` (computed at call time, not a separate constant). Single source of truth — if `FETCH_NUM_PAGES` changes, `has_more` adjusts automatically.
4. `fresh_count` is recorded so the LLM can gauge query exhaustion (e.g., 2 fresh out of 10 = mostly seen).
5. Ledger entries are **never deleted by the agent** — only by `reset_discovery_state`. They accumulate across sessions.
6. The ledger is loaded in `fetch_profile` and injected into the system prompt alongside profile/preferences. Same pattern as existing context injection.

## Dependency Graph

```
Ticket 1 (Schema + Store methods) ──► Ticket 2 (Read path: state, fetch, prompt)
                                  └──► Ticket 3 (Write path: log after search + tests)
                                           │
                                           ▼
                                  Ticket 2 must also be done before Ticket 3
```

---

## Ticket 1: Search Ledger Schema & ProfileService Methods

### Overview
Define the `SearchLedgerEntry` Pydantic model and add two new `ProfileService` methods (`get_search_ledger`, `log_search`) to read/write ledger entries from the LangGraph Store. This is data shapes and store access only — no graph or prompt changes.

### Implementation Steps

1. **New Pydantic Model — `app/agent/memory_schema.py`**:
   Add `SearchLedgerEntry` after the existing `SeenJob` class:
   ```python
   class SearchLedgerEntry(BaseModel):
       """Record of a single job search execution.
       Stored under (user_id, 'search_ledger') namespace in the LangGraph Store.
       The LLM reads these entries to avoid repeating searches and to discover
       unexplored pages.
       """

       query: str = Field(..., description="Raw query string passed to JSearch (e.g., 'Python Developer in London')")
       country: str = Field(..., description="2-letter ISO country code used in the search")
       remote_only: bool = Field(default=False, description="Whether remote_only filter was applied")
       page: int = Field(..., description="Page number that was fetched")
       results_count: int = Field(..., description="Total number of jobs returned by the API for this page")
       fresh_count: int = Field(..., description="Number of jobs that were new (not previously seen)")
       has_more: bool = Field(..., description="True if results_count >= expected page size, indicating more pages exist")
       searched_at: str = Field(..., description="ISO 8601 timestamp of when this search was executed")
   ```

2. **No new constant needed.** `has_more` is computed inside `log_search` as `results_count >= FETCH_NUM_PAGES * 10`. This derives the expected max from the existing `FETCH_NUM_PAGES` constant (`app/agent/constants.py`), which is the single source of truth for how many pages `fetch_jobs` requests. If `FETCH_NUM_PAGES` ever changes, `has_more` adjusts automatically — no second constant to keep in sync.

3. **New ProfileService methods — `app/services/profile_service.py`**:

   **`get_search_ledger`**:
   ```python
   async def get_search_ledger(self, user_id: str = DEFAULT_USER_ID) -> list[dict[str, Any]]:
       """Fetch all search ledger entries, sorted by searched_at (most recent first)."""
       items = await self._store.asearch((user_id, "search_ledger"), limit=100)
       entries = [item.value for item in items if item.value]
       return sorted(entries, key=lambda e: e.get("searched_at", ""), reverse=True)
   ```
   **IMPORTANT:** `asearch()` has a default limit (typically 10). The ledger accumulates across sessions and will exceed 10 entries. Always pass `limit=100` to avoid silent truncation.

   **`log_search`**:
   ```python
   async def log_search(
       self,
       input_data: "JobSpecialistInput",
       results_count: int,
       fresh_count: int,
       user_id: str = DEFAULT_USER_ID,
   ) -> None:
       """Persist a search ledger entry after a job search execution."""
       from app.agent.constants import FETCH_NUM_PAGES

       expected_max = FETCH_NUM_PAGES * 10  # JSearch returns 10 results per page
       entry = SearchLedgerEntry(
           query=input_data.query,
           country=input_data.country,
           remote_only=input_data.remote_only,
           page=input_data.page,
           results_count=results_count,
           fresh_count=fresh_count,
           has_more=results_count >= expected_max,
           searched_at=datetime.now(UTC).isoformat(),
       )
       key = str(uuid4())
       await self._store.aput((user_id, "search_ledger"), key, entry.model_dump())
       logger.info(
           "Search logged to ledger",
           query=entry.query,
           country=entry.country,
           page=entry.page,
           results_count=results_count,
           fresh_count=fresh_count,
           has_more=entry.has_more,
       )
   ```

   Add `SearchLedgerEntry` to the import from `app.agent.memory_schema` at the top of the file.

4. **Update `reset_discovery_state` — `app/services/profile_service.py`**:
   Add `"search_ledger"` to the namespace list in the existing loop:
   ```python
   for namespace_key in ("pending_jobs", "seen_jobs", "decisions", "search_ledger"):
   ```

5. **Tests — `tests/unit/test_profile_service.py`** (extend or create):
   - `test_search_ledger_entry_validates`: Construct a `SearchLedgerEntry` with valid data. Assert all fields round-trip through `.model_dump()` / `model_validate()`.
   - `test_search_ledger_entry_rejects_missing_query`: Omitting `query` raises `ValidationError`.
   - `test_log_search_persists_entry`: Create an `InMemoryStore`, instantiate `ProfileService`, call `log_search` with a `JobSpecialistInput(query="Python London", country="gb")` and `results_count=10, fresh_count=7`. Then call `get_search_ledger`. Assert 1 entry returned with correct `query`, `country`, `results_count`, `fresh_count`, `has_more=True`, and a valid `searched_at` timestamp.
   - `test_log_search_has_more_false_when_under_page_size`: Call `log_search` with `results_count=6`. Assert the entry has `has_more=False`. (Threshold is `FETCH_NUM_PAGES * 10 = 10`.)
   - `test_get_search_ledger_returns_sorted_by_most_recent`: Log 3 searches with staggered timestamps. Assert `get_search_ledger` returns them most-recent-first.
   - `test_get_search_ledger_empty_store`: Assert `get_search_ledger` returns `[]` on a fresh store.
   - `test_reset_discovery_state_clears_ledger`: Log a search, call `reset_discovery_state`, assert `get_search_ledger` returns `[]`.

### Explicit Constraints & Warnings
- **Do NOT modify any graph, node, prompt, or state code in this ticket.** This is schema, store methods, and constants only.
- **Do NOT add deduplication logic.** Every call to `log_search` writes a new entry. The LLM handles overlap reasoning.
- `SearchLedgerEntry` deliberately excludes `date_posted` — as discussed, the filter value is meaningless for comparison. What matters is `searched_at` (when it actually ran) and `has_more` / `fresh_count` (what it found).
- The `log_search` method takes `JobSpecialistInput` directly (not raw args) to ensure type safety. Use a string-style forward reference (`"JobSpecialistInput"`) in the type hint to avoid circular imports, with the actual import inside the function body.
- `has_more` derivation: `results_count >= FETCH_NUM_PAGES * 10`. Computed at call time inside `log_search` — no separate constant. `FETCH_NUM_PAGES` (currently `1`) is the single source of truth. JSearch returns 10 results per page, so `1 * 10 = 10` is the expected max. If `FETCH_NUM_PAGES` ever changes, this adjusts automatically.

### Acceptance Criteria
- [Automated] All 7 new tests pass.
- [Automated] All existing tests in `tests/unit/test_profile_service.py` (if any) and `tests/integration/` continue to pass.
- [Automated] `mypy` passes on `app/agent/memory_schema.py` and `app/services/profile_service.py`.

---

## Ticket 2: Read Path — Load Ledger into State & Inject into System Prompt

### Overview
Load the search ledger in `fetch_profile`, add it to `DiscoveryAgentState`, format it into a compact block, and inject it into the system prompt so the LLM can reason about its search history.

### Implementation Steps

1. **New state field — `app/agent/discovery/state.py`**:
   Add to `DiscoveryAgentState`:
   ```python
   search_ledger: NotRequired[list[dict[str, Any]]]
   ```
   This field is hydrated by `fetch_profile` and read by `main_chatbot` for prompt injection. It is **never** written by the agent — only by `fetch_profile` on each turn.

2. **Load ledger in `fetch_profile` — `app/agent/main/nodes.py`**:
   In the `fetch_profile` function, add a store search for the search ledger namespace alongside the existing parallel fetches:
   ```python
   profile_item, prefs_items, decisions_items, ledger_items = await asyncio.gather(
       store.aget(namespace_profile, "data"),
       store.asearch(namespace_prefs),
       store.asearch(namespace_decisions),
       store.asearch((user_id, "search_ledger"), limit=100),
   )
   ```
   **IMPORTANT:** Pass `limit=100` on the `search_ledger` call. `asearch()` defaults to ~10 results, and the ledger accumulates across sessions. Without the explicit limit, older entries are silently dropped.

   Process the ledger items:
   ```python
   search_ledger = sorted(
       [item.value for item in ledger_items if item.value],
       key=lambda e: e.get("searched_at", ""),
       reverse=True,
   )
   ```
   Add to the return patch:
   ```python
   patch: dict[str, Any] = {
       "user_profile": profile_dict,
       "preferences": preferences,
       "recent_decisions": recent_decisions,
       "search_ledger": search_ledger,
   }
   ```
   Update the completion log to include `ledger_count=len(search_ledger)`.

3. **New formatting helper — `app/agent/main/nodes.py`**:
   Add after the existing `_format_preferences_summary`:
   ```python
   def _format_search_ledger(ledger: list[dict[str, Any]]) -> str | None:
       """Format search ledger into a compact block for the system prompt.
       Returns None when empty so the caller can omit the section entirely.
       """
       if not ledger:
           return None

       lines: list[str] = []
       for entry in ledger:
           query = entry.get("query", "?")
           country = entry.get("country", "?")
           page = entry.get("page", "?")
           results = entry.get("results_count", 0)
           fresh = entry.get("fresh_count", 0)
           has_more = entry.get("has_more", False)
           searched_at = entry.get("searched_at", "?")

           more_tag = " [MORE PAGES AVAILABLE]" if has_more else ""
           lines.append(f'- "{query}" (country={country}, page={page}) → {results} results, {fresh} fresh{more_tag} — {searched_at}')
       return "\n".join(lines)
   ```
   This produces lines like:
   ```
   - "Python Developer in London" (country=gb, page=1) → 10 results, 7 fresh [MORE PAGES AVAILABLE] — 2026-03-15T14:30:00+00:00
   - "React Developer in London" (country=gb, page=1) → 5 results, 5 fresh — 2026-03-15T14:25:00+00:00
   ```

4. **Inject into system prompt — `app/agent/main/nodes.py`**:
   In `main_chatbot`, after the existing `feedback_block` construction:
   ```python
   ledger = state.get("search_ledger", [])
   ledger_summary = _format_search_ledger(ledger)
   search_history_block = (
       f"\n**SEARCH HISTORY (your previous searches this session):**\n{ledger_summary}\n"
       "Use this history to avoid repeating the same searches. "
       "If a search shows [MORE PAGES AVAILABLE], you can fetch the next page instead of re-running the same query. "
       "If a search has low fresh_count relative to results, that query is mostly exhausted.\n"
       if ledger_summary
       else ""
   )
   ```
   Add `search_history_block=search_history_block` to the `SYSTEM_PROMPT.format(...)` call.

5. **Update system prompt template — `app/agent/main/prompts.py`**:
   Add the `{search_history_block}` placeholder after `{feedback_block}`:
   ```python
   {feedback_block}{search_history_block}**MEMORY INSTRUCTIONS:**
   ```
   This slots the search history between the feedback section and the memory instructions, giving the LLM awareness of its search history before it decides what tool to call.

6. **Tests — `tests/unit/test_main_nodes.py`** (extend existing file):
   - `test_format_search_ledger_none_returns_none`: Assert `_format_search_ledger([])` returns `None`.
   - `test_format_search_ledger_formats_entries`: Provide 2 ledger entries (one with `has_more=True`, one with `has_more=False`). Assert the output contains `[MORE PAGES AVAILABLE]` for the first and not the second.
   - `test_format_search_ledger_includes_all_fields`: Assert output contains query, country, page, results_count, fresh_count, and searched_at values.
   - `test_fetch_profile_loads_search_ledger`: Mock the store to return 2 ledger items. Assert the returned patch contains `search_ledger` with 2 entries sorted by `searched_at` descending.
   - `test_main_chatbot_includes_search_history_in_prompt`: Provide state with a non-empty `search_ledger`. Mock `main_llm.invoke`. Capture the messages passed to `invoke`. Assert the system message content contains `"SEARCH HISTORY"` and the query text from the ledger.
   - `test_main_chatbot_omits_search_history_when_empty`: Provide state with empty `search_ledger`. Assert the system message does NOT contain `"SEARCH HISTORY"`.
   - `test_system_prompt_template_accepts_search_history_block`: Smoke test — call `SYSTEM_PROMPT.format(name="x", role="x", profile_summary="x", preferences_summary="x", feedback_block="", search_history_block="", max_search_attempts=5)`. Assert it does NOT raise `KeyError`. This catches template/format-call mismatches.

### Explicit Constraints & Warnings
- **Do NOT write ledger entries in this ticket.** This is the read path only. The write path is Ticket 3.
- **The `search_ledger` state field is `NotRequired`** — existing callers that don't provide it (like the Profile workspace) are unaffected.
- The ledger block is **conditionally injected** (same pattern as `feedback_block`) — when there's no search history, the prompt is unchanged from current behavior.
- **Do NOT cap the ledger entries** in `fetch_profile`. Load all of them. The ledger grows slowly (one entry per search, max ~5 per conversation turn) and the formatted output is compact (~100 chars per line). Token cost is negligible.
- **Error isolation for the 4th gather awaitable:** Use `return_exceptions=True` on the `asyncio.gather` call, then handle the ledger result defensively. If `ledger_items` is an `Exception` instance (e.g., store namespace doesn't exist), treat it as an empty list and log a warning. Profile, preferences, and decisions must NOT be lost because the ledger fetch failed.
- When testing `main_chatbot`, mock the `main_llm` at `app.agent.main.nodes.main_llm` — the existing test pattern.

### Acceptance Criteria
- [Automated] All 7 new tests pass.
- [Automated] All existing tests in `test_main_nodes.py` and `test_fetch_profile` pass without modification (the new field is `NotRequired`).
- [Automated] `mypy` passes on `app/agent/main/nodes.py`, `app/agent/main/prompts.py`, `app/agent/discovery/state.py`.
- [Manual] Start the backend. Send a search request. Confirm the server logs show `ledger_count=0` on the first turn (no history yet).

---

## Ticket 3: Write Path — Log Search After Execution & Integration Tests

### Overview
After every `fetch_jobs` call, write a `SearchLedgerEntry` to the store via `ProfileService.log_search`. This closes the loop: searches are logged → loaded on next turn → LLM reads history → makes informed search decisions.

### Implementation Steps

1. **Pass `ProfileService` into `_run_single_job_search` — `app/agent/discovery/graph.py`**:
   Update the function signature to accept `profile_service`:
   ```python
   async def _run_single_job_search(
       tool_call: Any,
       seen_ids: set[str],
       user_profile: dict[str, Any] | None,
       preferences: dict[str, Any] | None,
       profile_service: ProfileService,
   ) -> tuple[ToolMessage, list[dict[str, Any]], list[JobListing]]:
   ```
   Update the call site in `call_job_specialist` to pass `profile_service`:
   ```python
   results = await asyncio.gather(*[_run_single_job_search(tc, seen_ids, user_profile, preferences, profile_service) for tc in job_tool_calls_to_run])
   ```

2. **Log search after fetch + dedup — `app/agent/discovery/graph.py`**:
   Inside `_run_single_job_search`, after step 2 (dedup) and before step 3 (subgraph invocation), add the ledger write:
   ```python
   # 2. Dedup using the shared seen_ids snapshot
   fresh, seen = _split_fresh_seen(all_listings, seen_ids)

   # 2.5 Log this search to the ledger
   await profile_service.log_search(
       input_data=input_data,
       results_count=len(all_listings),
       fresh_count=len(fresh),
   )

   # 3. Invoke 2-node subgraph...
   ```
   The ledger entry is written **per search**, immediately after fetch, regardless of whether the subgraph succeeds or fails. This ensures the LLM knows a search was attempted even if summarization timed out.

3. **Update existing test call sites**:
   The signature change to `_run_single_job_search` (new `profile_service` parameter) will break any existing tests that call it directly. Search for all direct calls in:
   - `tests/integration/test_job_specialist_pipeline.py`
   - `tests/unit/test_discovery_graph.py` (if exists)

   Update every call to pass a mock `ProfileService` (with `log_search` as an `AsyncMock`) as the new last parameter. Do NOT skip this — the tests will fail with `TypeError: missing required argument`.

4. **New tests — `tests/unit/test_discovery_graph.py`** (extend or create):
   - `test_run_single_job_search_logs_to_ledger`: Mock `jsearch_api_search` to return 8 jobs. Set `seen_ids` to contain 3 IDs that overlap with the 8 returned jobs (e.g., jobs with IDs `"id_1"`, `"id_2"`, `"id_3"`). Mock `profile_service.log_search`. Call `_run_single_job_search`. Assert `log_search` was called once with `results_count=8` and `fresh_count=5` (8 total minus 3 seen).
   - `test_run_single_job_search_logs_even_on_zero_results`: Mock `jsearch_api_search` to return empty list. Assert `log_search` was called with `results_count=0, fresh_count=0`.
   - `test_run_single_job_search_logs_before_subgraph`: Mock both `log_search` and `job_search_graph.ainvoke`. Make `ainvoke` raise `Exception`. Assert `log_search` was still called (it runs before subgraph). Note: this validates the ordering — ledger write happens before summarization.
   - `test_call_job_specialist_passes_profile_service`: Mock internals. Assert that `_run_single_job_search` receives the `profile_service` instance from `call_job_specialist`.

5. **Integration test — `tests/integration/test_search_ledger.py`** (new file):
   - `test_ledger_round_trip_through_pipeline`: Using `InMemoryStore`:
     1. Create `ProfileService` with the store.
     2. Execute `_run_single_job_search` with mocked JSearch (returns 10 jobs) and mocked LLM.
     3. Call `get_search_ledger`.
     4. Assert 1 entry with correct `query`, `results_count=10`, `has_more=True`.
     5. Execute a second search with different query.
     6. Call `get_search_ledger`.
     7. Assert 2 entries, most recent first.
   - `test_ledger_visible_to_fetch_profile`: Using `InMemoryStore`:
     1. Log 2 searches via `ProfileService.log_search`.
     2. Call `fetch_profile` (mock the profile/prefs/decisions namespaces as empty).
     3. Assert the returned patch contains `search_ledger` with 2 entries.
   - `test_reset_clears_ledger`: Log searches, call `reset_discovery_state`, assert ledger is empty.

### Explicit Constraints & Warnings
- **The ledger write is NOT inside the `asyncio.gather` for subgraph invocation.** It happens sequentially after fetch + dedup but before subgraph. This is intentional — we want the record even if summarization fails.
- **Do NOT batch ledger writes** like `mark_jobs_seen`. Each search logs independently because the ledger entry includes per-search metadata (`results_count`, `fresh_count`, `has_more`).
- **`_run_single_job_search` signature change is BREAKING.** The new `profile_service` parameter must be added to every existing call site and every existing test that calls this function directly. Failing to update existing tests will produce `TypeError: missing required argument`. Step 3 explicitly lists the files to audit.
- **Do NOT add any dedup or skip logic.** The write path is unconditional — every search gets logged. The LLM decides what to do with the history on the read side.

### Acceptance Criteria
- [Automated] All 4 new unit tests and 3 new integration tests pass.
- [Automated] All **existing** tests in `test_discovery_graph.py`, `test_job_specialist_pipeline.py`, and `test_main_nodes.py` pass (after updating call sites per Step 3).
- [Automated] `mypy` passes on `app/agent/discovery/graph.py`.
- [Manual] Start the backend. Send "Find me Python jobs in London". Check server logs for `"Search logged to ledger"` with `results_count` and `has_more`. Send the same query again. Check that the system prompt (visible in debug logs) now contains `"SEARCH HISTORY"` with the previous search entry.

---

## Review Checklist

- [ ] No programmatic dedup logic — the LLM is the decision-maker.
- [ ] No hash-based key — ledger entries use UUID keys.
- [ ] `SearchLedgerEntry` excludes `date_posted` (meaningless for comparison).
- [ ] `has_more` derived from `results_count >= FETCH_NUM_PAGES * 10` (single source of truth, no separate constant).
- [ ] `asearch` calls on `search_ledger` namespace pass `limit=100` (avoids silent truncation at default ~10).
- [ ] `asyncio.gather` in `fetch_profile` uses `return_exceptions=True` — ledger fetch failure doesn't crash profile loading.
- [ ] Existing tests updated for `_run_single_job_search` signature change (new `profile_service` param).
- [ ] Template smoke test verifies `SYSTEM_PROMPT.format()` accepts `search_history_block` without `KeyError`.
- [ ] Ledger loaded in `fetch_profile` alongside existing context (same pattern).
- [ ] Ledger injected conditionally — empty ledger = no prompt change.
- [ ] Ledger write happens before subgraph invocation (survives summarization failures).
- [ ] `reset_discovery_state` clears `search_ledger` namespace.
- [ ] No backward compatibility needed — new `NotRequired` field, clean addition.
