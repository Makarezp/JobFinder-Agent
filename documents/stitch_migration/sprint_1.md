# Sprint 1: Premium Shell (Stitch Styling)
**Goal**: Take the functional, bare-bones React Native app from Sprint 0 and apply the premium Stitch design system using NativeWind.

*   **Ticket 1.1**: *Base Layout Infrastructure.*
    *   Translate the global "shell" styling into `app/_layout.tsx` or a wrapper component.
    *   Setup the SafeArea and main background gradients using NativeWind classes.
*   **Ticket 1.2**: *Premium Command Center.*
    *   Refactor the basic `<TextInput>` into a new `components/CommandCenter.tsx`.
    *   Implement the dark mode styling and SVG icons for attaching files/sending messages.
*   **Ticket 1.3**: *Premium Advisory Feed.*
    *   Refactor the basic text messages into a styled `components/ChatMessage.tsx` mapping the Stitch bubbles (AI vs User) to `<View>` structures.
    *   Integrate this into the `FlatList` to render the conversation history with premium aesthetics.

*   **Definition of Done (DoD)**: Navigating to the app displays the chat interface with the exact colors, fonts, and gradients of the Stitch design. Sending a message relies on the working Sprint 0 logic, but the resulting AI response bubble is perfectly styled.

---

## Detailed Ticket Breakdown

### Ticket 1.1: Base Layout Infrastructure

#### Overview
We need to extract the global "shell" from the Stitch HTML and apply it to our React Native `app/index.tsx` screen. This ensures the premium aesthetic (gradients, fonts, background colors) envelopes the application.

#### Implementation Steps
1. **Analyze Stitch Shell**: Identify the main container classes in the Stitch output (e.g., `bg-gray-900`, Flex directions).
2. **Translate to React Native**:
   - Open `frontend/app/index.tsx`.
   - Wrap the screen in a `SafeAreaView`.
   - Use NativeWind (e.g., `<View className="flex-1 bg-gray-900 flex-row">`) to set up the container that will eventually hold the left chat pane and right deck pane.

### Ticket 1.2: Command Center Component

#### Overview
The "Command Center" is the persistent input area. We must translate the Stitch dark-mode `<form>` into a React Native component.

#### Implementation Steps
1. **Create Component**: Create `frontend/components/CommandCenter.tsx`.
2. **Translate Input**: Replace the Stitch `<input>` with React Native's `<TextInput>`. Apply NativeWind classes to match the rounded corners, padding, and text color.
3. **SVG Icons**: Utilize `react-native-svg` to bring the Stitch SVG icons (paperclip, send arrow) into the component. Wrap them in `<TouchableOpacity>` or `<Pressable>` for hit areas.
4. **Local State Wiring**: Add `const [text, setText] = useState("")` to manage the input, bypassing the backend temporarily.

### Ticket 1.3: Advisory Feed Component

#### Overview
Translate the premium chat bubbles from Stitch into React Native `<View>` and `<Text>` elements.

#### Implementation Steps
1. **Create Bubble Component**: Create `frontend/components/ChatMessage.tsx`.
2. **Role Styling**: Accept a prop like `role: 'user' | 'ai'`. Use this to conditionally apply NativeWind classes (e.g., `user` gets `bg-indigo-600 rounded-l-2xl`, AI gets `bg-white/10`).
3. **Markdown Handling**: For the AI bubble, we will eventually need a library like `react-native-markdown-display` to handle generated bolding/lists, but for Sprint 1, standard `<Text>` is sufficient for mockup strings.
4. **The Feed**: Create `frontend/components/AdvisoryFeed.tsx` utilizing a `<FlatList>` that maps over a fixed array of mockup messages to verify scrolling and spacing.

#### Acceptance Criteria
- The input area in `index.html` accurately matches the premium styling of the Stitch prototype.
- Typing a message and pressing Enter (or clicking the new Send icon) successfully triggers the `/chat` route via HTMX.
- Clicking the new Attachment icon successfully opens the OS file picker, and selecting a PDF triggers the `/upload-cv` route.
- The input field clears automatically after sending.

---

### Ticket 1.3: Advisory Feed Component

#### Overview
The "Advisory Feed" is the chat history window where the user and the agent communicate. Currently, `components/chat_message.html` uses a basic light-gray/indigo box style. The new Stitch design uses a premium styling for these bubbles (e.g., glassmorphism, different fonts, specific spacing). We need to extract the Stitch bubble styling and apply it to our existing Jinja partial.

#### The Stitch Source Material
In the Stitch HTML artifact (`files/b811d949ff1042d599551b3ca6a411fe`), we need to identify the exact HTML blocks representing:
1.  **User Message Bubble**: Typically aligned to the right or styled distinctly. Look for classes like `bg-indigo-600`, `text-white`, `rounded-l-2xl`.
2.  **AI Navigator Bubble**: Typically aligned to the left, often using the custom theme color (`#564be7`), glassmorphism effects (`bg-white/10`, `backdrop-blur`), or specific gradients.

#### Implementation Steps
1. **Analyze `components/chat_message.html`**:
   - Our current file uses a Jinja `{% if user_message %}` and `{% if ai_message %}` block to render the respective bubbles.
   - It also handles rendering raw string messages vs. complex Markdown output (`{{ ai_message | markdown | safe }}`).

2. **Apply User Bubble Styling**:
   - Replace the wrapper `<div>` of the `user_message` block (currently `bg-indigo-600 text-white`) with the exact CSS classes from the Stitch user bubble design.
   - Ensure text padding and flex alignment are maintained so text doesn't overflow.

3. **Apply AI Navigator Bubble Styling**:
   - Replace the wrapper `<div>` of the `ai_message` block (currently `bg-indigo-50 text-indigo-900`) with the exact CSS classes from the Stitch AI bubble design.
   - Ensure the `markdown | safe` filter still applies correctly inside this new wrapper, meaning headers, lists, and links generated by the LLM don't clash with the new Tailwind typography classes. (We may need to add `@tailwindcss/typography` classes like `prose prose-invert` if the bubble has dark styling).

4. **Verify HTMX Insertion**:
   - The `/chat` endpoint returns this exact `chat_message.html` partial, which HTMX appends to the bottom of the feed (`hx-swap="beforeend"`).
   - Ensure there are no unclosed div tags or structural breakages that would cause the feed to render improperly upon new message arrival.

#### Acceptance Criteria
- Loading existing chat history renders correctly using the new Stitch bubble aesthetics.
- Submitting a new message appends a perfectly styled User bubble and AI bubble without requiring a page refresh.
- Markdown generated by the AI (bolding, lists, links) renders legibly inside the new AI bubble design.
