# Specification: Contextual Workspaces

## 1. Overview
*   **Summary:** Refactoring the frontend UI and state management to implement a "Contextual Workspaces" model. The application will transition from a single, generic chatbot alongside a dashboard to dedicated, tab-specific AI workspaces (e.g., a Discovery Workspace and a Profile Workspace).
*   **Context:** Currently, the app uses a fixed 40/60 layout where a single chat thread remains present across all tabs. This mixes unrelated conversation contexts (e.g., 20 minutes of job filtering mixed with resume updates), which confuses the user experience and the LLM's state. Creating context-isolated workspaces ensures the AI acts as a specialized agent for the exact task the user is performing.

## 2. Functional Requirements
*   [ ] **Global Navigation Shift:** Move the primary tab navigation (Discovery, Profile) to the top level of the application, controlling the active workspace.
*   [ ] **Workspace Layout (60/40 Split):** Each active tab Must implement its own 60/40 layout (Left: Agent Chat Console, Right: Visual Canvas like the Job Deck or Profile Data).
*   [ ] **Thread Isolation (Frontend):** Modify the chat state management (`useChatStore`) to support multiple active threads based on the active tab, ensuring conversations don't bleed across workspaces.
*   [ ] **Context Injection (Single Gateway):** Update the frontend chat payload to append a `workspace` property (e.g., `workspace: "discovery"`) alongside the message to `/api/chat`.
*   [ ] **Backend Dynamic Routing (`chat_service.py`):** Intercept the `workspace` property at the `ChatService` level before it enters the graph. Append this workspace name to the user's `thread_id` (e.g., `user123_discovery`) to create mathematically isolated memory checkpoints in LangGraph.
*   [ ] **Backend Specialization & Onboarding Deprecation:** Split the current unified generic agent graph into smaller, focused graphs (e.g., `profile_graph.py` and `discovery_graph.py`).
    *   Deprecate the explicit LangGraph "Onboarding Gate" (`check_onboarding_status` router).
    *   The current `ONBOARDING_CHATBOT_NODE` logic will merge into the new **Profile Agent**. Its core responsibility continues to be extracting CVs and populating preferences.
    *   The current `MAIN_CHATBOT_NODE` logic becomes the **Discovery Agent**.
    *   *Note: Frontend UI-blocking rules regarding incomplete profiles are out-of-scope for this ticket and will be handled in later iterations.*
*   [ ] **Contextual UI Elements:** Limit specific UI controls to relevant workspaces (e.g., the "Attach CV" button should only appear in the Profile workspace's chat console).

## 3. Verification & Acceptance Criteria
*   [ ] When the user switches between the Discovery and Profile tabs, the chat history completely swaps to reflect only the conversation relevant to that tab.
*   [ ] Messages sent from the Discovery tab successfully trigger job searches and do not access profile-updating tools inappropriately.
*   [ ] Messages sent from the Profile tab successfully trigger profile updates and do not trigger job searches.
*   [ ] The right-hand Canvas accurately displays the Discovery Deck in the Discovery workspace, and the Profile View in the Profile workspace.
*   [ ] The backend logs confirm that the LLM is receiving the correct tab-specific context or tools based on the active workspace.
