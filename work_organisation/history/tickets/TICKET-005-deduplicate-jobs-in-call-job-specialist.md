# Ticket 005: Mark seen jobs and pass structured context to LLM in `call_job_specialist`

## Overview

Currently all jobs returned by `job_specialist_tool` are passed to the LLM as fresh results every time, even if the LLM has already processed them in a previous search. Silently dropping seen jobs would be wrong — the LLM needs to know the full search space to make good decisions. Instead, this ticket introduces a `seen_jobs` store namespace that tracks every job ID that has passed through `call_job_specialist`. On subsequent searches, results are split into `fresh` and `seen` buckets. Fresh jobs carry full data; seen jobs carry identity metadata only (`id`, `title`, `company`, `location`) — enough for the LLM to reason about them without polluting context with full descriptions. The LLM is instructed to filter and present only fresh jobs normally, treating seen jobs as background context.

**Prerequisite:** The system prompt must already contain the "Filter & Present Results" instruction with Lens 1 (CV Fit) and Lens 2 (Preferences). Verify that step 3 of `JOB SEARCH INSTRUCTIONS` in `app/agent/main/prompts.py` is titled "Filter & Present Results" — not the old "Present Results". The fresh/seen split depends on the LLM already knowing how to filter jobs.

---

## Touch Points

1. `app/agent/memory_schema.py` — add `SeenJob` schema
2. `app/agent/graph.py` — `call_job_specialist` node
3. `app/services/profile_service.py` — `mark_jobs_seen` and `get_seen_job_ids` methods
4. `app/agent/main/prompts.py` — update job search instructions to handle `fresh` / `seen` split

---

## Implementation Steps

### 1. Add `SeenJob` schema — `app/agent/memory_schema.py`

```python
class SeenJob(BaseModel):
    """
    Minimal identity record for a job that has already been processed by the LLM.
    Stored under (user_id, "seen_jobs") namespace.
    """

    id: str
    title: str
    company: str
    location: str
```

### 2. Add store methods — `app/services/profile_service.py`

```python
async def get_seen_job_ids(self, user_id: str = DEFAULT_USER_ID) -> set[str]:
    """Return the set of all job IDs previously processed by the LLM."""
    items = await self._store.asearch((user_id, "seen_jobs"))
    return {item.key for item in items if item.value}


async def mark_jobs_seen(self, jobs: list[JobListing], user_id: str = DEFAULT_USER_ID) -> None:
    """Persist minimal identity records for all jobs returned by a search."""
    for job in jobs:
        seen = SeenJob(id=job.id, title=job.title, company=job.company, location=job.location)
        await self._store.aput((user_id, "seen_jobs"), job.id, seen.model_dump())
```

### 3. Update `call_job_specialist` — `app/agent/graph.py`

Inject `profile_service` via `functools.partial` at compile time (same pattern as `fetch_profile`). Construct `ProfileService(store)` inside `get_compiled_graph` using the `store` parameter already available — no signature change to `get_compiled_graph` is needed:

```python
def get_compiled_graph(checkpointer: Any, store: BaseStore) -> Any:
    profile_service = ProfileService(store)
    ...
    builder.add_node(
        JOB_SPECIALIST_NODE,
        functools.partial(call_job_specialist, profile_service=profile_service),
    )
```

Inside `call_job_specialist`, split results into fresh and seen, then mark fresh as seen, and build a structured `ToolMessage`.

**The ordering of operations is critical:** (1) fetch existing seen IDs, (2) split results, (3) mark fresh jobs as seen. Do NOT mark before fetching — that would make all jobs appear "seen" immediately.

```python
async def call_job_specialist(
    state: AgentState,
    profile_service: ProfileService,
) -> dict[str, Any]:
    ...
    result = await job_search_graph.ainvoke(cast(Any, subgraph_state))
    results: list[JobListing] = result.get("search_results", [])

    # Step 1: Fetch existing seen IDs BEFORE marking anything
    seen_ids = await profile_service.get_seen_job_ids(DEFAULT_USER_ID)

    # Step 2: Split results into fresh (never seen) and seen (already processed)
    fresh = [r for r in results if r.id not in seen_ids]
    seen = [r for r in results if r.id in seen_ids]

    # Step 3: Mark fresh jobs as seen for next time (idempotent via store.aput)
    await profile_service.mark_jobs_seen(fresh, DEFAULT_USER_ID)

    # Build structured payload: full data for fresh, identity-only for seen
    fresh_payload = [r.model_dump() for r in fresh]
    seen_payload = [{"id": r.id, "title": r.title, "company": r.company, "location": r.location} for r in seen]

    output_content = json.dumps(
        {
            "fresh": fresh_payload,
            "seen": seen_payload,
        },
        indent=2,
    )

    return {
        "messages": [ToolMessage(content=output_content, tool_call_id=tool_call_id)],
        "search_attempts": current_attempts + 1,
    }
```

### 4. Update job search instructions — `app/agent/main/prompts.py`

Add a note to the "Search Jobs" section explaining the `ToolMessage` structure:

```
*   The tool returns a JSON object with two keys:
    - `"fresh"`: jobs not seen before — full data including description. Apply
      your CV fit and preference evaluation to these normally.
    - `"seen"`: jobs already processed in a previous search — identity only
      (id, title, company, location), no description. Do NOT include seen jobs
      in `final_answer` unless there are no fresh jobs that pass your evaluation,
      in which case you may acknowledge the situation and suggest broadening
      the search.
```

---

## Explicit Constraints & Warnings

- **Fetch `seen_ids` BEFORE marking new jobs.** The correct order is: (1) fetch existing seen IDs, (2) compute fresh vs seen, (3) mark fresh jobs as seen. Inverting steps 1 and 3 means all jobs would appear as "seen" immediately.
- **Marking is idempotent.** `store.aput` with the same key overwrites silently. Re-marking a job that's already seen is harmless.
- **`seen_jobs` is never pruned in this ticket.** It grows indefinitely. This is acceptable for now — each entry is ~50 tokens of metadata. A pruning strategy (e.g. cap at last 500) can be added later.
- **`get_compiled_graph` does NOT need a signature change.** Construct `ProfileService(store)` inside `get_compiled_graph` using the existing `store` parameter. Do not add `profile_service` to the function signature.
- **Do not store full job data in `seen_jobs`.** Only `SeenJob` (4 fields). The point is to minimise token cost when seen jobs appear in the `ToolMessage`.
- **Prerequisite: LLM filtering instructions must exist.** The system prompt must already contain the "Filter & Present Results" instruction (step 3 of `JOB SEARCH INSTRUCTIONS` in `prompts.py`). Without it, the LLM has no instruction on how to treat fresh vs seen jobs differently. Verify step 3 is titled "Filter & Present Results" before implementing.

---

## Acceptance Criteria

- **[Automated]** `pytest` passes. Add the following unit tests (suggested file: `tests/unit/test_seen_jobs.py`):
  - **`test_fresh_seen_split_mixed`**: Given a store with pre-existing seen job IDs `{"abc", "xyz"}` and search results `[JobListing(id="abc", ...), JobListing(id="new1", ...)]`, verify the `ToolMessage` content parses to `{"fresh": [<new1 full data>], "seen": [{"id": "abc", ...identity only...}]}`.
  - **`test_first_search_all_fresh`**: Given an empty store (no seen IDs), verify all results appear under `"fresh"` and `"seen"` is an empty list.
  - **`test_all_results_already_seen`**: Given a store where every returned job ID is already seen, verify `"fresh"` is an empty list and all results appear under `"seen"` with identity-only fields.
  - **`test_mark_jobs_seen_called_with_fresh_only`**: Verify that `mark_jobs_seen` is called with only the fresh jobs, not the full results list. This guards the critical ordering: fetch → split → mark.
  - **`test_seen_payload_has_no_description`**: Verify that entries in `"seen"` contain only `id`, `title`, `company`, `location` — no `description`, `salary`, `apply_link`, or other full-data fields.
- **[Automated]** `mypy .` passes — `call_job_specialist` signature, `mark_jobs_seen`, `get_seen_job_ids` all typed correctly.
- **[Manual]** Trigger a job search. Check the `ToolMessage` in logs — all jobs appear under `"fresh"`, none under `"seen"`.
- **[Manual]** Trigger the same search again. Check the `ToolMessage` — the same job IDs now appear under `"seen"` with only `id`, `title`, `company`, `location`. No `description` field present on seen entries.
- **[Manual]** Verify the LLM does not include seen jobs in `final_answer.jobs` when fresh results are available.
- **[Manual]** Check the store — `(user_id, "seen_jobs")` namespace contains one entry per unique job ID processed, each with only the 4 identity fields.
