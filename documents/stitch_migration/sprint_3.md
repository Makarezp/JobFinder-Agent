# Sprint 3: The Interactivity Loop (Zustand Feedback Actions)

(in progress do not implement, needs more refinment)

**Goal**: Implement the core "Tinder for Jobs" learning loop. Actioning a card in the Next.js UI executes logic entirely within the `src/core/store` Zustand store, which handles the optimistic UI removal and the POST webhook to FastAPI.

---

## Detailed Ticket Breakdown

### Ticket 3.1: The Webhook Route (`routes.py`)

#### Overview
Before wiring the frontend, the FastAPI backend needs an endpoint to receive the learning feedback.

#### Implementation Steps
1. **The Webhook Route**:
   - Define `class JobFeedbackRequest(BaseModel): job_id: str; company: str; title: str; action: Literal["pass", "pursue"]; reason: str`.
   - Create `@router.post("/api/feedback")` that extracts these values, constructs a `Preference` model, updates the LangGraph memory store natively, and returns the newly updated master preferences array.

### Ticket 3.2: Zustand Feedback Action

#### Overview
Implement the orchestration logic purely inside the `src/core/` boundary.

#### Implementation Steps
1. **Zustand Action**:
   - Inside `src/core/store/useJobStore.ts`, create an action: `submitFeedback(jobId, actionType)`.
2. **Optimistic UI**:
   - Within this action, synchronously filter the active `jobs` array to remove `jobId`, causing Next.js to immediately unmount the `JobCard`.
3. **API Orchestration**:
   - Execute an async `fetch('/api/feedback', ...)` with the correct feedback payload.
   - Upon receiving the JSON response of updated preferences, write that array to a new Zustand state slice (e.g., `usePreferenceStore.ts`).

### Ticket 3.3: Pass/Pursue UI & The Reactive Pulse Banner

#### Overview
Wire the UI interactions in Next.js back to the newly created core logic.

#### Implementation Steps
1. **Interactive Elements**:
   - In `frontend/src/components/JobCard.tsx`, wire the "Pass" and "Pursue" buttons directly to `submitFeedback`.
2. **The Pulse Banner**:
   - Create `frontend/src/components/PulseBanner.tsx`.
   - Consume the state natively: `const preferences = usePreferenceStore((state) => state.preferences)`.
   - Render these preferences (e.g., "Excluding: Django") as small styled badges at the top of the `DiscoveryDeck`.

#### Acceptance Criteria
- Clicking "Pass" gracefully hides a `JobCard`. The core package successfully updates the Python memory store. A split second later, the Next.js `PulseBanner` naturally re-renders pulling from the centralized Zustand state, showing the Agent learned the new restriction.

---

### Ticket 3.4: Logic Integration Testing

#### Overview
Ensure the Zustand feedback store correctly intercepts UI actions, mutates state optimistically, and triggers API side effects cleanly.

#### Implementation Steps
1. **Zustand Logic Tests (`Vitest`)**:
   - Create `src/core/store/useFeedbackStore.test.ts`.
   - Test the `submitFeedback` action. Mock the `fetch`/API call. Verify that calling `submitFeedback(jobId, 'pass')` correctly updates the optimistic jobs array and triggers the mock `fetch`.
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
   - Wait 1-2 seconds for the `/api/feedback` webhook to complete in the background.
   - Verify the `PulseBanner` elegantly appears/slides down at the top of the `DiscoveryDeck`.
   - Verify it accurately states what the AI just learned (e.g., "Excluding: This particular company/tech").

4. **Network Verification**:
   - Open Chrome DevTools -> Network Tab.
   - As you click Pass or Pursue on the cards, verify that a `POST /api/feedback` request is being dispatched to the FastAPI backend containing the correct JSON payload (`job_id`, `action`).
   - Verify this network request does not block the UI or cause the Next.js page to freeze while the backend processes the LangGraph update.
