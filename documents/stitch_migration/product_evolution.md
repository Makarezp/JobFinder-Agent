# Product Evolution Strategy: CVviewer Web (Next.js)

## 1. The Learning Loop
Visualizing and using "What I've Learned" in real-time.

*   **The "Advisory Pulse" Widget**: Instead of hiding preferences in a separate profile page, we inject a small `PulseBanner` component above the job results. It reads directly from a global Zustand store in the `src/core/store` directory.
*   **Feedback Integration**: Every `JobCard` has an explicit "Pass" or "Pursue" action. When "Pass" is clicked, the Zustand `useJobStore` instantly removes the card from local state and orchestrates a background API call to `/api/feedback`.
*   **Code Implementation**: The `src/core/api` folder handles the API client logic, completely decoupled from the Next.js UI tier.

## 2. Interactivity & Screens: The Next.js UI Flow
The Next.js UI is structured around distinct functional panels, each consuming specific slices of the Zustand store:

1.  **`CommandCenter` (The Chat Input)**: A persistent bar at the bottom. Triggers the `sendMessage` action in the Zustand store.
2.  **`AdvisoryFeed` (The Agent's Voice)**: Consumes the message history from `useChatStore` to render conversational explanations.
3.  **`DiscoveryDeck` (The Job Cards)**: Consumes the active jobs array from `useJobStore`. Re-renders independently from the chat feed when new jobs arrive via JSON.
4.  **`PulseBanner` (Memory Drawer)**: Consumes the preferences array from the core store. Automatically responds when the feedback webhook returns updated learning variables.

## 3. Agent Organization: Searching vs. Advising
In the Python backend `app/agent/graph.py`, we maintain two gears:

*   **The Executor (Searching)**: Highly constrained to `app/tools/adzuna_api.py`.
*   **The Navigator (Advising)**: A routing layer in LangGraph that evaluates raw results against the `MemoryStore` and injects narrative explanations into the `ai_message` alongside the JSON jobs array.

## 4. UI/UX Design System: Stitch Integration
*   The premium visual layout designed by Stitch (with its dark-themed indigo accents) will be implemented using TailwindCSS in the `frontend` Next.js project.
*   The Left Pane (60%) will house the `AdvisoryFeed`, and the Right Pane (40%) will house the `DiscoveryDeck`. The Next.js framework will easily handle the responsive flexbox layouts provided by the Stitch prototypes.

## 5. Maximum Logic Reuse (Unified Architecture)
By strictly keeping all business logic (Zustand, types, fetch clients) inside `frontend/src/core/`, we ensure it remains 100% independent of React UI rendering. If we migrate to React Native later, the `src/core/` folder can be copied identically to the mobile app without requiring any refactoring.
