# Sprint 2: The Discovery Deck (Stateful API Integration)
**Goal**: Connect the React Native UI to the FastAPI LangGraph backend. When the backend returns jobs JSON, React state updates the new `#discovery-deck` to render the job cards independently of the chat feed.

*   **Ticket 2.1**: *Job Card Extraction.*
    *   Translate the Stitch job card design into a `components/JobCard.tsx`.
*   **Ticket 2.2**: *Deck Layout.*
    *   Create `components/DiscoveryDeck.tsx` containing a generic `<FlatList>` to map over available job data and inject it into the right pane of `app/index.tsx`.
*   **Ticket 2.3**: *API Wiring & Global State.*
    *   Convert FastAPI's `/chat` endpoint to return standard JSON (the chat message text + the `jobs` list).
    *   In the React Native app, wire the `CommandCenter` to execute a `fetch` request, and store the resulting `jobs` array in component state (or a context provider) to trigger the `DiscoveryDeck` re-render.

*   **Definition of Done (DoD)**: A user asks for Jobs. The API responds with JSON. The conversational answer is appended to the `AdvisoryFeed` state, and the `DiscoveryDeck` state updates, instantly populating the right-side panel with highly styled `JobCard` components.

---

## Detailed Ticket Breakdown

### Ticket 2.1: Job Schema vs UI Component

#### Overview
Translate the physical HTML `<div class="job-card">` structure from Stitch into a reusable React Native `components/JobCard.tsx` component. It must strictly type-check against the FastAPI backend's data model.

#### Implementation Steps
1. **Schema Definitions**:
   - Create a `frontend/types/api.ts` file.
   - Define `export interface Job { id: string, title: string, company_name: string, description: string ... }` to exactly match the backend `JobModel` returned by the LangGraph Adzuna tool.
2. **Translate to `<View>`**:
   - Create `frontend/components/JobCard.tsx` accepting `{ job }: { job: Job }`.
   - Use `<View className="bg-gray-800 rounded-xl p-4...">` and `<Text>` to recreate the visual hierarchy.
3. **Data Binding**: Map the typed React prop `job` to the UI elements (e.g., `<Text>{job.title}</Text>`).
4. **Tag Mapping**: Create a helper to map `job.tags` to colored pills/badges using `<View>` with pill-style rounding.

### Ticket 2.2: Deck Layout

#### Overview
We need to allocate the right side of our "Pilot/Navigator" dashboard to house the grid of job cards, distinct from the left-side scrolling chat feed.

#### Implementation Steps
1. **Create the Deck**:
   - Create `frontend/components/DiscoveryDeck.tsx`.
   - Wrap the component in a `ScrollView` or `FlatList` that handles its own independent vertical scrolling.
2. **Dashboard Placement**:
   - Open `frontend/app/index.tsx`.
   - Ensure the Flexbox structure gives space to the Deck (e.g., `flex: 1` or specific width percentages) depending on if we are running in Web mode or Mobile.

### Ticket 2.3: API Wiring & Global State

#### Overview
We manage state purely on the client. The backend `/chat` endpoint (refactored in Sprint 0) returns `{"ai_message": "...", "jobs": [...]}`. React fetches this JSON and maps the `jobs` array directly into the `DiscoveryDeck` state.

#### Implementation Steps
1. **Backend Validation (`routes.py`)**:
   - Ensure the `ChatService._parse_agent_result()` dictionary seamlessly maps the LangGraph `final_answer` jobs payload into the top-level `jobs` key of the JSON response.
2. **Setup Frontend Fetch**:
   - Inside `frontend/app/index.tsx`, update the submit handler in `CommandCenter` to POST the serialized `ChatRequest` to `http://localhost:8000/chat` using `application/json`.
3. **Manage State**:
   - Maintain `const [messages, setMessages] = useState<ChatMessage[]>(...)` and `const [deckJobs, setDeckJobs] = useState<Job[]>(...)`.
   - Upon receiving the JSON response (`const response = await fetch(...)`), deserialize the body. Let `setDeckJobs(response.jobs)`, which triggers `DiscoveryDeck` to render the cards.

#### Acceptance Criteria
- When LangGraph triggers a real job search, the UI updates *both* panels instantly.
- A new chat bubble appears on the left explaining the search.
- The React Native `JobCard` components populate the right side `#discovery-deck` sequentially.
