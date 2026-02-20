# Sprint 0: Functional React Native MVP (Chat Only)

**Goal**: Replicate the current functionality of the app (the chat window) in a bare-bones React Native Web app. We will prove the API connectivity works before applying any complex styling.

---

## Detailed Ticket Breakdown

### Ticket 0.1: Expo Initialization & Repository Setup

#### Overview
We need to generate a new Expo app in the `frontend/` directory to serve as our React Native workspace.

#### Implementation Steps
1. **Initialize the App**:
   - Run the definitive setup command: `npx create-expo-app@latest frontend --template blank-typescript`
2. **Setup Dependencies**:
   - Install Web dependencies: `npx expo install react-dom react-native-web @expo/metro-runtime`
   - Install NativeWind early so it's ready for Sprint 1: `npm install nativewind` and `npm install --save-dev tailwindcss@3.3.2`. Initialize `tailwind.config.js`.

#### Acceptance Criteria
- A `frontend/` directory exists with a functioning Expo/TypeScript setup.
- Web rendering compiles (`npm run web`) to a blank white screen.

---

### Ticket 0.2: Backend API & JSON Refactoring

#### Overview
Currently, the FastAPI `/chat` endpoint relies on HTMX `Form` data and returns a rendered Jinja HTML template (`components/chat_message.html`). We need to modernize this to a standard REST API pattern (JSON in, JSON out) for React Native.

#### Implementation Steps
1. **Configure CORS (`app/main.py`)**:
   - Add `CORSMiddleware` to the FastAPI app to allow requests from the Expo Web development server (usually `http://localhost:8081`).
2. **Update Request Parsing (`app/api/routes.py`)**:
   - Create a Pydantic model: `class ChatRequest(BaseModel): message: str`.
   - Modify `chat_endpoint` to accept `request: ChatRequest` instead of `message: str = Form(...)`.
3. **Update Response Format**:
   - Instead of `templates.TemplateResponse(...)`, have the route directly return the result from `ChatService.process_message(...)`.
   - `FastAPI` will automatically serialize the returned dictionary: `{"user_message": "...", "ai_message": "...", "jobs": [...]}` into a JSON response.

#### Acceptance Criteria
- Sending a POST request to `/chat` with `{"message": "Hello"}` using `curl` returns a JSON payload containing `ai_message` and `jobs`.
- The backend no longer depends on Jinja templates for the `/chat` route.

---

### Ticket 0.3: The Functional Chat Interface

#### Overview
Build a bare-bones React Native screen that can send text to the backend and append the responses to a list, mimicking the current web functionality. No premium styling needed yet.

#### Implementation Steps
1. **Build the State Structure**:
   - In `frontend/app/index.tsx`, initialize `const [messages, setMessages] = useState<{role: string, text: string}[]>([])` and `const [inputText, setInputText] = useState("")`.
2. **Create the Input Bar**:
   - Render a simple `<TextInput>` and a "Send" `<Button>`.
   - The "Send" function should instantly append the user's text to `messages`, and then execute a `fetch('http://localhost:8000/chat', { method: 'POST' ... })`.
3. **Handle the Response**:
   - Parse the returning JSON from Ticket 0.2.
   - Append `{"role": "ai", "text": response.ai_message}` to the `messages` array.
4. **Render the Feed**:
   - Use a basic `<FlatList data={messages} ... />` to render out `<Text>` elements for each message.

#### Acceptance Criteria
- The web app loads. A user can type a query like "Hi", click Send, and the LangGraph backend naturally responds, with the response text appearing in the list. The UI proves the pipeline works.
