# Sprint 3: The Interactivity Loop (Stateful REST Updates)
**Goal**: Implement the Feedback loop so the Agent learns from UI swipe/click interactions. React manages the fluid card expulsion animations, while sending standard JSON payloads to a FastAPI webhook to update Agent memory.

*   **Ticket 3.1**: *Pass/Pursue Interactive UI.*
    *   Add `<TouchableOpacity>` buttons to `JobCard.tsx` (and prepare for future Swiping logic).
    *   Create a REST route `/api/feedback` in `routes.py`.
*   **Ticket 3.2**: *Memory Integration.*
    *   Update `ChatService` to accept this JSON feedback and inject it into the LangGraph state.
*   **Ticket 3.3**: *The Reactive Pulse Banner.*
    *   Create `components/PulseBanner.tsx`.
    *   When the `/api/feedback` `fetch` returns successfully, update the global React state so the Pulse Banner re-renders instantly with the new user preferences.

*   **Definition of Done (DoD)**: A user clicks "Pass" on a `JobCard`. The card gracefully animates off the screen (local state update). A background fetch sends the data to `/api/feedback`, updating the memory store. React receives the new preferences JSON and immediately reflects the new constraint in the `PulseBanner` component.

---

## Detailed Ticket Breakdown

### Ticket 3.1: Pass/Pursue UI & The Webhook

#### Overview
Make the React Native job cards interactive. Clicking "Pass" sends a strict JSON feedback loop to FastAPI.

#### Implementation Steps
1. **Interactive Elements**:
   - In `JobCard.tsx`, add `<TouchableOpacity>` elements for "Pass" (red) and "Pursue" (indigo).
   - Add an `onPress={handlePass}` handler.
2. **Local UI State Expulsion**:
   - Immediately filter the `deckJobs` array in the parent state: `setDeckJobs(prev => prev.filter(j => j.id !== job.id))`.
3. **The Webhook Route (`routes.py`)**:
   - Define a Pydantic model: `class JobFeedbackRequest(BaseModel): job_id: str; company: str; title: str; action: Literal["pass", "pursue"]; reason: str`.
   - Create a REST endpoint: `@router.post("/api/feedback")` that accepts `JobFeedbackRequest` and `StoreDep`.

### Ticket 3.2: Native Memory Integration

#### Overview
We need to map the JSON REST payload directly into the `BaseStore` inside the LangGraph infrastructure so that future queries exclude or target these constraints.

#### Implementation Steps
1. **Model Instantiation**:
   - Inside the `/api/feedback` endpoint, take the `JobFeedbackRequest` values and construct an `app.agent.memory_schema.Preference` model. For example, if action is "pass", set `avoid=True` and summarize the reason.
2. **Update Store**:
   - Execute an asynchronous put command: `await store.aput((DEFAULT_USER_ID, "preferences", str(uuid.uuid4())), "data", pref.model_dump())`
3. **Return Context**:
   - Immediately run an `await store.asearch((DEFAULT_USER_ID, "preferences"))` to fetch the complete updated list of preferences and return it as the JSON response to the `fetch` call.

### Ticket 3.3: The Reactive Pulse Banner

#### Overview
Users need visual reassurance that the Agent is successfully learning. We replace HTMX OOB swaps with pure React reactivity.

#### Implementation Steps
1. **Create the Component**: Create `frontend/components/PulseBanner.tsx`. It displays horizontal pills or text (e.g., "Excluding: Django").
2. **Global State Context**:
   - Introduce a `const [preferences, setPreferences] = useState([])` alongside the jobs data.
3. **Feedback Response Handling**:
   - When the `fetch` POST to `/api/feedback` succeeds, the FastAPI backend should return the newly updated user preferences list.
   - React takes this response (`const newPrefs = await response.json()`) and calls `setPreferences(newPrefs)`.
   - Since `PulseBanner` receives `preferences` as a prop/context, it seamlessly re-renders the new banner tag globally.
