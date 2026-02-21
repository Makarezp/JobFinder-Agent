# Sprint 3: The Interactivity Loop (Zustand Feedback Actions)

(in progress do not implement, needs more refinment)

**Goal**: Implement the core "Tinder for Jobs" learning loop. Actioning a card in the Next.js UI executes logic entirely within the `src/core/store` Zustand store, which handles the optimistic UI removal and the POST webhook to FastAPI.

---

## Detailed Ticket Breakdown

### Ticket 3.1: Backend Schema Evolution (`schemas.py` & `routes.py`)

#### Overview
To facilitate the interactivity loop and accurately track preferences, the backend must uniquely identify parsed jobs, and the Chat endpoint must return the user's current learned preferences on every cycle.

#### Implementation Steps
1. **Job ID Tracking**:
   - In `app/agent/schemas.py`, update `JobListing` to include `id: str = Field(..., description="Unique ID for this job listing")`. Ensure the Adzuna search nodes correctly populate this.
2. **Preference Hydration**:
   - In `app/api/routes.py`, refactor the `POST /api/chat` response to include a fourth key: `preferences: List[dict]`.
   - Modify `chat_endpoint` to execute `store.search(("default_user", "preferences"))` alongside the LangGraph invocation, appending the retrieved `Preference` Pydantic models to the final JSON return payload.

### Ticket 3.2: Zustand Feedback Action

#### Overview
Implement the orchestration logic purely inside the `src/core/` boundary.

#### Implementation Steps
1. **Zustand Action**:
   - Inside `src/core/store/useJobStore.ts`, create an action: `submitFeedback(job: Job, actionType: 'pass' | 'pursue')`.
2. **Optimistic UI**:
   - Within this action, synchronously filter the active `jobs` array to remove `job.id`, causing Next.js to immediately unmount the `JobCard`.
3. **Synthetic Chat Invocation**:
   - We do *not* use a webhook. Instead, we rely on the Agent's existing `save_preference` tool.
   - Within `submitFeedback`, execute `useChatStore.getState().sendMessage(syntheticPrompt, true)`.
   - The `syntheticPrompt` should be a structured string like: `[SYSTEM_FEEDBACK]: The user clicked {actionType.toUpperCase()} on the job {job.title} at {job.company}. Do not suggest similar jobs. If it's obvious why, use save_preference to filter future searches. If not, briefly ask them why.` The second parameter `true` should instruct the UI to hide this message from the user's visible chat feed.
   - When the `/api/chat` fetch resolves, grab the newly appended `response.preferences` array and write it to `usePreferenceStore.ts`.

### Ticket 3.3: Pass/Pursue UI & The Reactive Pulse Banner

#### Overview
Wire the UI interactions in Next.js back to the newly created core logic.

#### Implementation Steps
1. **Interactive Elements**:
   - In `frontend/src/components/JobCard.tsx`, wire the "Pass" and "Pursue" buttons directly to `submitFeedback`.
2. **The Pulse Banner**:
   - Create `frontend/src/components/PulseBanner.tsx`.
   - Consume the state natively: `const preferences = usePreferenceStore((state) => state.preferences)`.
   - Render these preferences (e.g., "Excluding: Django") as small styled badges at the top of the `DiscoveryDeck`. Ensure it only renders if `preferences.length > 0`.

#### Acceptance Criteria
- Clicking "Pass" gracefully hides a `JobCard`.
- The Zustand store successfully dispatches a hidden synthetic message to `/api/chat`.
- The backend LangGraph agent processes the context, potentially invokes `save_preference`, and returns the updated `preferences` array.
- The `PulseBanner` naturally renders the new restriction badge from the Zustand state.

---

### Ticket 3.4: Logic Integration Testing

#### Overview
Ensure the Zustand feedback store correctly intercepts UI actions, mutates state optimistically, and triggers API side effects cleanly.

#### Implementation Steps
1. **Zustand Logic Tests (`Vitest`)**:
   - Create `src/core/store/useFeedbackStore.test.ts`.
   - Test the `submitFeedback` action. Verify that calling `submitFeedback(job, 'pass')` correctly updates the optimistic jobs array and triggers the mocked `sendMessage` on the chat store with the required hidden `[SYSTEM_FEEDBACK]` string.
2. **PulseBanner Component Tests (`RTL`)**:
   - Create `src/components/PulseBanner.test.tsx`.
   - Mock the `usePreferenceStore` to simulate the backend having learned 2 exclusions.
   - Verify the `PulseBanner` component visually renders the 2 distinct restriction badges.

#### Acceptance Criteria
- Tests ensure the UI buttons for interaction are correctly wired to both state updates and network requests without brittle logic.

---

## Manual Verification (End of Sprint 3)

To definitively prove Sprint 3 (and the complete core MVP) is finished, execute an end-to-end "Tinder for Jobs" graphical session:

1. **Initial Population**:
   - Open `http://localhost:3000`.
   - Ask the AI for "Remote junior Node.js jobs". Wait for the `DiscoveryDeck` to populate with results.

2. **Interaction Flow**:
   - On the top `JobCard`, hover over the "Pass" (X) button. Ensure the interaction ring/color changes.
   - Click the "Pass" button.
   - Verify that specific card instantly unmounts from the UI stack and the next card taking its place.

3. **Pulse Banner Hydration**:
   - Wait for the synthetic `/api/chat` request to complete in the background (you may see a loading indicator).
   - Verify the agent naturally replies in the chat feed (e.g., "I saw you passed on X, why was that?").
   - Verify the `PulseBanner` elegantly appears/slides down at the top of the `DiscoveryDeck` once the agent invokes `save_preference`.
   - Verify it accurately states what the AI just learned.

4. **Network Verification**:
   - Open Chrome DevTools -> Network Tab.
   - As you click Pass or Pursue on the cards, verify that a `POST /api/chat` request is being dispatched to the FastAPI backend containing the synthetic `[SYSTEM_FEEDBACK]` message payload.
   - Verify that when the response returns, the `preferences` JSON array contains updated LangGraph constraints, proving the AI tooling correctly fired.
