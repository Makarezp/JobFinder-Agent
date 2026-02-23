# Sprint 4: Persistent Job Deck

## Goal
Jobs returned by the agent must accumulate in a persistent, backend-owned deck. A job should only leave the deck when the user explicitly clicks Pass or Pursue. The agent can optionally view the deck (via tool) to avoid duplicates — but the deck is never forced into every turn's context.

---

## Ticket 4.1: Backend — `PendingJob` Model & Store Namespace

### Overview
Create the data model and store CRUD operations for persisting pending jobs in the `(user_id, "pending_jobs")` namespace, following the existing `DecisionLog` pattern.

### Implementation Steps
1. **Schema**: Add `PendingJob` model to `app/agent/memory_schema.py` with fields mirroring the frontend `Job` interface (`id`, `title`, `company`, `location`, `salary`, `description`, `apply_link`, `added_at`).
2. **Service**: Add methods to `app/services/profile_service.py`:
   - `get_pending_jobs(user_id)` — `asearch` on `(user_id, "pending_jobs")`
   - `add_pending_jobs(jobs, user_id)` — `aput` each job, keyed by its deterministic `id`
   - `remove_pending_job(job_id, user_id)` — delete or soft-remove by key

### Explicit Constraints & Warnings
- Key each job by its deterministic `id` (the MD5 slug from `_parse_agent_result`), NOT a random UUID — this enables deduplication.
- Check whether `AsyncPostgresStore` supports `adelete`. If not, use `aput` with a `removed: true` flag and filter on read.

### Acceptance Criteria
- [Automated] Unit test: `add_pending_jobs` followed by `get_pending_jobs` returns the added jobs.
- [Automated] Unit test: `remove_pending_job` followed by `get_pending_jobs` no longer includes the removed job.

---

## Ticket 4.2: Backend — Deck API Endpoints

### Overview
Expose a REST endpoint to fetch the current deck, and update the existing feedback endpoint to remove the job from the deck on pass/pursue.

### Implementation Steps
1. **Schema**: Add `DeckResponse` to `app/api/schemas.py` — a list of `PendingJob` dicts.
2. **Route**: Add `GET /api/deck` to `app/api/routes.py` — calls `ProfileService.get_pending_jobs()`, returns `DeckResponse`.
3. **Update Feedback**: In `POST /api/feedback` handler, after `log_decision`, call `ProfileService.remove_pending_job(job_id)` to remove the job from the deck.
4. **Schema Update**: Add `job_id: str` field to `FeedbackRequest` so the endpoint knows which deck item to remove.

### Explicit Constraints & Warnings
- `GET /api/deck` must be under the `/api` prefix (proxy rule).
- Do not return removed/soft-deleted jobs from `GET /api/deck`.

### Acceptance Criteria
- [Automated] Integration test: POST a job to the deck, GET `/api/deck` returns it, POST `/api/feedback` with pass, GET `/api/deck` no longer includes it.
- [Manual] Network tab shows correct payloads for both endpoints.

---

## Ticket 4.3: Backend — Persist Jobs on Agent Response

### Overview
When the agent returns jobs via `final_answer`, automatically write them to the pending deck store so they survive page refreshes and aren't lost on the next agent turn.

### Implementation Steps
1. **Modify `ChatService._parse_agent_result()`** in `app/services/chat_service.py`:
   - After extracting `jobs` from `final_answer` args and injecting IDs, call `ProfileService.add_pending_jobs(jobs, user_id)`.
2. **Inject ProfileService** into `ChatService` (or access store directly) to enable the write.

### Explicit Constraints & Warnings
- Deduplication is handled by keying on the deterministic `id` — `aput` with the same key overwrites, so no duplicates.
- Do not change the shape of `ChatResponse` — the frontend still receives jobs inline for immediate rendering. The store write is a side-effect for persistence.

### Acceptance Criteria
- [Automated] Unit test: After `process_message` returns jobs, `get_pending_jobs` returns those jobs.
- [Automated] Unit test: Calling `process_message` twice with overlapping jobs does not create duplicates.

---

## Ticket 4.4: Backend — `view_pending_deck` Agent Tool

### Overview
Create an optional tool the agent can call to see what's currently in the user's deck, so it can avoid proposing duplicates. The agent decides when to call it — the deck is NOT loaded into context automatically.

### Implementation Steps
1. **Tool**: Add `view_pending_deck` to `app/agent/main/tools.py`.
   - Reads from store `(user_id, "pending_jobs")` namespace.
   - Returns a JSON string summary (title + company for each, to minimize tokens).
2. **Bind**: Add the tool to the `main_tools` list so it's available to `main_chatbot`.
3. **Prompt**: Add a line to the system prompt in `app/agent/main/prompts.py`: *"Use `view_pending_deck` to check the user's current job deck before searching, to avoid showing duplicates."*

### Explicit Constraints & Warnings
- The tool must access the store. Since tools can't use `InjectedStore` directly, use `functools.partial` to inject the store at graph compilation time (same pattern as `fetch_profile`), OR make it a subgraph node.
- Keep the returned payload concise — title + company + id only. Do not dump full descriptions into the LLM context.

### Acceptance Criteria
- [Automated] Unit test: Tool returns correct summary of pending jobs from store.
- [Manual] In a chat session, agent calls `view_pending_deck` before a second search and avoids re-proposing the same jobs.

---

## Ticket 4.5: Frontend — Hydrate Job Store from Deck API

### Overview
Refactor `useJobStore` to load its initial state from `GET /api/deck` instead of relying on `useChatStore.setJobs()`. Remove the tight coupling between chat responses and the job list.

### Implementation Steps
1. **API Wrapper**: Add `fetchDeckRequest()` to `frontend/src/core/api/chat.ts` — `GET /api/deck` → `Job[]`.
2. **Store Refactor** in `frontend/src/core/store/useJobStore.ts`:
   - Add `fetchDeck()` action that calls `fetchDeckRequest()` and sets `jobs`.
   - Add `isLoading` and `error` state fields.
   - Keep `submitFeedback` as-is (it already removes optimistically).
3. **Remove `setJobs`**: Delete the `setJobs` method. Remove all `useJobStore.setJobs()` calls from `useChatStore.ts`.
4. **Hydration**: In `page.tsx`, call `useJobStore.getState().fetchDeck()` on mount (alongside existing `fetchHistory` and `fetchProfile` calls).
5. **After Send**: In `useChatStore.sendMessage`, after a successful response that contains jobs, call `fetchDeck()` to refresh the deck (backend already persisted them in Ticket 4.3).

### Explicit Constraints & Warnings
- `DiscoveryDeck.tsx` and `JobCard.tsx` should require zero changes — they already read from `useJobStore.jobs`.
- The `fetchDeck` call after `sendMessage` replaces the old `setJobs` call. Do not call both.
- Handle loading and error states in `DiscoveryDeck.tsx` (show spinner while deck loads, show error message on failure).

### Acceptance Criteria
- [Automated] Vitest: `fetchDeck()` populates `jobs` from mock API response.
- [Automated] Vitest: `submitFeedback()` removes job optimistically, jobs array shrinks by 1.
- [Automated] Vitest: After `sendMessage`, `fetchDeck` is called (not `setJobs`).
- [Manual] Refresh the page — jobs persist. Send a new query — old jobs remain, new jobs append.

---

## Ticket 4.6: Full Integration Tests

### Overview
End-to-end validation that the persistent deck works across the full stack: agent returns jobs → backend persists → frontend hydrates → user passes → job removed from deck and store.

### Implementation Steps
1. **Backend integration tests**: Full flow through `ChatService` → Store → API endpoints.
2. **Frontend store tests**: Updated tests for `useJobStore` and `useChatStore` decoupling.
3. **Manual E2E**: Document a manual test script covering the happy path and edge cases.

### Acceptance Criteria
- [Automated] Backend: Agent response with 3 jobs → `GET /api/deck` returns 3 → feedback on 1 → `GET /api/deck` returns 2.
- [Automated] Frontend: All existing tests pass with the new `fetchDeck` pattern.
- [Manual] Full browser walkthrough: search → see jobs → refresh → jobs still there → pass one → it's gone → new search → old jobs + new jobs visible.

---

## Dependency Graph

```
4.1 → 4.2 → 4.3 ──→ 4.5 → 4.6
             4.4 ─┘
```

Tickets 4.3 and 4.4 can be worked in parallel once 4.2 is done.
