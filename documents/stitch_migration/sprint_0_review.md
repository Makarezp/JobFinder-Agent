# Critical Review: Sprint 0 (Functional Setup)

## Overall Verdict
The sprint plan is structurally sound and focuses on the right MVP elements (functional vertical slice before styling). However, there are a few architectural weak points and missing implementation details that will cause friction during execution if not addressed.

## 🔴 High-Priority Concerns & Weak Points

### 1. Old Code and Template Cleanup (Ticket 0.2)
**The Update:** The plan correctly mutates the existing endpoints (`/chat`, `/upload-cv`, `/`) rather than maintaining two API versions. Since breaking the legacy HTMX is acceptable, the highest priority is ensuring we don't leave phantom state.
**Recommendation:**
- The updated Sprint 0 document now explicitly demands removing `app/templates` and Jinja components. The executing agent MUST ensure that `test_profile_routes.py` and other route tests are also heavily refactored or deleted so they don't break the build when the HTML responses vanish.
- Ensure that `app/main.py` explicitly drops the `templates` and `StaticFiles` mounts.
- *Also note: `ChatRequest` should still ideally be placed in schemas to adhere to `CONVENTIONS.md`*.

### 2. Next.js to FastAPI Network Connectivity (Ticket 0.3)
**The Update:** The plan now correctly mandates using **Next.js rewrites** (`next.config.ts`) to proxy `/api/*` requests to the FastAPI backend running on port 8000.
**Why this is crucial:**
- Development is split between Next.js on `localhost:3000` and FastAPI on `localhost:8000`. Direct fetches cross-origin lead to sticky CORS blocks and preflight `OPTIONS` requests slowing down the network. Proxying means the browser only talks to port 3000, completely side-stepping CORS.
- Setting explicit API prefixes like `/api/chat` lays proper groundwork for this rewrite strategy.

### 4. JSON Error Handling Contract (Ticket 0.2)
**The Update:** Ticket 0.2 now correctly mandates a **Soft Degradation** error strategy.
**Why this is crucial:** Currently, the FastAPI `routes.py` `Except` blocks return hardcoded HTML strings (e.g. `<p class='text-red'>`). Returning these to a Next.js JSON API would break the `react-markdown` parser. By softly failing and returning a 200 OK JSON with `ai_message: "**System Error**: message"`, we prevent the Next.js `Zustand` store from needing complex `try/catch` logic while effectively sanitizing the legacy HTMX bindings.

## Summary Checklist for the Developer Executing This:
- [ ] Create `/api/*` routes instead of overwriting root HTTP endpoints.
- [ ] Put `ChatRequest` in a separate `schemas.py` file.
- [ ] Use `next.config.ts` API rewrites mapping `/api/*` to `8000/api/*` to fix the `localhost:3000 -> 8000` port mapping.
- [ ] Ensure HTML error tags (`<p>`) are completely eradicated from FastAPI exception returns and replaced with Markdown strings over JSON.
- [ ] Omit `Content-Type` headers when submitting `FormData` from the Zustand store.
- [ ] Purge the `app/templates` directory totally and cleanse related backend code/tests of Jinja references.
