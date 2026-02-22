# Sprint 3: The Interactivity Loop & Profile View

**Goal**: Implement the core "Tinder for Jobs" feedback loop and elevate the user's profile into a first-class, tabbed view. When a user clicks "Pass" on a job card, the system logs their feedback, removes the card, and surfaces the decision in a persistent "Profile" tab. The agent uses this accumulated history to refine future searches.

**Design Reference**: The Stitch-generated profile layout is at `documents/stitch_migration/stich_profile.html`. Use it as a **visual direction**, not a pixel-perfect specification. The design may include elements (e.g., "Add Constraint" button) that we have intentionally excluded from this sprint. The implementing agent should analyze the HTML for styling cues (glass panels, color tokens, spacing) but follow the ticket specifications for structure and behavior.

---

## Detailed Ticket Breakdown

### Ticket 3.1: Backend — Decision Log Schema & Feedback Endpoint ✅ DONE

#### Overview
Create the data model and API endpoint for logging user feedback on job cards. When a user clicks "Pass" on a job, the frontend sends a `POST /api/feedback` request. The backend persists this as a `DecisionLog` entry in the LangGraph memory store under the `(user_id, "decisions")` namespace. This log is later read by the agent (via `fetch_profile`) to inform future searches.

#### Implementation Steps
1. **Decision Log Schema** (`app/agent/memory_schema.py`):
   - Add a new Pydantic model `DecisionLog` with the following fields:
     ```python
     class DecisionLog(BaseModel):
         job_title: str
         company: str
         action: Literal["pass", "pursue"]
         description: str | None = None
         reason: str | None = None
         timestamp: str  # ISO 8601 format
     ```
   - `description` carries a brief job summary snippet (sourced from `JobListing.description`) so the agent has richer context when reviewing past decisions.
   - This model lives alongside the existing `UserProfile` and `Preference` models.

5. **Add `sentiment` field to `Preference` model** (`app/agent/memory_schema.py`):
   - Add `sentiment: Literal["positive", "negative"] = "positive"` to the existing `Preference` model. This allows the frontend to classify preferences into "Looking For" vs "Avoiding" without fragile heuristics. Existing preferences default to `"positive"`.
   - Update `save_preference` tool logic: when the user says "no X" or "avoid Y", set `sentiment` to `"negative"`. When the user says "I want X" or "looking for Y", set `sentiment` to `"positive"`.

2. **Feedback Request Schema** (`app/api/schemas.py`):
   - Add `FeedbackRequest` Pydantic model:
     ```python
     class FeedbackRequest(BaseModel):
         job_title: str
         company: str
         action: Literal["pass", "pursue"]
         description: str | None = None
         reason: str | None = None
     ```

3. **Feedback Endpoint** (`app/api/routes.py`):
   - Add `POST /api/feedback` endpoint.
   - Inject `StoreDep` (the LangGraph `BaseStore`) via the existing DI pattern.
   - Generate a unique key for the entry using `str(uuid4())` (import from `uuid`). Do NOT use slug-based keys — they risk silent overwrites if two actions share the same second.
   - Construct a `DecisionLog` instance with `timestamp` set to `datetime.now(timezone.utc).isoformat()` (import `timezone` from `datetime`). Do NOT use `datetime.utcnow()` — it is deprecated in Python 3.12+.
   - Write to store: `await store.aput((user_id, "decisions"), key, log.model_dump())`.
   - Return `JSONResponse(content={"status": "ok"})`.

4. **Job ID on JobListing** (`app/agent/schemas.py`):
   - Add `id: str` field to `JobListing`:
     ```python
     id: str = Field(default="", description="Deterministic hash for frontend tracking. Computed in _parse_agent_result, not by the LLM.")
     ```
   - **CRITICAL**: The `id` MUST be computed in `_parse_agent_result` in `ChatService` as a post-processing step. Do NOT rely on the LLM to generate it — `_parse_agent_result` returns raw `tool_calls` dicts without Pydantic validation, so adding the field to the schema alone does nothing for the actual response. Add the following after extracting jobs:
     ```python
     import hashlib
     for job in jobs:
         if "id" not in job:
             slug = f"{job.get('company', '')}{job.get('title', '')}{job.get('apply_link', '')}".encode()
             job["id"] = hashlib.md5(slug).hexdigest()[:12]
     ```
   - The hash includes `apply_link` (not just `company + title`) to avoid deterministic duplicates for same-titled roles at the same company.

#### Explicit Constraints & Warnings
- **Do NOT route feedback through the chat agent.** `POST /api/feedback` is a simple CRUD write to the store. It does not invoke the LangGraph graph. The agent reads decisions passively on its next invocation.
- **Do NOT use `ChatServiceDep` in the feedback endpoint.** Use `StoreDep` directly. The feedback path must be fast and independent of the LLM.
- **The `id` field on `JobListing` is a breaking change for the frontend `Job` interface.** Ticket 3.3 handles the frontend update. Until then, the frontend will ignore unknown fields from the JSON response, so this is safe to deploy first.

#### Acceptance Criteria
- [Automated] `pytest` test sends a `POST /api/feedback` with `{"job_title": "Dev", "company": "Acme", "action": "pass", "reason": "Too corporate"}` and asserts the store now contains a `DecisionLog` entry under `("default_user", "decisions")`.
- [Automated] `pytest` test verifies the `DecisionLog` Pydantic model validates correctly and rejects invalid `action` values (e.g., `"maybe"`).
- [Manual] Use `curl -X POST http://localhost:8000/api/feedback -H "Content-Type: application/json" -d '{"job_title": "Test", "company": "TestCo", "action": "pass"}'` and verify a `200 {"status": "ok"}` response. Then hit `GET /api/profile` and verify the `decisions` array (added in Ticket 3.2) contains the entry.
- [Automated] Verify that `_parse_agent_result` injects `id` into every job dict — mock a tool call response without `id` and assert the returned jobs all have a 12-character hex `id`.

---

### Ticket 3.2: Backend — Profile Endpoint Enhancement & Agent Context

#### Overview
Update the existing `GET /api/profile` endpoint to also return the decision log, so the frontend has everything it needs for the Profile tab in a single request. Additionally, update the agent's `fetch_profile` node to inject recent decisions into the system prompt context, allowing the agent to passively learn from user feedback without any special feedback-processing logic.

#### Implementation Steps
1. **Update `GET /api/profile`** (`app/api/routes.py`):
   - The existing endpoint already fetches `profile` and `preferences` from the store.
   - Add a third query: `await store.asearch((user_id, "decisions"))` to retrieve all `DecisionLog` entries.
   - Parse each item's `.value` through the `DecisionLog` model (same pattern as existing `Preference` parsing).
   - Sort **in Python** by `timestamp` descending (most recent first). `store.asearch()` does NOT guarantee order:
     ```python
     decisions_items = await store.asearch((user_id, "decisions"))
     decisions = sorted(
         [DecisionLog(**item.value).model_dump() for item in decisions_items if item.value],
         key=lambda d: d["timestamp"],
         reverse=True,
     )
     ```
   - Return the full payload:
     ```python
     {
         "profile": profile.model_dump(),
         "preferences": preferences,
         "decisions": decisions  # list[dict]
     }
     ```

2. **Update `fetch_profile` node** (`app/agent/main/nodes.py`):
   - In the existing `fetch_profile` function, add a third store query alongside the profile and preferences fetches:
     ```python
     decisions_items = await store.asearch((user_id, "decisions"))
     ```
   - Parse into `DecisionLog` models. Take only the **last 10** entries to avoid bloating the prompt context.
   - Return the decisions in the state dict: `return {"user_profile": profile_dict, "preferences": preferences, "recent_decisions": decisions_list}`.

3. **Update `AgentState`** (`app/agent/state.py`):
   - Add `recent_decisions` using `NotRequired` (since `AgentState` is a `TypedDict`, NOT a Pydantic model — default values are not supported):
     ```python
     from typing import NotRequired
     recent_decisions: NotRequired[list[dict[str, Any]]]
     ```
   - All access MUST use `state.get("recent_decisions", [])` to avoid `KeyError`.

4. **Update `main_chatbot` node** (`app/agent/main/nodes.py`):
   - Read `state.get("recent_decisions", [])` and format it into the system prompt.
   - Add a helper `_format_decisions_summary(decisions)` that outputs something like:
     ```
     Recent Feedback:
     - PASSED "Fullstack Dev" at FintechCorp — "Builds internal tooling for trading desks": "Legacy technology stack"
     - PASSED "Senior Python" at AgencyX — "Client-facing Python consultancy role": "Agency model"
     ```
   - Include `description` (the job snippet) between the job title/company and the reason, separated by `—`. If `description` is `None`, omit the `—` segment entirely.
   - If `decisions` is empty, return `"No feedback history yet."` (consistent with `_format_profile_summary` and `_format_preferences_summary` patterns).

5. **Update system prompt** (`app/agent/main/prompts.py`):
   - Add a `{decisions_summary}` placeholder to `SYSTEM_PROMPT`.
   - Add a prompt section:
     ```
     **RECENT USER FEEDBACK:**
     {decisions_summary}
     Use this history to avoid suggesting similar jobs. Do not mention this feedback log explicitly unless the user asks about it.
     ```

#### Explicit Constraints & Warnings
- **Do NOT create a separate service class for the profile endpoint.** It's already a simple store read. Adding a service layer here would be over-engineering.
- **Limit decisions to 10 in the agent context.** The full history is available via `GET /api/profile` for the UI, but the LLM prompt should only see recent entries to avoid token waste.
- **The `recent_decisions` state field uses `NotRequired`.** It must be accessed via `state.get("recent_decisions", [])` so existing graph executions (before any feedback exists) don't break.
- **Steps 4 and 5 MUST be implemented atomically.** The `SYSTEM_PROMPT` template and the `main_chatbot` `.format()` call must be updated together. Adding `{decisions_summary}` to the prompt without passing the value in `.format()` will raise `KeyError` and crash every chat request.
- **Do NOT change the `POST /api/chat` response shape yet.** The chat response remains `{user_message, ai_message, jobs}`. Preferences are fetched separately via `GET /api/profile`.

#### Acceptance Criteria
- [Automated] `pytest` test: after writing 2 `DecisionLog` entries to the store, calling `GET /api/profile` returns a JSON body with `profile`, `preferences`, and `decisions` keys, where `decisions` is a list of length 2 sorted by timestamp descending.
- [Automated] Unit test for `_format_decisions_summary`: given a list of 2 decision dicts, verify the output string contains both job titles and reasons.
- [Manual] Start the backend, submit a feedback via `POST /api/feedback`, then run a chat query. Check the backend logs to verify `fetch_profile` now logs a `decisions_count` alongside the existing `pref_count`.

---

### Ticket 3.3: Frontend — Types, Stores & API Client

#### Overview
Build the entire frontend data layer for Sprint 3. This ticket creates no UI — it strictly covers the `src/core/` boundary: TypeScript interfaces, API client functions, and Zustand stores. The UI components in Ticket 3.4 depend entirely on the contracts established here.

#### Implementation Steps

1. **Update TypeScript Types** (`frontend/src/core/types/api.ts`):
   - Add `id: string` to the existing `Job` interface. This field is now provided by the backend `JobListing` model (added in Ticket 3.1).
   - Add the following new interfaces:
     ```typescript
      export interface Preference {
        key: string;
        value: string | number | boolean | string[];
        category: "hard" | "soft";
        sentiment: "positive" | "negative";
      }

     export interface DecisionLogEntry {
       job_title: string;
       company: string;
       action: "pass" | "pursue";
       description: string | null;
       reason: string | null;
       timestamp: string; // ISO 8601
     }

      export interface ProfileResponse {
        profile: {
          id: number;
          name: string | null;
          role: string | null;
          cv_summary: string | null;
          cv_uploaded: boolean;
        };
       preferences: Record<string, Preference>;
       decisions: DecisionLogEntry[];
     }

     export interface FeedbackRequest {
       job_title: string;
       company: string;
       action: "pass" | "pursue";
       description: string | null;
       reason: string | null;
     }
     ```

2. **Add API Client Functions** (`frontend/src/core/api/profile.ts` — new file):
   - Create `frontend/src/core/api/profile.ts`.
   - Export `fetchProfileRequest(): Promise<ProfileResponse>` — calls `GET /api/profile`.
   - Export `submitFeedbackRequest(body: FeedbackRequest): Promise<void>` — calls `POST /api/feedback` with `Content-Type: application/json`. Does not return a meaningful value; throws on non-2xx.
   - Both functions use the same `fetch` pattern as `frontend/src/core/api/chat.ts`. No raw `fetch()` calls in components.

3. **Create `useProfileStore`** (`frontend/src/core/store/useProfileStore.ts` — new file):
   - This store is the single source of truth for the Profile tab data.
   - State shape:
     ```typescript
     interface ProfileState {
       profile: ProfileResponse["profile"] | null;
       preferences: Record<string, Preference>;
       decisions: DecisionLogEntry[];
       isPending: boolean;
       fetchProfile: () => Promise<void>;
     }
     ```
   - `fetchProfile` action: sets `isPending: true`, calls `fetchProfileRequest()`, updates `profile`, `preferences`, and `decisions` from response, sets `isPending: false`. On error, logs to `console.error` and sets `isPending: false` without mutating existing state.

4. **Update `useJobStore`** (`frontend/src/core/store/useJobStore.ts`):
   - Add `submitFeedback(job: Job, action: "pass" | "pursue", reason: string | null): Promise<void>` action.
   - **Optimistic removal first**: synchronously filter out `job.id` from the `jobs` array before making any network call.
   - Then call `submitFeedbackRequest({ job_title: job.title, company: job.company, action, description: job.description ?? null, reason })`.
   - On network error: log to `console.error`. Do **not** roll back the optimistic removal — the card is already gone from the user's perspective; re-appearing it is more jarring than leaving it gone.
   - After successful feedback, call `useProfileStore.getState().fetchProfile()` to refresh the Profile tab's decision log.

#### Explicit Constraints & Warnings
- **Do NOT call `fetch()` directly in any store action.** All network calls go through `src/core/api/`. This is the `core/` architectural boundary rule.
- **`Job.id` is now required.** The old composite key (`company + title`) used in `DiscoveryDeck` for the React `key` prop must be updated to use `job.id` in Ticket 3.4.
- **Update all existing test fixtures** that create `Job` mock objects (`useJobStore.test.ts`, `useChatStore.test.ts`, `JobCard.test.tsx`, `DiscoveryDeck.test.tsx`) to include the `id: string` field. This is required to pass `tsc --noEmit`.
- **Fix `setJobs([])` in `useChatStore.sendMessage`:** The current `else` branch at line 66 calls `setJobs([])` when the agent returns no jobs, which wipes the Discovery Deck. Change the logic to only call `setJobs()` when `response.jobs.length > 0` — remove the `else` branch entirely. This is a prerequisite for Ticket 3.4 (preference deletion via chat will trigger this bug).
- **Do NOT add `useProfileStore` state to `useChatStore`.** They are separate concerns. Profile data is fetched on-demand when the Profile tab is opened, not on every chat message.
- **The optimistic removal is irreversible by design.** We are not implementing undo in this sprint.
- **Preferences in `ProfileResponse` are a `Record<string, Preference>` (dict keyed by preference key).** This matches the existing backend response shape from `GET /api/profile`.

#### Acceptance Criteria
- [Automated] `useProfileStore.test.ts`: mock `fetchProfileRequest` to return a fake `ProfileResponse`. Call `fetchProfile()`. Assert `profile`, `preferences`, and `decisions` are set correctly in the store and `isPending` returns to `false`.
- [Automated] `useJobStore.test.ts`: add a test for `submitFeedback`. Seed the store with 2 jobs. Call `submitFeedback(jobs[0], "pass", "Too senior")`. Assert the `jobs` array immediately drops to length 1 (optimistic removal). Assert `submitFeedbackRequest` was called with the correct payload (mock the API module with `vi.mock`).
- [Automated] `tsc --noEmit` passes with no type errors — verify `Job.id` is referenced correctly as `string`, not `string | undefined`.
- [Manual] In the browser console, call `useProfileStore.getState().fetchProfile()` after submitting a feedback. Verify the store's `decisions` array contains the new entry.

---

### Ticket 3.4: Frontend — Tabbed Right Pane, ProfileView & JobCard Wiring

#### Overview
This is the UI integration ticket. It introduces a tab system in the right pane (switching between Discovery Deck and Profile), creates the `ProfileView` component for rich memory display, and wires the "Pass" button on `JobCard` to the feedback flow. The Stitch profile design (`documents/stitch_migration/stich_profile.html`) provides visual direction for the Profile tab — use it for glass-panel styling, typography, and layout inspiration, but note that not all UI elements in the design are implemented (e.g., "Add Constraint" button is intentionally excluded).

#### Implementation Steps

1. **Tabbed Right Pane** (`frontend/src/app/page.tsx`):
   - Replace the current `<DiscoveryDeck />` with a tab container.
   - Add local state: `const [activeTab, setActiveTab] = useState<"discovery" | "profile">("discovery")`.
   - Render a tab header above the content area with two buttons: `Discovery` and `Profile`. Use the styling from the Stitch profile design (lines 158-167): `px-8 pt-6 pb-2`, `border-b border-glass-border`, active tab uses `border-b-2 border-primary text-white`, inactive tab uses `text-slate-400 border-transparent`.
   - Conditionally render `<DiscoveryDeck />` or `<ProfileView />` based on `activeTab`.
   - **Refactor `DiscoveryDeck.tsx`**: Remove its internal `<h2>Discovery Deck</h2>` header and subtitle — the tab bar replaces them. Move the match count (`Found X matches`) to a subtitle line below the tab bar, visible only when the Discovery tab is active.
   - When `activeTab` changes to `"profile"`, call `useProfileStore.getState().fetchProfile()` to hydrate the Profile tab on demand.

2. **Create `ProfileView` Component** (`frontend/src/components/ProfileView.tsx` — new file):
   - `"use client"` component.
   - Consumes state from `useProfileStore`: `profile`, `preferences`, `decisions`, `isPending`.
   - **Loading State**: When `isPending` is `true`, render a centered spinner or pulsing skeleton (same aesthetic as the rest of the app).
   - **Empty State**: When `profile` is `null` and `isPending` is `false`, render a message: *"I don't know much about you yet. Upload your CV or tell me about yourself in the chat."*
   - **Populated State**: Three sections, each in a `glass-panel rounded-2xl` card:

     **Section A: Identity Card**
     - Avatar placeholder (a `size-20 rounded-full` div with gradient background).
     - User name (`profile.name`) in `text-xl font-bold text-white`.
     - Role (`profile.role`) in `text-primary font-medium text-sm`.
     - AI Summary: if `profile.cv_summary` exists, render it in a nested `bg-surface-dark/50 border border-glass-border rounded-xl p-4` sub-card labeled "AI Summary" with the `auto_awesome` material icon (see Stitch profile design lines 179-186).

     **Section B: Search Preferences**
     - Two-column grid (`grid grid-cols-1 md:grid-cols-2`) split into "Looking For" (green header, `check_circle` icon) and "Avoiding" (red header, `cancel` icon).
     - Iterate over `Object.entries(preferences)`. Classify using the `sentiment` field from the backend `Preference` model: `sentiment === "positive"` → "Looking For"; `sentiment === "negative"` → "Avoiding".
     - Each preference renders as a list item with `text-sm text-slate-200` label, and a hover-reveal `close` button (`opacity-0 group-hover:opacity-100`) for deletion.
     - Clicking the `close` button calls `useChatStore.getState().sendMessage(`Remove my preference for "${key}"`)` — this routes through the agent's existing `delete_preference` tool. **Do NOT create a new REST endpoint for preference deletion in this sprint.**

     **Section C: Decision Log (Passed Jobs)**
     - Header: "Passed Jobs Feedback" with `history` icon.
     - Iterate over `decisions` array (already sorted by timestamp descending from the backend).
     - Each entry renders as a sub-card with: an icon (`corporate_fare` material icon), job title + company in `text-sm font-semibold text-white`, timestamp in `text-[10px] text-slate-500`, description snippet (if provided) in `text-xs text-slate-400 italic`, and reason text (if provided) in `text-sm text-slate-300` with the reason phrase highlighted in `text-indigo-300`.
     - If `decisions` is empty, render: *"No feedback yet. Pass or pursue some jobs to see your decision history here."*

3. **Wire `JobCard` "Pass" Button** (`frontend/src/components/JobCard.tsx`):
   - The "Pass" button currently has no `onClick` handler.
   - Add local state: `const [showReasonInput, setShowReasonInput] = useState(false)` and `const [reason, setReason] = useState("")`.
   - On "Pass" click: toggle `showReasonInput` to `true`. This reveals a small inline row below the buttons: a text input (`placeholder="Why? (optional)"`) and two small buttons: "Skip" and "Submit".
   - "Skip" calls `useJobStore.getState().submitFeedback(job, "pass", null)` and hides the input.
   - "Submit" calls `useJobStore.getState().submitFeedback(job, "pass", reason)` and hides the input.
   - The entire reason-input row should match the app's design language: `bg-surface-dark/50 border border-glass-border rounded-lg` input, small `text-xs` buttons.

4. **Update `DiscoveryDeck` keys** (`frontend/src/components/DiscoveryDeck.tsx`):
   - Replace the existing composite key `key={`${job.company}-${job.title}`}` with `key={job.id}`.
   - Pass `job` (including `id`) as a prop to `JobCard`.

#### Explicit Constraints & Warnings
- **The Stitch profile design is a visual guide, not a spec.** It includes an "Add Constraint" button — do NOT implement this. The Profile tab is read-mostly; the user corrects preferences via chat.
- **Do NOT create a `DELETE /api/preferences/:key` REST endpoint.** Preference deletion in this sprint goes through the chat agent's existing `delete_preference` tool via `sendMessage`. This keeps the architecture simple and avoids duplicating tool logic into REST endpoints.
- **ProfileView must handle all three states: loading, empty, and populated.** Do not skip the empty state — it's the first-run experience.
- **Do NOT fetch profile data on every page load.** Only fetch when the Profile tab is activated. The Advisory Feed and Discovery Deck should not pay the cost of a `/api/profile` call they don't need.
- **The reason input on JobCard is optional UX.** If it proves too complex, a simple `window.prompt("Why? (optional)")` is an acceptable fallback for this sprint. Premium styling can come later.
- **`JobCard` now requires `job.id` to exist.** If for any reason the backend returns a job without an `id`, the component must not crash. Use a fallback: `job.id ?? \`${job.company}-${job.title}\``.
- **"Pursue" feedback is out of scope for Sprint 3.** The Pursue button remains an `<a>` link opening `apply_link` in a new tab. Wiring `submitFeedback(job, "pursue", null)` is deferred to Sprint 4.
- **Add `custom-scroll` CSS utility to `globals.css`.** It's used in `DiscoveryDeck` and `ProfileView` but never defined. Add the Stitch design's scrollbar styles:
  ```css
  .custom-scroll::-webkit-scrollbar { width: 6px; }
  .custom-scroll::-webkit-scrollbar-track { background: transparent; }
  .custom-scroll::-webkit-scrollbar-thumb { background-color: rgba(255, 255, 255, 0.1); border-radius: 20px; }
  ```
- **Update `DiscoveryDeck.test.tsx`** mock fixtures to include `id` field on `Job` objects.

#### Acceptance Criteria
- [Automated] `ProfileView.test.tsx`: mock `useProfileStore` to return `isPending: true` → assert loading indicator renders. Mock to return `profile: null, isPending: false` → assert empty state text renders. Mock with full profile data → assert name, role, AI Summary, at least one preference, and at least one decision log entry all render.
- [Automated] `JobCard.test.tsx`: update existing tests. Simulate click on "Pass" → assert the reason input appears. Simulate typing a reason and clicking "Submit" → assert `submitFeedback` was called with the correct `job`, `"pass"`, and the typed reason.
- [Automated] `page.test.tsx` (or integration): verify both tabs render and switching between them toggles the visible component.
- [Manual] Open `http://localhost:3000`. Click the "Profile" tab. Verify the loading spinner appears briefly, then profile data populates. Switch back to "Discovery". Verify job cards still render. Click "Pass" on a card → type a reason → click "Submit". The card disappears. Switch to "Profile" tab. Verify the decision log shows the entry you just submitted.

---

## Manual Verification (End of Sprint 3)

This is the definitive end-to-end test for Sprint 3. It proves that all four tickets work as a system, not just in isolation.

**Prerequisites**: Backend running (`./scripts/dev.sh`), frontend running (`npm run dev`), backend has valid `ADZUNA_APP_ID`. Start with a **reset profile** (`curl -X DELETE http://localhost:8000/api/profile/reset`).

### Step 1: Verify the Empty Profile State
- Open `http://localhost:3000`.
- Click the **Profile** tab in the right pane.
- **Expected**: A brief loading state, then an empty-state message: *"I don't know much about you yet..."*
- The Discovery tab should still show its empty state ("No jobs yet") when you switch back.

### Step 2: Build the Profile via Chat
- In the Advisory Feed, type: *"Hi, I'm a Senior Python Engineer looking for remote-only roles at startups. I hate agencies and Java."*
- **Expected**: The agent responds conversationally. It calls `update_my_profile` (name, role) and `save_preference` (remote, no-agency, no-java) in the background.
- Switch to the **Profile** tab and click refresh (or re-click the tab to re-fetch).
- **Expected**: The Identity Card shows name and role. The Preferences section shows "Remote First" and "Startups" under "Looking For", and "Java" / "Agencies" under "Avoiding".

### Step 3: Discover Jobs
- Switch to the **Discovery** tab.
- Type: *"Find me Python backend jobs."*
- **Expected**: The Discovery Deck populates with job cards. The agent, having read the preferences, should not be suggesting Java or agency roles.

### Step 4: Pass a Job with a Reason
- Find any job card and click **Pass**.
- **Expected**: A small reason-input row appears below the buttons.
- Type a reason: *"Too much legacy code"*.
- Click **Submit**.
- **Expected**: The card disappears immediately (optimistic removal). No page reload needed.
- Open browser DevTools → Network tab. Verify a `POST /api/feedback` request fired with `{"action": "pass", "reason": "Too much legacy code", ...}` and received `{"status": "ok"}`.

### Step 5: Verify the Decision Log
- Switch to the **Profile** tab.
- **Expected**: The "Passed Jobs Feedback" section now shows one entry: the job you just passed, with the reason *"Too much legacy code"* highlighted.

### Step 6: Verify the Agent Learns
- Switch back to **Discovery**.
- Type: *"Show me more similar roles."*
- **Expected**: The agent responds with a new batch of jobs. Check backend logs to confirm `fetch_profile` loaded `decisions_count: 1`. The agent should ideally avoid suggesting the same company or role type you just passed on.

### Step 7: Correct a Preference via Chat
- In the Advisory Feed, type: *"Actually, I'm fine with hybrid roles now."*
- **Expected**: The agent calls `delete_preference("location")` or equivalent, responds confirming the change.
- Switch to the **Profile** tab.
- **Expected**: The hybrid/remote constraint is gone from the Preferences section.
