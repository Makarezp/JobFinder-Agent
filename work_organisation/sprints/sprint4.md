# Sprint 4: Persistent Job Deck

## Goal
Jobs returned by the agent must accumulate in a persistent, backend-owned deck. A job should only leave the deck when the user explicitly clicks Pass or Pursue. The agent can optionally view the deck (via tool) to avoid duplicates — but the deck is never forced into every turn's context.

---

## Ticket 4.1: Backend — `PendingJob` Model & Store Namespace ✅ DONE

### Overview
Create the data model and store CRUD operations for persisting pending jobs in the `(user_id, "pending_jobs")` namespace, following the existing `DecisionLog` pattern.

### Implementation Steps
1. **Schema**: Add `PendingJob` model to `app/agent/memory_schema.py` with fields exactly mirroring the frontend `Job` interface (`id`, `title`, `company`, `location`, `salary: str | None`, `description`, `apply_link`) plus `added_at: str` (ISO 8601). `added_at` is a store metadata field — do NOT add it to the frontend `Job` type.
2. **Service**: Add methods to `app/services/profile_service.py`:
   - `get_pending_jobs(user_id)` — `asearch` on `(user_id, "pending_jobs")`, **filter out soft-deleted items** (`item.value.get("removed") == True`)
   - `add_pending_jobs(jobs, user_id)` — `aput` each job, keyed by its deterministic `id`
   - `remove_pending_job(job_id, user_id)` — use `aput` with `removed: True` flag (do not rely on `adelete` — `AsyncPostgresStore` support is unconfirmed)
3. **Logging**: Every method must log start and completion using `structlog`, following the same pattern as `log_decision` (e.g. `logger.info("Pending jobs fetched", user_id=user_id, count=len(jobs))`).

### Explicit Constraints & Warnings
- Key each job by its deterministic `id` (the MD5 slug from `_parse_agent_result`), NOT a random UUID — this enables deduplication.
- `get_pending_jobs` **must** filter `removed: True` items — soft-deletes are invisible only if the read path explicitly excludes them.

### Acceptance Criteria
- [Automated] Unit test: `add_pending_jobs` followed by `get_pending_jobs` returns the added jobs.
- [Automated] Unit test: `remove_pending_job` followed by `get_pending_jobs` no longer includes the removed job.

---

## Ticket 4.2 + 4.5: Deck API & Frontend Hydration (Paired Release) ✅ DONE

### Overview
These two tickets are merged into a single paired release to avoid a breaking contract change. The backend adds `GET /api/deck` and `job_id` to `FeedbackRequest`; the frontend simultaneously adds `fetchDeck()` and starts sending `job_id`. Neither side ships without the other.

### Backend Implementation Steps

1. **Schema** in `app/api/schemas.py`:
   - Add `DeckResponse(BaseModel)` with a typed `jobs: list[PendingJob]` field — not a raw dict list.
   - Add `job_id: str` field to `FeedbackRequest`.

2. **Route** in `app/api/routes.py`:
   - Add `GET /api/deck` — calls `ProfileService.get_pending_jobs(DEFAULT_USER_ID)`, returns `DeckResponse`.
   - Update `POST /api/feedback` handler: after `log_decision`, call `ProfileService.remove_pending_job(body.job_id, DEFAULT_USER_ID)`.

### Frontend Implementation Steps

1. **API Wrapper**: Add `fetchDeckRequest()` to `frontend/src/core/api/profile.ts` (NOT `chat.ts` — deck state is a profile/job concern, not a chat concern) — `GET /api/deck` → `Job[]`.

2. **Type Update** in `frontend/src/core/types/api.ts`:
   - Add `job_id: string` to the `FeedbackRequest` interface.

3. **Store Refactor** in `frontend/src/core/store/useJobStore.ts`:
   - Add `fetchDeck()` action that calls `fetchDeckRequest()` and sets `jobs`.
   - Add `isLoading` and `error` state fields.
   - Update `submitFeedback` to pass `job_id: job.id` in the `submitFeedbackRequest` call.
   - Delete the `setJobs` method entirely.

4. **Remove `setJobs` from `useChatStore.ts`**:
   - Remove `useJobStore.getState().setJobs(response.jobs)` from `sendMessage`.
   - Remove `useJobStore.getState().setJobs(lastMessage.jobs)` from `fetchHistory`.
   - After a successful `sendMessage` response, call `useJobStore.getState().fetchDeck()` instead (only if `response.jobs.length > 0`).

5. **Hydration** in `page.tsx`: call `useJobStore.getState().fetchDeck()` on mount alongside existing `fetchHistory` and `fetchProfile` calls.

6. **Loading/error states**: Handle `isLoading` and `error` in `DiscoveryDeck.tsx` — show a spinner while the deck loads, show an error message on failure.

### Explicit Constraints & Warnings
- `GET /api/deck` must be under the `/api` prefix (Next.js proxy rule).
- Do not return soft-deleted jobs from `GET /api/deck`.
- `DiscoveryDeck.tsx` and `JobCard.tsx` require zero changes — they already read from `useJobStore.jobs`.
- The `fetchDeck` call after `sendMessage` replaces the old `setJobs` call entirely. Do not call both.
- `fetchDeck()` introduces a second sequential network call after `sendMessage`. Keep `isPending: true` in `useChatStore` until `fetchDeck` also resolves to prevent a stale deck flash.

### Acceptance Criteria
- [Automated] Backend integration test (mocked store): POST a job to the deck → `GET /api/deck` returns it → POST `/api/feedback` with `job_id` → `GET /api/deck` no longer includes it.
- [Automated] Vitest: `fetchDeck()` populates `jobs` from mock API response.
- [Automated] Vitest: `submitFeedback()` removes job optimistically AND sends `job_id` in the request payload.
- [Automated] Vitest: After `sendMessage` with jobs in response, `fetchDeck` is called (not `setJobs`).
- [Manual] Network tab shows `job_id` present in `POST /api/feedback` payload.
- [Manual] Refresh the page — jobs persist. Send a new query — old jobs remain, new jobs append.

---

## Ticket 4.3: Backend — Persist Jobs on Agent Response

### Overview
When the agent returns jobs via `final_answer`, automatically write them to the pending deck store so they survive page refreshes and aren't lost on the next agent turn.

### Implementation Steps

1. **Inject `ProfileService` into `ChatService`** via constructor — do NOT construct it internally from `self._store`. Update `ChatService.__init__` to accept `profile_service: ProfileService`. Update `get_chat_service` in `app/api/dependencies.py`:
   ```python
   service = ChatService(graph, store, ProfileService(store))
   ```

2. **Move the store write to `process_message` and `process_cv`** — do NOT modify `_parse_agent_result`. Because `_parse_agent_result` is synchronous and `add_pending_jobs` is async, the write must happen in the async callers after `_parse_agent_result` returns:
   ```python
   result = self._parse_agent_result(final_state, message)
   if result["jobs"]:
       await self._profile_service.add_pending_jobs(result["jobs"], DEFAULT_USER_ID)
   return result
   ```
   Apply the same pattern in both `process_message` and `process_cv`.

### Explicit Constraints & Warnings
- **Do NOT make `_parse_agent_result` async** — it has no I/O and changing it to async requires updating all callers including `get_history`. Keep it sync; perform async side-effects in the calling methods only.
- **Do NOT construct `ProfileService(self._store)` inside `ChatService`** — this violates DI rules (DESIGN_PRINCIPLES.md §5). Always inject via constructor.
- Do not change the shape of `ChatResponse` — the frontend still receives jobs inline. The store write is a side-effect only.

### Acceptance Criteria
- [Automated] Unit test: After `process_message` returns jobs, `get_pending_jobs` returns those jobs (mock store injected via `ProfileService`).
- [Automated] Unit test: Calling `process_message` twice with overlapping jobs does not create duplicates.

---

## Ticket 4.4: Backend — `view_pending_deck` Agent Tool

### Overview
Create an optional tool the agent can call to see what's currently in the user's deck, so it can avoid proposing duplicates. The agent decides when to call it — the deck is NOT loaded into context automatically.

### Implementation Steps
1. **Tool**: Add `view_pending_deck` to `app/agent/main/tools.py`.
   - Use `Annotated[BaseStore, InjectedStore()]` for store injection — **do NOT use `functools.partial`**. Check `app/tools/memory.py` and mirror the exact `InjectedStore` pattern used by `update_my_profile`, `save_preference`, and `delete_preference`.
   - Get `user_id` from `config: RunnableConfig` via `config["configurable"]["user_id"]` — same pattern as other memory tools.
   - Returns a compact JSON string: `title`, `company`, and `id` only. Do NOT include descriptions or full job data — minimize token usage.
2. **Bind**: Add `view_pending_deck` to the `main_tools` list in `app/agent/main/tools.py`.
3. **Prompt**: Add a line to the system prompt in `app/agent/main/prompts.py`: *"Use `view_pending_deck` to check the user's current job deck before searching, to avoid showing duplicates."*

### Explicit Constraints & Warnings
- **Do NOT use `functools.partial`** — applying it to a `@tool`-decorated function corrupts the tool schema sent to the LLM, resulting in malformed or empty parameter definitions.
- The `InjectedStore` parameter must be the last parameter in the function signature and annotated correctly so LangGraph strips it from the LLM-facing schema.

### Acceptance Criteria
- [Automated] Unit test: Tool returns correct compact summary (title + company + id) of pending jobs from a mocked store.
- [Manual] In a chat session, `view_pending_deck` appears in the server logs before a second job search in the same session.

---

## Ticket 4.6: Full Integration Tests

### Overview
End-to-end validation that the persistent deck works across the full stack: agent returns jobs → backend persists → frontend hydrates → user passes → job removed from deck and store.

### Implementation Steps
1. **Backend integration tests**: Use an in-memory `InMemoryStore` (injected via the existing DI override pattern) — do NOT require a live Postgres instance. Mark any tests that do require a real DB with `@pytest.mark.integration` and document they are excluded from default CI.
2. **Frontend store tests**: Updated tests for `useJobStore` and `useChatStore` with the new `fetchDeck` pattern.
3. **Manual E2E**: Documented test script in `work_organisation/` covering happy path and edge cases.

### Acceptance Criteria
- [Automated] Backend (mocked store): Agent response with 3 jobs → `GET /api/deck` returns 3 → feedback on 1 → `GET /api/deck` returns 2.
- [Automated] Frontend: All existing Vitest tests pass with the new `fetchDeck` pattern and no `setJobs` calls.
- [Manual] Full browser walkthrough: search → see jobs → refresh → jobs still there → pass one → it's gone → new search → old jobs + new jobs visible.

---

## Dependency Graph

```
4.1 → [4.2 + 4.5] → 4.3 ──→ 4.6
                     4.4 ─┘
```

- Tickets 4.3 and 4.4 can be worked in parallel once the paired 4.2+4.5 release is merged.
- Ticket 4.6 requires 4.3 and 4.4 to be complete.
