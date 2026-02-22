# Sprint 1: Premium Shell (Stitch Styling in Next.js)

**Goal**: Take the functional Next.js app from Sprint 0 and apply the premium Stitch design system using Tailwind CSS to establish the layout scaffolding.

---

## Detailed Ticket Breakdown

### Ticket 1.1: Base Layout Infrastructure ✅ DONE

#### Overview
Extract the global "shell" from the Stitch Design reference (`documents/stitch_migration/stitch_design.html`) and apply it to the Next.js `src/app/layout.tsx` and `src/app/page.tsx`.

#### Implementation Steps
1. **Translate Shell**:
   - Open `frontend/src/app/layout.tsx`. Apply the global dark-mode Tailwind classes (e.g., `bg-gray-900 text-white`) to the `<body>`.
2. **Two-Pane Layout**:
   - Open `frontend/src/app/page.tsx`.
   - Create the flexbox grid separating the Left Pane (`AdvisoryFeed` area) from the Right Pane (`DiscoveryDeck` area) as dictated by the Stitch prototypes.

### Ticket 1.2: Command Center Component ✅ DONE

#### Overview
Translate the Stitch dark-mode chat input form from the design reference (`documents/stitch_migration/stitch_design.html`) into a reusable Next.js Server/Client component.

#### Implementation Steps
1. **Create Component**: Create `frontend/src/components/CommandCenter.tsx` (using `"use client"`).
2. **Apply Tailwind**: Style the text input with the rounded corners, background colors, and padding from the Stitch HTML.
3. **SVG Icons**: Utilize standard SVG tags for the paperclip and send icons, styling their hover states with Tailwind. **Crucial:** The paperclip SVG must wrap a visually hidden `<input type="file" accept="application/pdf" />`.
4. **Zustand Wiring & Loading State**:
   - Wire the text input's `onSubmit` to `useChatStore().sendMessage()`.
   - Wire the hidden file input's `onChange` to `useChatStore().uploadCV()`.
   - **Loading UI**: Read a new `isPending` state from `useChatStore`. While true, disable both inputs, change the "send" icon to a loading spinner or pulsing animation, and dim the input area.

### Ticket 1.3: Advisory Feed & Chat Bubbles ✅ DONE

#### Overview
Translate the premium chat bubbles from the Stitch design reference (`documents/stitch_migration/stitch_design.html`) into Next.js components that consume the Zustand `messages` array.

#### Implementation Steps
1. **Create Bubble Component**: Create `frontend/src/components/ChatMessage.tsx`.
2. **Role Styling**: Accept a `role` prop. Use Tailwind template literals to apply styles conditionally (e.g., User gets `bg-indigo-600`, AI gets the premium `#564be7` glassmorphism styling).
   - **Error Styling**: If the AI message begins with `**System Error**` (as defined in Sprint 0's soft degradation), apply distinct error styling to the bubble (e.g., a subtle red border or a distinct background tint) to differentiate it from a normal AI response.
3. **Markdown Handling**: Install `@tailwindcss/typography`. Use a library like `react-markdown` within the AI bubble, wrapped in a `<div className="prose prose-invert max-w-none">` to cleanly render the LLM's bolding, lists, and links without clashing with the dark Tailwind theme.
4. **The Feed**: Create `frontend/src/components/AdvisoryFeed.tsx` that consumes `useChatStore().messages` and maps them out vertically. Implement a `useRef` pointing to a dummy `div` at the bottom of the list, triggering `.scrollIntoView({ behavior: "smooth" })` in a `useEffect` on message change to ensure reliable auto-pinning.

#### Acceptance Criteria
- The Next.js dashboard visually mirrors the Stitch prototype perfectly.
- Submitting a message correctly leverages the core Zustand store to update the styled chat feed.

---

### Ticket 1.4: Component Testing ✅ DONE

#### Overview
Ensure the new premium UI components render correctly and properly trigger the mocked Zustand store actions when interacted with.

#### Implementation Steps
1. **Chat Message Tests**:
   - Create `src/components/ChatMessage.test.tsx`.
   - Write tests verifying that User vs. AI messages render with the correct distinct CSS classes (e.g., `#564be7` for AI).
   - Verify that markdown links and bolding render correctly.
2. **Command Center Tests**:
   - Create `src/components/CommandCenter.test.tsx`.
   - Mock the `useChatStore` to provide a dummy `sendMessage` and `uploadCV` function, as well as an `isPending` boolean toggle.
   - Fire a `userEvent.click` on the send button and verify the mocked `sendMessage` was called.
   - Set `isPending` to true and verify the inputs become disabled.

#### Acceptance Criteria
- Vitest/RTL successfully runs the new tests.
- High component coverage ensures that styling changes or Zustand refactors don't unexpectedly break the core chat loop UI.

---

## Manual Verification (End of Sprint 1)

To definitively prove Sprint 1 is complete before moving to Sprint 2 (Discovery Deck), perform the following manual visual tests:

1. **Two-Pane Layout Verification**:
   - Open `http://localhost:3000`.
   - Resize the browser window. Verify the `AdvisoryFeed` (Left Pane) takes up roughly 60% of the screen and the placeholder for the `DiscoveryDeck` (Right Pane) takes up 40%, matching the Stitch HTML structure.
   - Verify the global dark-mode background colors are applied and reach the edges of the screen.

2. **Command Center Visuals & Interaction**:
   - Inspect the `CommandCenter` component at the bottom of the screen.
   - Verify the SVG icons (paperclip, send arrow) are present.
   - Type a message and hit enter. Verify the input instantly disables and a loading indicator replaces the send icon while waiting for the response.
   - Upload a PDF via the paperclip icon and verify the exact same loading state triggers.

3. **Chat Feed Premium Styling**:
   - Review both a "User" bubble and an "AI" bubble in the `AdvisoryFeed`.
   - Verify the AI bubble utilizes the premium Stitch styling.
   - Trigger the AI to generate a Markdown list or bold text. Verify the `@tailwindcss/typography` plugin correctly renders the markdown cleanly inside the dark-themed bubble.
   - Force an error response from the backend. Verify the resulting `**System Error**` message bubble is visually distinct from a normal successful AI bubble.

4. **Scroll Behavior**:
   - Flood the chat with messages to exceed the viewport height.
   - Verify the `AdvisoryFeed` handles independent vertical scrolling without scrolling the entire browser page or the Command Center off-screen.
   - Verify new messages auto-scroll the feed to the bottom.
