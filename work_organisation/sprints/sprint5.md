# Sprint 5: Job Carousel & Full Description Pipeline

## Visual Reference
`work_organisation/stich_desing_cards.html` — AI-generated HTML prototype of the target design. For the parts we are implementing, follow it faithfully: carousel layout, nav gutters, side peek cards, card header structure, scrollable body, floating action bar, and all CSS classes (`glass-panel`, `glow-card`, `nav-gutter`, `side-card`, `floating-action-bar`, `custom-scroll`, `scroll-mask`).

**Do NOT implement** the following elements from the prototype — they are out of scope for this sprint:
- Match score (98% badge)
- Skill tag pills
- "Why this is a match" / rationale section
- Team size metadata
- Posted date metadata
- "Navigator Suggestion" badge
- Notifications bell / user avatar in header

---

## Goal
Replace the grid of small job cards with a full-profile carousel. Each job occupies the entire discovery area — the user reads it in full and decides to Pass or Pursue. Simultaneously, the agent pipeline is upgraded to always deep-inspect candidates before surfacing them, so every card in the deck carries a full description.

---

## Ticket 5.1: Backend — Add `full_description` to the Data Pipeline — DONE

### Overview
Add `full_description: str | None` as an optional field to `PendingJob` (the persistence model). This is a purely additive, non-breaking change — existing jobs without a full description will carry `None`.

> **Do NOT add `full_description` to `JobListing`.** `JobListing` is the schema the LLM populates inside its `final_answer` tool call. Adding the field there would cause the LLM to attempt to fill it, which is unreliable for large content. `full_description` is stitched onto jobs by the backend in Ticket 5.2 — the LLM is never the carrier. Keep `JobListing` as the compact, LLM-facing output schema.

### Implementation Steps

1. **`app/agent/memory_schema.py` — `PendingJob`**: Add field after `description`:
   ```python
   full_description: str | None = None
   ```
   `added_at` remains the last field.

2. **`app/services/profile_service.py` — `add_pending_jobs`**: No change required. The method builds `PendingJob` using `**job` spread (line 83–86). Because `full_description` defaults to `None` in `PendingJob`, existing job dicts without the field will deserialise correctly. Job dicts that carry `full_description` (injected by `_parse_agent_result` in Ticket 5.2) will be stored automatically.

3. **`app/api/schemas.py` — `DeckResponse`**: No change required. `DeckResponse` wraps `list[PendingJob]` directly — the new field is automatically included in the serialised response once added to `PendingJob`.

### Explicit Constraints & Warnings
- Do NOT add `full_description` to `JobListing` — see overview.
- Do NOT add `full_description` to `JobSummary` — that model represents the lightweight Adzuna search result and must stay compact.
- Do NOT make this field required (`...`) — jobs already in the store have no `full_description`. A required field would break deserialisation of existing persisted jobs.
- Do NOT modify `DeckResponse` or `FeedbackRequest` — the API contract is unchanged.

### Acceptance Criteria
- [Automated] `mypy --strict` passes with no new errors.
- [Automated] Unit test: `PendingJob(**existing_job_dict)` with no `full_description` key deserialises without error and `full_description` is `None`.
- [Automated] Unit test: `PendingJob` with `full_description="some text"` serialises to dict with the field present.

---

## Ticket 5.2: Backend — Agent Inspect-First Flow — DONE

### Overview
Update the agent to enforce a **search → filter → inspect → surface** flow. The agent currently calls `final_answer` immediately after a search.

**Architecture note — how `full_description` reaches the deck:**
The LLM is NOT responsible for carrying `full_description` into `final_answer`. Raw scraped content can be up to 20,000 chars — asking the LLM to re-emit it verbatim in a tool call is unreliable (LLMs truncate, corrupt, or drop large strings under context pressure) and token-expensive (~40K tokens per search turn).

Instead, the backend owns the stitching:
1. Each inspect result is stored in `AgentState` keyed by the job URL.
2. After the graph completes, `_parse_agent_result` matches each job's `apply_link` against the stored inspect results and injects `full_description` into the raw job dict.
3. `add_pending_jobs` then persists the enriched dict via `**job` spread — `PendingJob.full_description` is populated automatically.

The LLM's only responsibility is to call `final_answer` with the `apply_link` intact (it already is, as a required `JobListing` field). It does not set `full_description`.

### Implementation Steps

1. **`app/agent/state.py` — `AgentState`**: Add two new fields:
   ```python
   inspect_attempts: int
   inspect_results: NotRequired[dict[str, str]]
   ```
   - `inspect_attempts` is non-`NotRequired` (mirrors `search_attempts`) — always initialised via the `inputs` dict.
   - `inspect_results` is `NotRequired` — a dict mapping job URL → raw full description string. Uses `NotRequired` because it requires no custom reducer; the node that updates it always reads the current value and returns the full merged dict (see Step 2).

2. **`app/agent/graph.py` — `call_job_specialist`**: Add the inspect guard and state update. The updated function logic after parsing `input_data`:

   ```python
   # --- Inspect guard ---
   if input_data.mode == "inspect":
       inspect_attempts = state.get("inspect_attempts", 0)
       if inspect_attempts >= 5:
           return {
               "messages": [ToolMessage(
                   content="SYSTEM ALERT: Maximum inspect attempts (5) reached.",
                   tool_call_id=tool_call_id,
               )]
           }
       new_inspect_attempts = inspect_attempts + 1
   else:
       new_inspect_attempts = state.get("inspect_attempts", 0)

   # --- (existing search guard remains above, unchanged) ---
   ```

   In the `mode == "inspect"` output block, after successfully retrieving `detail`, store the result in state by merging with the current dict:
   ```python
   elif input_data.mode == "inspect":
       detail = result.get("inspect_result")
       if not detail:
           output_content = "Failed to fetch details."
       else:
           output_content = detail.model_dump_json(indent=2)
           # Merge into inspect_results keyed by URL
           current_results = dict(state.get("inspect_results", {}))
           current_results[input_data.url] = detail.full_description

   return {
       "messages": [ToolMessage(content=output_content, tool_call_id=tool_call_id)],
       "search_attempts": new_attempts,
       "inspect_attempts": new_inspect_attempts,
       "inspect_results": current_results,  # only set when mode=="inspect" and success
   }
   ```
   When `mode == "search"`, omit `inspect_results` from the return dict (no update needed).

3. **`app/services/chat_service.py` — `_parse_agent_result`**: After extracting the `jobs` list from the `final_answer` tool call args, stitch `full_description` from state:
   ```python
   inspect_results: dict[str, str] = result.get("inspect_results", {})
   for job in jobs:
       if not job.get("full_description") and inspect_results:
           job["full_description"] = inspect_results.get(job.get("apply_link", ""))
   ```
   This runs before the `id` injection block and before `add_pending_jobs` is called, so the enriched dict flows cleanly into `PendingJob(**job)` in `profile_service.py`.

4. **`app/services/chat_service.py` — `process_message` inputs dict**: Add both new counters and the results dict:
   ```python
   inputs: dict[str, Any] = {
       "messages": [HumanMessage(content=message)],
       "search_attempts": 0,
       "inspect_attempts": 0,
       "inspect_results": {},
   }
   ```

5. **`app/services/chat_service.py` — `process_cv` inputs dict**: Add the same keys for consistency. The CV upload flow routes to the onboarding path and never reaches `call_job_specialist`, so these counters are never read — but initialising them prevents state inconsistency if the routing ever changes:
   ```python
   inputs: dict[str, Any] = {
       "messages": [HumanMessage(content=f"I just uploaded my CV ({filename}). Please analyze it.")],
       CV_RAW_TEXT_KEY: cv_text,
       "search_attempts": 0,
       "inspect_attempts": 0,
       "inspect_results": {},
   }
   ```

6. **`app/agent/main/prompts.py` — `SYSTEM_PROMPT`**: Add an explicit job surfacing protocol. Insert after the existing tool instructions:

   ```
   ## Job Surfacing Protocol (MANDATORY)
   You MUST follow this sequence every time you search for jobs. Never skip a step.

   1. SEARCH: Call `job_specialist_tool` with mode="search" to get a list of job summaries.
   2. FILTER: From the summaries, select the top candidates that best match the user's CV,
      preferences, and recent decisions. Aim for 2-3 candidates. Skip any that clearly
      conflict with known hard preferences (e.g. wrong tech stack, wrong location).
   3. INSPECT: For each selected candidate, call `job_specialist_tool` with mode="inspect"
      and the candidate's `url`. Use the returned full description to confirm fit.
   4. ANALYZE: After inspecting, decide if each job is a genuine fit. If a job does not
      hold up under scrutiny, drop it silently — do not surface it.
   5. SURFACE: Call `final_answer` with only the confirmed fits. For each job, populate
      `description` with a concise summary (2-3 sentences) and ensure `apply_link` is
      included exactly as returned by the search. Do NOT attempt to populate a
      `full_description` field — the backend handles that automatically.
   ```

### Explicit Constraints & Warnings
- Do NOT change the graph topology (nodes, edges, routing logic) — this is a prompt + state change only.
- `inspect_attempts` must be treated exactly like `search_attempts` — reset to `0` on every new call via the `inputs` dict.
- Do NOT add `inspect_attempts` to `NotRequired` — it must always be present in the `inputs` dict and state.
- `inspect_results` uses `NotRequired` because the node always returns the full merged dict (no reducer needed). It is always initialised to `{}` in `process_message` and `process_cv`.
- The `current_results` merge in Step 2 must use `dict(state.get("inspect_results", {}))` — copy the existing dict, add the new entry, return the whole thing. Do not return only the new entry, or previous inspect results will be lost.

### Acceptance Criteria
- [Automated] `mypy --strict` passes with no new errors on `state.py`, `graph.py`, and `chat_service.py`.
- [Automated] Unit test: When `inspect_attempts >= 5`, `call_job_specialist` in inspect mode returns a `ToolMessage` with the SYSTEM ALERT content and does NOT invoke the subgraph.
- [Automated] Unit test: After a successful inspect call, the returned dict contains `inspect_results` with the job URL as key and `full_description` as value.
- [Automated] Unit test: `_parse_agent_result` — given a `final_state` with `inspect_results = {"https://example.com/job": "Full text"}` and a job dict with `apply_link = "https://example.com/job"`, the returned job dict has `full_description = "Full text"`.
- [Manual] Run a chat session requesting jobs. Server logs must show at least one `inspect_job` node execution before `final_answer` is called.
- [Manual] Jobs returned from `GET /api/deck` have non-null `full_description` values.

---

## Ticket 5.3: Frontend — Add `full_description` to `Job` Type

### Overview
Add `full_description: string | null` to the frontend `Job` interface so the carousel component can render it. This is a purely additive type change.

### Implementation Steps

1. **`frontend/src/core/types/api.ts` — `Job` interface**: Add field after `description`:
   ```typescript
   full_description: string | null;
   ```

2. **`frontend/src/core/store/useJobStore.ts`**: No change required — the store stores `Job[]` and the new field passes through automatically.

3. **`frontend/src/core/api/profile.ts`**: No change required — `fetchDeckRequest` deserialises the raw JSON response; the new field is included automatically.

### Explicit Constraints & Warnings
- Do NOT add `full_description` to `FeedbackRequest` — it is not sent back to the backend on pass/pursue.
- Do NOT add `full_description` to `ChatResponse` — the chat response type is a separate concern. Jobs reach the deck via `GET /api/deck`, not directly from the chat response.
- After this ticket, `JobCard.tsx` will have a TypeScript error because it does not yet reference `full_description`. This is expected — it is resolved in Ticket 5.5.

### Acceptance Criteria
- [Automated] `npm run type-check` passes with no errors.
- [Automated] Existing Vitest tests pass without modification.

---

## Ticket 5.4: Frontend — Carousel Shell (`DiscoveryDeck` Redesign)

### Overview
Redesign `DiscoveryDeck.tsx` from a responsive grid into a full-height carousel shell. One job profile occupies the entire discovery area at a time. Left/right navigation arrows allow free browsing. Passing a job hides it locally and auto-advances to the next.

### Implementation Steps

1. **`frontend/src/components/DiscoveryDeck.tsx` — Full rewrite**:

   **State** (all local — do NOT add to Zustand store):
   ```typescript
   const [currentIndex, setCurrentIndex] = useState(0);
   const [passedIds, setPassedIds] = useState<Set<string>>(new Set());
   ```

   **Derived values**:
   ```typescript
   const visibleJobs = jobs.filter(j => !passedIds.has(j.id));
   const currentJob = visibleJobs[currentIndex] ?? null;
   ```

   **Navigation handlers**:
   - `goNext()`: `setCurrentIndex(i => Math.min(i + 1, visibleJobs.length - 1))`
   - `goPrev()`: `setCurrentIndex(i => Math.max(i - 1, 0))`

   **Pass handler** (receives job from `JobProfile`):
   ```typescript
   function handlePass(job: Job, reason: string | null) {
     setPassedIds(prev => new Set(prev).add(job.id));
     // Clamp index after removal. visibleJobs.length - 2 is the new max valid index
     // once this job is removed. Math.max(0, ...) prevents -1 when passing the last job.
     setCurrentIndex(i => Math.max(0, Math.min(i, visibleJobs.length - 2)));
     useJobStore.getState().submitFeedback(job, "pass", reason);
   }
   ```

   **Layout structure**:
   ```
   <section> (flex-1, flex, items-center, justify-center, relative, overflow-hidden)
     <!-- Left nav gutter -->
     <div> (absolute left-0, nav-gutter class, z-30, cursor-pointer, onClick=goPrev)
       <chevron_left icon>
     </div>

     <!-- Side peek cards (desktop only, hidden md:block) -->
     <div> (absolute left ~5%, scale-92, opacity-40, blur-sm, side-card class)
       <!-- ghost card — no content, purely decorative -->
     </div>
     <div> (absolute right ~5%, same styling)
     </div>

     <!-- Main profile card -->
     <div> (w-full max-w-4xl, h-full, z-20, mx-20)
       {currentJob ? <JobProfile job={currentJob} onPass={handlePass} /> : <EmptyState />}
     </div>

     <!-- Right nav gutter -->
     <div> (absolute right-0, nav-gutter right class, z-30, cursor-pointer, onClick=goNext)
       <chevron_right icon>
     </div>
   </section>
   ```

   **Empty state** (inline, not a separate component):
   - Render when `visibleJobs.length === 0` and `!isLoading`.
   - Message: *"You're all caught up. Ask the navigator to find more."*
   - Include a `smart_toy` Material Symbol icon.

   **Loading state**: Reuse the existing spinner pattern from the current `DiscoveryDeck.tsx`.

   **Error state**: Reuse the existing error message pattern from the current `DiscoveryDeck.tsx`.

2. **CSS** (`globals.css` or inline via Tailwind): Port the `nav-gutter`, `side-card`, and `glow-card` custom styles into the project. Use `work_organisation/stich_desing_cards.html` as the visual reference — do not copy it verbatim, adapt to the existing component patterns.

### Explicit Constraints & Warnings
- `passedIds` and `currentIndex` are LOCAL component state — do NOT add them to `useJobStore`. The Zustand store is the source of truth for the job list; the carousel's view state is ephemeral.
- Do NOT remove jobs from `useJobStore.jobs` on pass — the store removal is handled by `submitFeedback` via `POST /api/feedback`. The `passedIds` Set provides immediate local feedback only.
- The `setCurrentIndex` clamp in `handlePass` **must** use `Math.max(0, Math.min(i, visibleJobs.length - 2))`. Without the `Math.max(0, ...)` guard, passing the last remaining job produces `currentIndex = -1`. If `fetchDeck` then loads new jobs, `visibleJobs[-1]` is `undefined` in JS and the deck appears empty even with data.
- Left arrow must be disabled (no-op or hidden) when `currentIndex === 0`. Right arrow must be disabled when `currentIndex === visibleJobs.length - 1`.
- The side peek ghost cards are decorative divs with no job data — they exist purely to create the carousel depth illusion. Do NOT render actual `JobProfile` components for them.
- `JobProfile` does not yet exist at the start of this ticket — implement Ticket 5.5 first, or stub `JobProfile` with a placeholder div.

### Acceptance Criteria
- [Automated] Vitest: When `jobs` has 3 items and `passedIds` contains 1 id, `visibleJobs.length` is 2.
- [Automated] Vitest: Calling `handlePass` adds the job id to `passedIds` and calls `submitFeedback`.
- [Automated] Vitest: Empty state renders when `visibleJobs.length === 0` and `isLoading` is false.
- [Automated] Vitest: When `visibleJobs` has exactly 1 job and `handlePass` is called, `currentIndex` is `0` (not `-1`) after the update.
- [Manual] With 3 jobs in the deck: right arrow advances through them, left arrow goes back. Passing a job removes it from view and advances. At the last job, right arrow does nothing.
- [Manual] Pass all jobs one by one — empty state appears cleanly after the last pass. Triggering a new search repopulates the carousel from index 0.

---

## Ticket 5.5: Frontend — `JobProfile` Component (Full Card)

### Overview
Build `JobProfile.tsx` — the full-profile job card that occupies the carousel. It has a sticky header (title, company, location, salary), a scrollable body (short description, divider, full description), and a floating action bar (Pass, Pursue) anchored to the card bottom.

### Implementation Steps

1. **Create `frontend/src/components/JobProfile.tsx`**:

   **Props interface**:
   ```typescript
   interface JobProfileProps {
     job: Job; // from frontend/src/core/types/api.ts
     onPass: (job: Job, reason: string | null) => void;
   }
   ```

   **Local state**:
   ```typescript
   const [showReasonInput, setShowReasonInput] = useState(false);
   const [reason, setReason] = useState("");
   ```

   **Pass flow**:
   - Click "Pass" → `setShowReasonInput(true)` (reason input appears above action bar)
   - "Submit" → `onPass(job, reason.trim() || null)` → reset state
   - "Skip" → `onPass(job, null)` → reset state

   **Layout structure** (mirrors `stich_desing_cards.html` card, scoped to our data):
   ```
   <div> (relative, glass-panel glow-card, rounded-2xl, flex flex-col, overflow-hidden, h-full)
   ^^^^ NOTE: `relative` is required here so the absolute-positioned floating action bar is
        scoped to the card and not to a parent container.

     <!-- Sticky Header -->
     <div> (shrink-0, p-8, pb-4, border-b, bg-surface-dark/50, backdrop-blur)
       <div> (flex gap-5, items-start)
         <!-- Logo placeholder -->
         <div> (size-20, rounded-2xl, bg-slate-800, flex, items-center, justify-center)
           <span material-symbols work text-4xl text-slate-400 />
         </div>
         <!-- Title block -->
         <div>
           <h3> job.title (text-3xl font-bold text-white)
           <p> job.company · job.location (text-lg text-slate-300)
           <!-- Salary pill — only if job.salary !== null -->
           <span> payments icon + job.salary (text-sm text-slate-400)
         </div>
       </div>
     </div>

     <!-- Scrollable Body -->
     <!-- pb-24 is required — the floating action bar (~80px tall) is absolute-positioned
          over the bottom of this scroll area. Without the padding, the last lines of a
          long full_description are permanently obscured and unreachable by scrolling. -->
     <div> (flex-1, overflow-y-auto, custom-scroll, p-8, pb-24, space-y-6, scroll-mask)

       <!-- Short description section -->
       <div>
         <h4> "Overview" (text-lg font-semibold text-white)
         <p> job.description (text-slate-300, leading-relaxed)
       </div>

       <!-- Full description section — only render if job.full_description is not null -->
       {job.full_description && (
         <div> (pt-4, border-t, border-glass-border)
           <h4> "Full Description" (text-lg font-semibold text-white)
           <div> job.full_description rendered as plain text (text-slate-300, leading-relaxed, whitespace-pre-wrap)
         </div>
       )}

     </div>

     <!-- Reason input — shown above action bar when showReasonInput is true -->
     {showReasonInput && (
       <div> (px-6, pb-2, flex gap-2, items-center)
         <input placeholder="Why? (optional)" />
         <button onClick=handleSkip> Skip </button>
         <button onClick=handleSubmit> Submit </button>
       </div>
     )}

     <!-- Floating Action Bar -->
     <div> (absolute bottom-8, left-1/2, -translate-x-1/2, w-[calc(100%-4rem)], max-w-lg, z-40)
       <div> (floating-action-bar, rounded-2xl, p-2, flex gap-3)
         <button onClick=handlePassClick> close icon + Pass </button>
         <a href=job.apply_link target=_blank> Pursue + arrow_forward icon </a>
       </div>
     </div>

   </div>
   ```

2. **CSS**: Add `floating-action-bar`, `custom-scroll`, `scroll-mask`, and `glow-card` to `globals.css` alongside the existing `glass-panel` definition. Refer to `work_organisation/stich_desing_cards.html` for the intended visual output.

3. **Delete `JobCard.tsx`** and its test file `JobCard.test.tsx` — `JobProfile.tsx` fully replaces it. Update any imports.

4. **`frontend/src/components/JobProfile.test.tsx`**: Write companion tests:
   - Renders title, company, location from `job` props.
   - Salary is rendered when `job.salary` is not null; absent when null.
   - Full description section is rendered when `job.full_description` is not null; absent when null.
   - Clicking "Pass" shows the reason input.
   - Clicking "Skip" calls `onPass(job, null)`.
   - Clicking "Submit" with a reason calls `onPass(job, reason)`.
   - Pursue link has correct `href` and `target="_blank"`.

### Explicit Constraints & Warnings
- The outer card div **must** have `position: relative` (Tailwind: add `relative` to the class list). The floating action bar uses `absolute` positioning — without `relative` on the card, it will escape the card and position against a parent container.
- The scrollable body **must** have `pb-24` (or equivalent ≥ 80px). The floating action bar overlays the bottom of the scroll area. Without this padding, the final lines of any long `full_description` are permanently hidden beneath the action bar and cannot be scrolled into view.
- `JobProfile` does NOT call `useJobStore` directly — it receives `onPass` as a prop. The parent (`DiscoveryDeck`) owns the store interaction. This keeps `JobProfile` purely presentational and testable.
- Do NOT call `submitFeedback` inside `JobProfile`. Call `onPass` and let `DiscoveryDeck` handle store dispatch.
- `full_description` may be raw scraped markdown (with `#`, `*`, `-` characters). Render it as `whitespace-pre-wrap` plain text for now — do NOT use a markdown renderer (unnecessary dependency at this stage).
- The `Pursue` action is an `<a>` tag, not a `<button>`. Do not intercept it — let the browser open the apply link natively.

### Acceptance Criteria
- [Automated] `npm run type-check` passes.
- [Automated] All `JobProfile.test.tsx` tests pass.
- [Automated] No remaining imports of `JobCard` anywhere in the codebase.
- [Manual] Card with a long `full_description`: body scrolls to the very last line of text; Pass and Pursue buttons remain visible and unobscured at all times.
- [Manual] Card with `full_description: null`: "Full Description" section is absent; card renders cleanly.
- [Manual] Click Pass → reason input appears → Submit → card disappears from carousel.

---

## Dependency Graph

```
5.1 (backend schema — PendingJob only)
  └→ 5.2 (agent inspect flow + AgentState stitching)

5.3 (frontend type)
  └→ 5.5 (JobProfile component)
        └→ 5.4 (carousel shell)

5.1 and 5.3 are independent entry points and can be worked in parallel.
5.4 requires 5.5. 5.5 requires 5.3.
The frontend (5.3 → 5.5 → 5.4) can ship before 5.1/5.2 — full_description
will be null for all jobs until the backend tickets are complete, and the
UI degrades gracefully (the "Full Description" section simply doesn't render).
```
