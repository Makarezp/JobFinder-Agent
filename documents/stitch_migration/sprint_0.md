# Sprint 0: Functional Setup (Next.js MVP)

**Goal**: Establish the `frontend/` directory with a barebones Next.js app. Prove the REST API connectivity works utilizing Zustand before adding styling.

---

## Detailed Ticket Breakdown

### Ticket 0.1: Next.js Initialization ✅ DONE

#### Overview
Set up the standard Next.js directory at exactly `frontend/` (the root of all frontend code).

#### Implementation Steps
1. **Initialize Project**:
   - Run `npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir`.
2. **Directory Structure Prep**:
   - Inside `frontend/src/`, create a `core/` folder to serve as the strict boundary for business logic (subfolders: `api/`, `store/`, `types/`).

#### Acceptance Criteria
- ✅ Running `npm run dev` inside `frontend/` loads the Next.js starter page (blank page after cleanup).
- ✅ The directory `frontend/src/core/{api,store,types}` exists.
- ✅ Committed: `e443d69 feat: add next frontend`

---

### Ticket 0.2: Backend API & JSON Refactoring ✅ DONE

#### Overview
The FastAPI `/chat` endpoint previously relied on HTMX Form data. We need to modernize this to a standard JSON REST API.

#### Implementation Steps
1. **Configure CORS (`app/main.py`)**:
   - Add `CORSMiddleware` to allow requests from the Next.js dev server (usually `http://localhost:3000`).
2. **Update Request Parsing & Prefix (`app/api/routes.py`)**:
   - Move all endpoints under the `/api` prefix (e.g., `@router.post("/api/chat")`, `@router.post("/api/upload-cv")`, `@router.get("/api/history")`).
   - Create a Pydantic model: `class ChatRequest(BaseModel): message: str`.
   - Modify `chat_endpoint` to accept JSON instead of `Form(...)`.
3. **Update Response Format**:
   - Return directly JSON: `{"user_message": "...", "ai_message": "...", "jobs": [...]}` instead of Jinja HTML for the `POST /api/chat` endpoint.
   - **Error Handling (Soft Degradation)**: When `try/except` catches an error in `/api/chat` or `/api/upload-cv`, do NOT return HTML strings like `<p class='text-red-500'>Error</p>`. Instead, return a standard 200 OK JSON response where the `ai_message` contains a Markdown-formatted error string (e.g., `f"**System Error**: {str(e)}"`). This ensures the frontend Zustand store always receives a consistent `{user_message, ai_message, jobs}` contract, even during failures.
4. **CV Upload Endpoint (`POST /api/upload-cv`)**:
   - Refactor `upload_cv` to return identical JSON instead of Jinja HTML. It continues to accept `multipart/form-data` for the file.
5. **History Endpoint**:
   - Refactor the existing history endpoint (serving `index.html`) to instead be `GET /api/history` returning the array from `await chat_service.get_history()` as pure JSON. We don't need a brand new root endpoint since Next.js will be handling the HTML delivery from now on.
6. **Code Cleanup (Crucial)**:
   - Delete the entire `app/templates` directory (HTMX views are no longer needed).
   - Remove Jinja2 dependencies and static file mounts from `app/main.py`.
   - Update tests in `tests/` that expect HTML responses to now expect JSON. Remove any tests strictly bound to Jinja rendering.

#### Acceptance Criteria
- ✅ `POST /api/chat` with JSON returns `{user_message, ai_message, jobs}`.
- ✅ `POST /api/upload-cv` with multipart file returns JSON.
- ✅ `GET /api/history` returns a JSON array.
- ✅ `GET /api/profile` returns JSON (profile + preferences).
- ✅ Backend errors return `200 OK` with `**System Error**: ...` in `ai_message`.
- ✅ `app/templates/` deleted entirely.
- ✅ All tests updated to assert JSON structure. `jinja2`/`markdown` removed from deps.
- ✅ `app/api/schemas.py` created for `ChatRequest` model.
- ✅ Committed: `07bb212 feat: modify api for return json`

---

### Ticket 0.3: The Zustand Chat Logic & Next.js UI

#### Overview
Build the pure Zustand store inside `frontend/src/core/` and integrate it into a bare-bones Next.js screen.

#### Implementation Steps
1. **Proxy Configuration (CRITICAL)**:
   - In `frontend/next.config.ts`, add a rewrite rule mapping `/api/:path*` to `http://localhost:8000/api/:path*`. This prevents all CORS and port-mapping issues by making the backend accessible directly through the Next.js dev server port (3000).
2. **Core Store (`frontend/src/core/store/`)**:
   - Install `zustand`.
   - Create `useChatStore.ts`. Define state for `messages`.
   - Add a `sendMessage(text: string)` action that executes a standard relative JSON `fetch('/api/chat')` and appends the JSON response.
   - Add an `uploadCV(file: File)` action that builds a `FormData` object, executes a `fetch('/api/upload-cv')`, and appends the JSON response. **CRITICAL:** Do NOT manually set the `Content-Type: multipart/form-data` header when sending `FormData` via JS `fetch`; let the browser set it automatically to handle boundaries.
   - Add a `fetchHistory()` action that fetches from the refactored `GET /api/history` to initialize the store.
3. **Next.js Integration (`frontend/src/app/`)**:
   - In `app/page.tsx`, import `useChatStore` and leverage `useEffect` to call the `fetchHistory()` action on component mount.
   - Render a simple bare-bones HTML `<input type="text">`, an `<input type="file">`, and a mapped list of messages from the store.
4. **Trigger Logic**:
   - When the send button or file upload is triggered, it calls the respective Zustand action (`sendMessage` or `uploadCV`). It does not handle fetch logic itself.

#### Acceptance Criteria
- The Next.js app loads and instantly fetches/renders existing chat history. A user types "Hi" or uploads a file, the core Zustand store makes the fetch call, and the UI updates reactively with the AI's JSON response.

---

### Ticket 0.4: Frontend Testing Infrastructure

#### Overview
Set up the unit and component testing environment for the Next.js frontend to ensure high coverage and reliable refactoring from the start.

#### Implementation Steps
1. **Install Dependencies**:
   - Install `vitest`, `@testing-library/react`, `@testing-library/dom`, `@testing-library/jest-dom`, and `@vitejs/plugin-react` inside `frontend/`.
2. **Configuration**:
   - Create a `vitest.config.ts` configured for the React/Next.js environment.
   - Set up standard testing scripts in `frontend/package.json` (e.g., `"test": "vitest run"`).
3. **Integration with Project Checks**:
   - Verify that running tests inside the frontend cleanly runs alongside the existing python backend tests (or consider how to wrap it in the global `./scripts/test.sh` eventually).

#### Acceptance Criteria
- Running `npm run test` inside the `frontend/` directory executes Vitest successfully.
- A dummy test file (e.g., `src/core/store/useChatStore.test.ts`) passes successfully.

---

### Ticket 0.5: Code Quality Tools (Linting, Formatting, Hooks)

#### Overview
Establish strict code quality gates for the frontend to match the Python backend's `ruff` and `mypy` standards.

#### Implementation Steps
1. **Formatting**:
   - Install `prettier` and `eslint-config-prettier`.
   - Create a `.prettierrc` file with project-standard rules.
2. **Linting**:
   - Configure the Next.js `.eslintrc.json` to be strict (e.g., enforcing plugin-react-hooks, blocking unused imports).
3. **Pre-commit Hooks**:
   - Install `husky` and `lint-staged`.
   - Configure a pre-commit hook to automatically run ESLint, Prettier, and TypeScript type-checking (`tsc --noEmit`) on staged frontend files.

#### Acceptance Criteria
- Running `npm run lint` and `npm run format` works.
- Committing a poorly formatted or type-invalid TypeScript file is blocked by Husky.

---

## Manual Verification (End of Sprint 0)

To definitively prove Sprint 0 is complete before moving to styling in Sprint 1, perform the following manual tests:

1. **Boot Verification**:
   - Start the FastAPI backend (`uvicorn app.main:app`).
   - Start the Next.js frontend (`npm run dev` in `frontend/`).
   - Open `http://localhost:3000`. Verify the page loads cleanly with no console errors and displays a basic unstyled input bar.

2. **History Hydration Test**:
   - Refresh the Next.js app (`http://localhost:3000`). Verify that the exact same chat history appears in the unstyled list immediately on page load, proving the `GET /api/history` JSON refactor and the `fetchHistory()` Zustand action work.
     Note: Since we use rewrites, the browser connects to `3000/api/history`, which proxy-routes to `8000/api/history`.

3. **Live Chat Flow Test**:
   - Type a prompt (e.g., "Hello Agent") into the Next.js unstyled input and click send.
   - Verify the user's message appears instantly (optimistic UI).
   - Verify that 2-5 seconds later, the AI's response appears below it, proving the pure JSON API connection `/api/chat` and Zustand `sendMessage` action are fully wired through the proxy.

4. **CV Upload Flow Test**:
   - Use the unstyled file input to upload a dummy PDF.
   - Verify the file is sent, the backend processes it, and the AI's confirmation message appears dynamically in the feed via the `uploadCV` action.

5. **Code Quality Gate Test**:
   - Open any TS file in `frontend/src/` and introduce a syntax error or unused variable.
   - Attempt to run `git commit`. Verify that Husky specifically intercepts and blocks the commit with an ESLint or TypeScript error.
