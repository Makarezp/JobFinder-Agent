# Sprint 2: The Discovery Deck (Stateful Job Stores)

**Goal**: Expand the Zustand business logic to handle complex Job Data structures, and wire that global state up to the Next.js Discovery Deck components independently of the chat feed.

---

## Detailed Ticket Breakdown

### Ticket 2.1: Types and Schema Definitions

#### Overview
Ensure the `src/core` accurately models the data coming from the LangGraph backend.

#### Implementation Steps
1. **Schema Definitions**:
   - In `frontend/src/core/types/api.ts`, define `export interface Job { title: string, company: string, location: string, salary: string | null, description: string, apply_link: string }` based strictly on the FastAPI `JobListing` schema. Note that there is no `id` field provided by the backend.
2. **Update Store Response**:
   - Modify the `useChatStore`'s `sendMessage` action to properly unpack `response.jobs` and dispatch it to a new specialized store `useJobStore.ts` in `src/core/store`.

### Ticket 2.2: Job Card Component

#### Overview
Translate the HTML `<div class="job-card">` from Stitch into a React component.

#### Implementation Steps
1. **Create Component**: Create `frontend/src/components/JobCard.tsx`.
2. **Tailwind Styling**: Recreate the visual hierarchy (background colors, rounded borders, typography) using Next.js and Tailwind.
3. **Data Binding**: Map the strictly-typed `Job` prop to the visual UI elements. Conditionally render Pill Badges for `job.location` and `job.salary` (if it exists).
4. **Link Wiring**: Use the Next.js `<Link>` component or a standard `<a>` tag pointed to `job.apply_link`.

### Ticket 2.3: Deck Layout & State Hydration

#### Overview
Populate the Right Pane mapped out in Sprint 1 with the actual job data driven by the Zustand store.

#### Implementation Steps
1. **Create the Deck**:
   - Create `frontend/src/components/DiscoveryDeck.tsx` (using `"use client"`).
2. **Consume State**:
   - Import the jobs array via `const jobs = useJobStore(state => state.jobs)`.
3. **Render**:
   - When `jobs.length === 0`, render a visually pleasing "Empty State" component (e.g., a faded icon and text encouraging the user to chat with the agent).
   - Otherwise, map over the array, rendering `JobCard` components. Since there is no `id` field from the backend, use a composite key for the React elements (e.g., `key={`${job.company}-${job.title}`}`). Ensure the container has independent vertical scrolling (`overflow-y-auto`).

#### Acceptance Criteria
- When a user asks for jobs in the Next.js frontend, the backend processes it, the Zustand store catches the JSON, and the `DiscoveryDeck` perfectly populates with styled job cards representing real Adzuna data. The chat feed simultaneously updates on the left.
- Before searching, the Deck displays a clear "Empty State" message instead of a buggy broken UI.
- The React key mapping correctly relies on a composite string (e.g. `company + title`) and does not crash, as `id` injection is specifically deferred to Sprint 3.
- `JobCard` pills map strictly to `location` and `salary`, not arbitrary tags.

---

### Ticket 2.4: Component & Logic Testing

#### Overview
Ensure the `JobCard` accurately renders domain models, and the `useJobStore` effectively manages lists of jobs.

#### Implementation Steps
1. **Zustand Logic Tests (`Vitest`)**:
   - Create `src/core/store/useJobStore.test.ts`.
   - Verify the store initializes with an empty jobs array.
   - Verify that when the store receives a standard `[Job, Job]` payload, it correctly maps and sets them in state.
2. **JobCard Component Tests (`RTL`)**:
   - Create `src/components/JobCard.test.tsx`.
   - Mock a backend `Job` object (with fake title, company, location, and salary).
   - Verify the `JobCard` visually renders the title text, the exact salary string, and maps `location` and `salary` to 2 distinct DOM pill elements.
3. **DiscoveryDeck Tests (`RTL`)**:
   - Create `src/components/DiscoveryDeck.test.tsx`.
   - Toggle the mock Zustand state to return 0 jobs, and verify the the "Empty State" string renders. Toggle it to return 2 dummy jobs, and verify 2 `JobCard` components render.

#### Acceptance Criteria
- Running `npm run test` executes logic vs. component tests cleanly and coverage remains >80%.

---

## Manual Verification (End of Sprint 2)

To definitively prove Sprint 2 is complete, manually test the integration between the Chat Feed and the Discovery Deck by running a live search.

1. **Live System Test**:
   - Ensure the FastAPI backend is running with a valid `ADZUNA_APP_ID`.
   - Open `http://localhost:3000`. The Right Pane (`DiscoveryDeck`) should display the new "Empty State" placeholder visually centered.
   - Run a prompt in the Next.js input: "Show me Python Software Engineering jobs, preferably remote."

2. **Simultaneous UI Hydration**:
   - Verify that when the backend JSON arrives, two things happen instantly:
     1. The agent's conversational explanation appears on the left in the `AdvisoryFeed`.
     2. The `DiscoveryDeck` on the right suddenly populates with 3-5 styled `JobCard` components.

3. **Data Integrity Check**:
   - Visually compare the titles/locations rendered in the cards against the raw Adzuna JSON response to verify no data was lost or misaligned during the Zustand mapping phase.
   - Verify the `JobCard` correctly truncated any description text that was overly long to prevent breaking the flex layout.
