# Tech Debt Audit: Full Backend Sweep

**Auditor**: Clean Code Auditor (Senior Python Architect)
**Date**: 2026-03-05
**Scope**: All backend source (`app/`) and tests (`tests/`)

---

## File 1: `app/agent/state.py`

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[state.py:17] - `active_agent` is phantom state**: This field is defined in `AgentState` but never read by any production code. Routing is driven by `onboarding_complete` via the `router()` function in `graph.py`. Tests set it as filler but no node or router inspects it. Violates Design Principle #7 (No Phantom State). **Action**: Delete the `active_agent` field. Remove from all test fixtures.
- [ ] **[state.py:13-14] - Weak typing on `user_profile` and `preferences`**: Both are `dict[str, Any] | None`. The project has Pydantic models (`UserProfile`, `Preference`) for these. Using `dict[str, Any]` defeats contract stability (Design Principle #2). **Action**: Consider using `UserProfile | None` and `dict[str, Preference] | None` or at minimum add a comment explaining why raw dicts are needed here (LangGraph serialisation constraint).
- [ ] **[state.py:19] - `recent_decisions` typed as `list[dict[str, Any]]`**: Same issue — `DecisionLog` exists but is not used as the type. **Action**: Same approach as above.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[state.py:8-9] - Docstring is redundant**: `"""State for the agent graph."""` adds zero information beyond what the class name already communicates. **Action**: Either delete or replace with a meaningful docstring explaining the field lifecycle.

---

## File 2: `app/agent/schemas.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found. This file is clean._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### 🔍 Nitpicks
- [ ] **[schemas.py:31] - Misleading `id` field description**: Description says `"Computed in _parse_agent_result, not by the LLM"` — this leaks internal implementation detail into a Pydantic schema that could be exposed externally. The field description should describe the data, not the pipeline. **Action**: Shorten to `"Unique identifier for frontend tracking."`.
- [ ] **[schemas.py:45] - `jobs` default is mutable `[]`**: `Field(default=[], ...)` — Pydantic handles this safely, but the semantic intent is `None` (no jobs) vs `[]` (searched but found nothing). Having `default=[]` with type `list | None` is ambiguous. **Action**: Change default to `None` to be explicit, or remove `| None` and always use `[]` for empty. Pick one semantic.

### ✅ Verdict: **Mostly clean.** Well-structured Pydantic models with clear field descriptions.

---

## File 3: `app/agent/graph.py`

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[graph.py:45-100] - `_run_single_job_search` + `call_job_specialist` violate SRP**: `call_job_specialist` is a single node that does four distinct things: (1) invokes the subgraph, (2) fetches seen job IDs, (3) splits fresh vs seen, (4) serializes the payload to JSON. The seen-job deduplication logic (lines 64-71) is a business rule buried inside orchestration glue. **Action**: Extract the fresh/seen split and serialization into a dedicated method on `ProfileService` (e.g., `split_and_mark_results(results, user_id) -> dict`). The node should only call the subgraph and delegate post-processing.
- [ ] **[graph.py:4] - Uses `logging` instead of `structlog`**: `import logging` + `logger = logging.getLogger(__name__)` violates the project convention (`CONVENTIONS.md §4`). Every other agent file uses `structlog`. **Action**: Replace with `import structlog; logger = structlog.get_logger(__name__)`.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[graph.py:44] - Comment as section header**: `# --- Helper: single job search execution ---` is used as a section separator. This is a code smell — if a file needs section headers, it has too many responsibilities. Currently acceptable given file size, but flag for future extraction if this file grows.
- [ ] **[graph.py:112] - `get_compiled_graph` return type is `Any`**: The function returns a compiled LangGraph object but types it as `Any`. **Action**: Use `CompiledStateGraph[AgentState]` or the appropriate LangGraph type.

### 🔍 Nitpicks
- [ ] **[graph.py:94-96] - Comment block could be a named constant**: The 3-line comment explaining "increment by 1 per batch" documents the relationship between `search_attempts` and the loop protection threshold. This coupling should be documented by a shared constant (e.g., `MAX_SEARCH_ATTEMPTS = 3` in `constants.py`) rather than a comment.

### ✅ Verdict: **Has one legitimate SRP issue** in the job search post-processing. Otherwise well-structured orchestration code.

---

## File 4: `app/agent/constants.py`

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[constants.py:25] - `ROUTER_NODE` is dead code**: `ROUTER_NODE: Final[str] = "router"` is defined but never imported or used anywhere in the codebase. The `router` function in `graph.py` is a conditional edge callback, not a registered node. Violates Design Principle #7 (No Dead Code). **Action**: Delete.
- [ ] **[constants.py] - Missing `MAX_SEARCH_ATTEMPTS` constant**: The magic number `3` appears in `route_main` (main/nodes.py:271) and in the system prompt (`SYSTEM_PROMPT` mentions "3 total search attempts"). This coupling between router logic and prompt text is held together by nothing but hope. **Action**: Add `MAX_SEARCH_ATTEMPTS: Final[int] = 3` here and reference it in both `route_main` and the prompt template.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[constants.py:14-18] - State key constants are inconsistently used**: `MESSAGES_KEY`, `CV_RAW_TEXT_KEY`, `ONBOARDING_COMPLETE_KEY`, `ACTIVE_AGENT_KEY` are defined, but production code frequently accesses state via string literals instead (e.g., `state.get("search_attempts")`, `state.get("user_profile")`). Either use the constants everywhere or delete them. **Action**: Audit all state access and pick one approach.

### ✅ Verdict: **Has dead code and a dangerous magic number.**

---

## File 5: `app/agent/memory_schema.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found. This file is clean._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### 🔍 Nitpicks
- [ ] **[memory_schema.py:11] - Hardcoded `id: int = 1`**: `UserProfile.id` defaults to `1`. In a single-user MVP this works, but it's a latent bug for multi-tenancy. The `user_id` is already managed as a string in the store namespaces (`"default_user"`). This integer id is unused by any store logic. **Action**: Consider removing or aligning with the string-based `user_id`.

### ✅ Verdict: **Excellent.** Clean Pydantic models with proper field descriptions and Literal constraints.

---

## File 6: `app/agent/main/nodes.py`

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[nodes.py:29-35] - Module-level LLM instantiation violates Dependency Injection**: `llm = ChatGoogleGenerativeAI(...)` and `main_llm = llm.bind_tools(main_tools)` are created at **import time** as module globals. This means: (a) tests must `patch("app.agent.main.nodes.main_llm")` — a deep internal path, directly contradicting the project's own DI guidance in `AGENTS.md §Gotchas`; (b) changing the model or temperature requires restarting the process; (c) circular import risk if config is slow. Violates Design Principle #5 (Dependency Injection). **Action**: Move LLM construction into `get_compiled_graph()` and inject via `functools.partial` or closure, same pattern used for `store`.
- [ ] **[nodes.py:186-253] - `main_chatbot` is ~67 lines and does 5 things**: (1) formats the system prompt, (2) builds the feedback block, (3) strips onboarding messages, (4) trims messages, (5) invokes the LLM with fallback. This violates SRP and makes the function hard to test in isolation. **Action**: Extract prompt construction into a `_build_system_prompt(profile, preferences, decisions) -> str` helper. The node body should be: build prompt → prepare messages → invoke → return.
- [ ] **[nodes.py:39-52] - `_is_fresh_onboarding_handoff` has fragile coupling**: The function detects handoff by checking if the last message contains `"Onboarding complete"` as a substring. The docstring itself warns (lines 46-48): _"If a node is ever inserted there, this detection will break silently."_ This is a ticking time bomb. **Action**: Use a structured signal (e.g., a dedicated state field `handoff_pending: bool` or a sentinel `ToolMessage` subclass) instead of string matching.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[nodes.py:69] - Stale comment**: `# cv is now just a string` — the word "now" implies a past refactoring. This is a changelog comment, not a code comment. **Action**: Delete.
- [ ] **[nodes.py:170] - Inline `type: ignore` with string key access**: `current_messages: list[BaseMessage] = state.get(MESSAGES_KEY, [])  # type: ignore` — the ignore is needed because `TypedDict.get()` returns a union. This is acceptable but suggests the state access pattern could use a thin accessor helper. **Action**: Acknowledge or add a typed accessor.
- [ ] **[nodes.py:199-204] - Ternary-formatted multiline block**: The `feedback_block` ternary spans 6 lines and is hard to scan. **Action**: Extract into a one-line helper: `feedback_block = _build_feedback_block(decisions_summary)`.

### 🔍 Nitpicks
- [ ] **[nodes.py:241] - `main_llm.invoke` is synchronous inside a `def` node**: `main_chatbot` is `def` (sync), not `async def`. LangGraph runs it in a thread executor, so it's not blocking the event loop. But it's inconsistent with `fetch_profile` which is `async def`. **Action**: Consider making `main_chatbot` async for consistency, using `await main_llm.ainvoke()`.

### ✅ Verdict: **Highest debt density in the project.** Module-level globals, oversized node function, and fragile string-based handoff detection.

---

## File 7: `app/agent/main/prompts.py`

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[prompts.py:98-99] - Hardcoded "3 searches" in prompt text**: `"You have a strict budget of 3 searches per conversation turn"` — this number must match `route_main`'s `>= 3` threshold. If either changes independently, the agent and the router will disagree. **Action**: Use a template variable `{max_search_attempts}` and inject from the shared constant proposed for `constants.py`.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[prompts.py:103] - Prompt is not terminated with `\n`**: The `SYSTEM_PROMPT` string ends on line 103 with `\"\"\"` but the last content line (102) has no trailing newline. Minor, but some LLMs are sensitive to trailing whitespace. **Action**: Ensure consistent trailing newline.

### 🔍 Nitpicks
- [ ] **[prompts.py:1] - Docstring is generic**: `"""Agent related prompts."""` — could be more descriptive: `"""System prompt for the main job-hunting agent."""`. **Action**: Improve.

### ✅ Verdict: **Well-written prompt.** Only real issue is the hardcoded `3` that must stay in sync with router logic.

---

## File 8: `app/agent/main/tools.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found. This file is clean._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### 🔍 Nitpicks
- [ ] **[tools.py:25] - `job_specialist_tool` returns a throwaway string**: `return "Job Specialist invoked."` — this stub return is never read because `call_job_specialist` in `graph.py` intercepts the tool call before it executes. The function body exists only to satisfy LangChain's `@tool` decorator. **Action**: Add a one-line comment explaining why this return value is unused (it's a routing sentinel, not a real tool).
- [ ] **[tools.py:34] - Same for `final_answer`**: `return "Final Answer Processed"` — same situation. The return is never consumed; `_parse_agent_result` reads the tool call args, not the result. **Action**: Same — add a comment.

### ✅ Verdict: **Clean.** Thin registration file doing its job. Stub returns are intentional.

---

## File 9: `app/agent/job_search/` (nodes.py, state.py, graph.py)

### `job_search/state.py` — ✅ **Perfect.** 13 lines, clean TypedDict. No findings.

### `job_search/graph.py`

#### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[graph.py:1] - Uses `logging` instead of `structlog`**: Same convention violation as the main `graph.py`. **Action**: Replace with `structlog.get_logger(__name__)`.

#### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[graph.py:12-18] - Module-level graph compilation**: `workflow.compile()` runs at **import time**. This is fine for a simple START→search→END subgraph, but it means the graph is frozen before any runtime configuration. If the subgraph ever needs injected dependencies (e.g., store), this pattern will break. **Action**: Flag for future — acceptable for now.

### `job_search/nodes.py`

#### 🚨 Critical Tech Debt (Must Fix)
_None found._

#### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[nodes.py:35-49] - Manual dict-to-Pydantic mapping is fragile**: The `for r in raw_results` loop manually maps `.get("id")`, `.get("title")`, etc. from the jsearch tool's output dicts into `JobListing` kwargs. If a field is added to `JobListing`, this mapping must be updated in lockstep. **Action**: Since `jsearch_api.py` already returns dicts with the exact `JobListing` field names, consider `JobListing(**r)` with a `try/except ValidationError` — let Pydantic do the mapping and validation, not handwritten `.get()` calls.
- [ ] **[nodes.py:48-49] - Bare `except Exception`**: Catches all exceptions during parse, including unexpected ones like `TypeError`. **Action**: Catch `pydantic.ValidationError` specifically if switching to `JobListing(**r)`, or at least log the exception type.

### 🔍 Nitpicks
_None._

### ✅ Verdict: **Clean subgraph.** Simple and well-scoped. The manual mapping in `nodes.py` is the only real debt.

---

## File 10: `app/agent/onboarding/` (nodes.py, prompts.py, tools.py)

### `onboarding/prompts.py` — ✅ **Clean.** Well-structured prompt, clear instructions. No findings.

### `onboarding/tools.py` — ✅ **Perfect.** 14 lines, pure re-export. No findings.

### `onboarding/nodes.py`

#### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[nodes.py:27-33] - Duplicate module-level LLM instantiation**: Same anti-pattern as `main/nodes.py`. `llm = ChatGoogleGenerativeAI(...)` and `onboarding_llm = llm.bind_tools(onboarding_tools)` created at import time. Tests must `patch("app.agent.onboarding.nodes.onboarding_llm")` — deep internal path. **Action**: Same fix — inject via `functools.partial` from `get_compiled_graph()`.
- [ ] **[nodes.py:93] - `hasattr(ai_message, "tool_calls")` is defensive band-aid**: `AIMessage` always has `tool_calls` (it's a defined attribute, defaulting to `[]`). Using `hasattr` is overly defensive and masks the real intent. Compare with `route_main` in `main/nodes.py:262` which correctly uses `isinstance(ai_message, AIMessage) and ai_message.tool_calls`. **Action**: Replace with `isinstance(ai_message, AIMessage) and ai_message.tool_calls` for consistency.

#### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[nodes.py:107-113] - `route_after_onboarding_tools` uses fragile string detection**: Checks `"Onboarding complete" in str(msg.content)` — same fragile substring pattern as `_is_fresh_onboarding_handoff` in `main/nodes.py`. Two separate places rely on the same magic string. **Action**: Extract the magic string `"Onboarding complete"` into a shared constant in `constants.py` (e.g., `ONBOARDING_COMPLETE_SIGNAL`). Better yet, use the structured signal approach proposed for `main/nodes.py`.
- [ ] **[nodes.py:56-84] - `onboarding_chatbot` is copy-paste of `main_chatbot` error handling**: The try/except/fallback pattern (lines 71-84) is structurally identical to `main_chatbot` (main/nodes.py:240-253). DRY violation. **Action**: Extract a shared `_invoke_llm_with_fallback(llm, messages, node_name) -> dict` helper.

### 🔍 Nitpicks
- [ ] **[nodes.py:56] - Sync `def` but could be async**: Same inconsistency as `main_chatbot` — `onboarding_chatbot` is sync while `check_onboarding_status` is async. **Action**: Consider async for consistency.

### ✅ Verdict: **Mirrors main agent's debt patterns.** Duplicate LLM globals and copy-pasted error handling.

---

## File 11: `app/tools/jsearch_api.py`

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[jsearch_api.py:19-38] - `JSearchApiArgs` duplicates `JobSpecialistInput`**: `JSearchApiArgs` is structurally identical to `JobSpecialistInput` in `schemas.py` — same fields, same types, same defaults. Two schemas for the same data shape is a DRY violation and a maintenance trap. **Action**: Delete `JSearchApiArgs` and use `JobSpecialistInput` as the `args_schema` directly, or extract a shared base model.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[jsearch_api.py:115-116] - Synchronous `httpx.Client` in an async-first project**: The tool uses `httpx.Client()` (blocking) rather than `httpx.AsyncClient`. Since `search_jobs` is a sync node, LangGraph runs it in a thread executor — so it doesn't block the event loop directly. But it's inconsistent with the project's async-first design. **Action**: Convert to `async def` + `httpx.AsyncClient` and update `search_jobs` to be async. Low priority unless performance becomes an issue.
- [ ] **[jsearch_api.py:87] - `settings.JSEARCH_API_KEY` read inside function body**: The API key is read on every invocation rather than being injected. This works because of the singleton pattern, but it makes the function untestable without patching `settings`. Tests already `patch("app.tools.jsearch_api.settings")` — a deep internal path. **Action**: Accept as pragmatic for now.

### 🔍 Nitpicks
- [ ] **[jsearch_api.py:41-57] - `_format_salary` could use early return for `None`**: The function checks `salary_min and salary_max`, then `salary_min`, then `salary_max`, then `fallback`. Readable as-is, but a guard clause `if not any([salary_min, salary_max, fallback]): return None` at the top would eliminate one branch.

### ✅ Verdict: **Solid tool implementation.** Proper error-as-string pattern. Main issue is the duplicated schema.

---

## File 12: `app/tools/memory.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[memory.py:55-57, 92-93, 121-122, 152-154] - Bare `except Exception` in every tool**: All four tools (`update_my_profile`, `save_preference`, `delete_preference`, `finalize_profile`) wrap their entire body in `try/except Exception`. This is correct per `CONVENTIONS.md §2` (tools must not raise), but the `except Exception` is too broad — it swallows `KeyboardInterrupt`, `SystemExit`, etc. **Action**: Use `except (ValueError, TypeError, RuntimeError)` or at minimum `except Exception` with `raise` for `KeyboardInterrupt/SystemExit`. Alternatively, trust that only store/Pydantic errors can occur and catch `(StoreError, ValidationError)`.

### 🔍 Nitpicks
- [ ] **[memory.py:36] - Comment is redundant**: `# Get existing profile to merge updates` — the next line is `existing = await store.aget(namespace, "data")`. The code is self-explanatory. **Action**: Delete.
- [ ] **[memory.py:84-87] - Comments are redundant**: `# Use Pydantic model for validation` and `# Store using model_dump` — restating what the code does. **Action**: Delete.

### ✅ Verdict: **Well-structured tools.** Correct error-as-string pattern. Only the overly broad exception catches need tightening.

---

## File 13: `app/services/chat_service.py`

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[chat_service.py:43-44, 84-85] - Phantom state fields `inspect_attempts` and `inspect_results`**: Both `process_message` and `process_cv` inject `"inspect_attempts": 0` and `"inspect_results": {}` into the graph input. **These fields do not exist in `AgentState`** (state.py). They are ghosts of a removed "job inspection" feature. No node reads or writes them. Violates Design Principle #7 (No Phantom State). **Action**: Delete both fields from both methods' `inputs` dicts.
- [ ] **[chat_service.py:132-136] - `inspect_results` stitching is dead logic**: `_parse_agent_result` reads `result.get("inspect_results")` and attempts to stitch `full_description` from it. Since `inspect_results` is never populated by any node, this code path never executes. It's dead logic coupled to the phantom fields above. **Action**: Delete lines 132-136.
- [ ] **[chat_service.py:108-127 vs 201-220] - `_parse_agent_result` and `get_history` duplicate AI message parsing**: Both methods contain nearly identical logic to extract `ai_content` and `jobs` from an `AIMessage`: check for `final_answer` tool call → extract args OR fall back to `msg.content` → handle multipart content list. This is a textbook DRY violation — the same 15-line block copy-pasted twice. **Action**: Extract a shared `_extract_ai_content(msg: AIMessage) -> tuple[str, list]` helper and call it from both methods.
- [ ] **[chat_service.py:157-236] - `get_history` is ~80 lines**: This method iterates messages, filters system triggers, pairs Human→AI turns, parses AI content, handles multipart, and appends dangling turns. That's at least 4 responsibilities. **Action**: Decompose: (1) `_pair_messages(messages) -> list[Turn]` for the iteration/pairing, (2) reuse the shared `_extract_ai_content` helper for parsing.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[chat_service.py:119-127] - Multipart content handling is defensive but undocumented**: The `isinstance(ai_content, list)` branch handles Gemini's multipart response format (list of text/dict parts). This is a known Gemini quirk but has no comment explaining **why** it's needed. A future developer will wonder what `list` content looks like. **Action**: Add a one-line comment: `# Gemini may return multipart content as a list of text/dict segments`.
- [ ] **[chat_service.py:141-142] - MD5 hash for job id**: Uses `hashlib.md5` with a `# noqa: S324` suppression. The comment says "not used for security" which is correct, but `hashlib.sha256` would avoid the lint suppression entirely with negligible perf difference. **Action**: Consider switching to avoid the noqa.

### 🔍 Nitpicks
- [ ] **[chat_service.py:53] - `final_state = inputs` before loop**: This is a safe fallback pattern, but naming the variable `final_state` before the loop even starts is confusing — it's actually `default_state`. **Action**: Rename to `last_state = inputs` for clarity.
- [ ] **[chat_service.py:144] - Comment is redundant**: `# Return dict for Jinja2 template` — the project migrated to Next.js. Jinja2 is legacy context. **Action**: Update to `# Return dict for frontend JSON response` or delete.

### ✅ Verdict: **Second highest debt density.** Phantom state fields, dead inspect logic, and a major DRY violation between two AI-message parsers.

---

## File 14: `app/services/profile_service.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found. This file is clean._

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[profile_service.py:13-16] - `__init__` accepts `store` but not `user_id`**: All methods take a `user_id` parameter that defaults to `DEFAULT_USER_ID`. The user_id could be injected once at construction time rather than threaded through every method call. **Action**: Accept for now — the per-method signature allows future multi-tenancy. But document this design decision in a comment.

### 🔍 Nitpicks
- [ ] **[profile_service.py:22, 42, 57, 75] - Duplicate namespace construction**: `(user_id, "preferences")`, `(user_id, "decisions")`, etc. are constructed inline in every method. **Action**: Consider `_ns(user_id, kind) -> tuple` helper for consistency, or accept the repetition given its simplicity.

### ✅ Verdict: **Excellent.** Clean service with clear responsibilities. Well-documented methods.

---

## File 15: `app/services/admin_service.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[admin_service.py:1] - Uses `logging` instead of `structlog`**: Same convention violation as other files. **Action**: Replace with `structlog.get_logger(__name__)`.

### 🔍 Nitpicks
- [ ] **[admin_service.py:10-11] - `__init__` stores `pool` but only `reset_system` uses it**: The class is a thin wrapper around a single function call (`reset_db_state(self.pool)`). This class could be a plain function. However, Fat Service → Thin Class is an acceptable pattern for DI consistency with `ChatService` and `ProfileService`. **Action**: Accept — consistency matters more here.

### ✅ Verdict: **Clean.** 19 lines, single responsibility. Only the logger choice needs fixing.

---

## File 16: `app/api/routes.py`

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[routes.py:1] - Uses `logging` instead of `structlog`**: Same convention violation. **Action**: Replace with `structlog.get_logger(__name__)`.
- [ ] **[routes.py:63, 78] - Hardcoded `DEFAULT_USER_ID` passed to services**: `chat_service.process_message(...)` and `profile_service.get_pending_jobs(DEFAULT_USER_ID)` wire the user_id at the API layer. This means multi-tenancy would require touching every route. **Action**: Extract `user_id` from a request header or auth dependency and inject it. For now, centralize it via a `get_user_id()` dependency in `dependencies.py`.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[routes.py:89-95] - Broad `except Exception` in `/api/chat`**: The endpoint catches all exceptions and returns a 200 with a Markdown error string. This is intentional (soft degradation), but it swallows unexpected errors silently. **Action**: Add `logger.exception(...)` inside the catch block so errors are always visible in logs, even when the user sees a graceful response.
- [ ] **[routes.py:37-49] - `/api/feedback` route builds `DecisionLog` inline**: The route handler manually constructs a `DecisionLog` and calls `store.aput()` directly, bypassing `ProfileService`. This violates the service-layer pattern used everywhere else. **Action**: Add a `log_decision()` method to `ProfileService` and delegate from the route.

### ✅ Verdict: **Functional but has layering violations.** Feedback route bypasses the service layer.

---

## File 17: `app/api/schemas.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### ✅ Verdict: **Perfect.** 22 lines, clean Pydantic models. No findings.

---

## File 18: `app/api/dependencies.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### 🔍 Nitpicks
- [ ] **[dependencies.py:25-35] - Services reconstructed on every request**: `get_chat_service()` creates a new `ChatService` and `ProfileService` on every call. These are stateless wrappers, so this is functionally fine, but it means object creation overhead on every request. **Action**: Accept — the objects are lightweight. If performance becomes an issue, consider `@lru_cache` or app-state caching.

### ✅ Verdict: **Clean.** Single wiring point, correct DI pattern.

---

## File 19: `app/api/middleware.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### ✅ Verdict: **Excellent.** 47 lines, clean middleware. Request correlation, timing, structured logging — all textbook.

---

## File 20: `app/core/config.py`

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[config.py:24-26] - Dead Adzuna config fields**: `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` remain in `Settings`. The Adzuna API was fully replaced by JSearch in Sprint 6. The legacy tools (`adzuna_api.py`, `scraper.py`) were deleted. These fields are dead config violating Design Principle #7. **Action**: Delete both fields.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[config.py:9] - `APP_NAME` says `"AI Scraper Bot"`**: This name is from the project's early prototype days. The project is now "CVviewer". **Action**: Update to `"CVviewer"` or read from an env var.
- [ ] **[config.py:47-50] - `STATE_LOG_PATH` imports `tempfile` inside a property**: Lazy import inside a property is unusual. It works but is surprising. **Action**: Move `import tempfile` to the top of the file.

### 🔍 Nitpicks
- [ ] **[config.py:55] - Module-level `settings = Settings()` singleton**: This is a common pattern but means settings are resolved at import time. Tests that need different settings must monkeypatch the object. **Action**: Accept — standard for FastAPI projects.

### ✅ Verdict: **Has dead Adzuna config.** Otherwise solid settings management.

---

## File 21: `app/core/logging.py`

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[logging.py:21-23] - `add_request_id_from_context` is a dead no-op**: This function takes `logger`, `method_name`, `event_dict` and returns `event_dict` unchanged. It does nothing. It is not referenced in the `shared_processors` list (lines 49-58). Dead code. **Action**: Delete.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[logging.py:99] - File truncation pattern is non-obvious**: `settings.STATE_LOG_PATH.open("w").close()` truncates the log file at startup. This works but is obscure. **Action**: Replace with `settings.STATE_LOG_PATH.write_text("")` for clarity.

### ✅ Verdict: **Solid logging setup.** One dead function to remove.

---

## File 22: `app/core/database.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[database.py:1] - Uses `logging` instead of `structlog`**: Convention violation. **Action**: Replace.

### ✅ Verdict: **Clean.** Well-structured async database management. Proper connection pooling.

---

## File 23: `app/core/node_logging_utils.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### ✅ Verdict: **Perfect.** 17 lines, single responsibility, clean structured logging.

---

## File 24: `app/core/snapshot_logging_utils.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### ✅ Verdict: **Excellent.** Clean recursive sanitization with Pydantic v1/v2 compat.

---

## File 25: `app/main.py`

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[main.py:55] - CORS origin hardcoded to `localhost:3000`**: `allow_origins=["http://localhost:3000"]` — this will break in production. **Action**: Move to `settings.CORS_ORIGINS: list[str]` and read from env.
- [ ] **[main.py:1] - Uses `logging` instead of `structlog`**: Convention violation. **Action**: Replace.

### 🔍 Nitpicks
- [ ] **[main.py:29] - Pool `max_size=20` duplicated**: Same pool config (`max_size=20, kwargs={"autocommit": True}`) appears here and in `database.py:39`. **Action**: Extract pool creation into `database.py` and call it from `lifespan`.

### ✅ Verdict: **Clean entrypoint.** CORS hardcoding is the main concern.

---

## Files 26-34: Tests (`tests/`)

### `tests/unit/test_agent.py`

#### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[test_agent.py:22] - Module-level graph compilation**: `graph = get_compiled_graph(checkpointer=MemorySaver(), store=InMemoryStore())` runs at **import time**. If the graph ever fails to compile, every test in this module fails with an obscure import error. **Action**: Move into a `@pytest.fixture(scope="module")`.

#### ⚠️ Test Quality (Should Fix)
- [ ] **[test_agent.py:42-61] - Tests patch deep internal paths**: `patch("app.agent.main.nodes.main_llm")` — this is a symptom of the module-level LLM globals issue flagged in File 6. When DI is fixed, these patches become simpler.
- [ ] **[test_agent.py:107-116] - Test fixtures include `active_agent`**: Tests set `"active_agent": "onboarding"` — a phantom state field. When `active_agent` is deleted from state, these fixtures must be cleaned.

### `tests/unit/test_main_nodes.py`

#### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[test_main_nodes.py:9-10] - Double import of `AIMessage`**: `from langchain_core.messages import AIMessage as AIMsg` AND `from langchain_core.messages import AIMessage as _AIMessage` — two aliases for the exact same class. Pick one. **Action**: Use `AIMessage` everywhere, delete the aliases.

#### ⚠️ Test Quality (Should Fix)
_Tests are well-structured. Good AAA pattern, clear docstrings._

### `tests/unit/test_chat_service.py` — ✅ **Clean.** Good fixture helpers, proper mocking, clear AAA.

### `tests/unit/test_decision_log.py` — ✅ **Clean.** Focused Pydantic validation tests, deterministic id checks.

### `tests/unit/test_job_specialist_nodes.py` — ✅ **Clean.** Good coverage of parallel calls, seen-job filtering, arg forwarding.

### `tests/unit/test_loop_limits.py` — ✅ **Clean.** Boundary tests for `route_main` at 0, 2, 3, 10 attempts. Textbook.

### `tests/unit/test_memory_tools.py` — ✅ **Clean.** Custom `FailingPutStore`/`FailingDeleteStore` subclasses are a clever test pattern.

### `tests/unit/test_message_trimming.py` — ✅ **Excellent.** Tests 3 facts about custom code (not LangChain internals), plus state mutation safety.

### `tests/unit/test_pending_jobs.py` — ✅ **Clean.** Full CRUD coverage, dedup test, edge cases.

### `tests/unit/test_seen_jobs.py` — ✅ **Excellent.** 5 targeted facts with clear docstrings explaining what each guards.

### `tests/unit/test_snapshot_logging_utils.py` — ✅ **Clean.** Covers token fields, preview truncation, None safety.

### `tests/test_logging.py`

#### ⚠️ Test Quality (Should Fix)
- [ ] **[test_logging.py:121] - Duplicate assertion**: `assert len(caplog.records) == 1` appears twice on consecutive lines (120 and 121). Copy-paste error. **Action**: Delete the duplicate.

### `tests/verify_memory.py`

#### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[verify_memory.py] - Entire file is broken dead code**: This manual verification script calls `save_preference` with the old API signature (`value`, `category` kwargs instead of `key`, `label`, `sentiment`). It would crash if run. It's not a pytest test (runs via `__main__`), bypasses the test framework, and requires a live Postgres instance. Violates Design Principle #7 (No Dead Code). **Action**: Delete this file entirely. Its functionality is already covered by `test_memory_tools.py`.

### `tests/integration/conftest.py` — ✅ **Excellent.** Clean testcontainers setup.

### `tests/integration/test_api_chat.py` — ✅ **Clean.** Good soft degradation test.

### `tests/integration/test_feedback_route.py` — ✅ **Clean.** Proper store override, cleanup in `finally` blocks.

---

# ══════════════════════════════════════════════════════
# AUDIT SUMMARY
# ══════════════════════════════════════════════════════

## Issue Counts

| Severity | Count |
|---|---|
| 🚨 Critical (Must Fix) | **18** |
| ⚠️ Should Fix | **20** |
| 🔍 Nitpick | **13** |

## Top 5 Debt Hotspots (Prioritized)

| Rank | File | 🚨 | ⚠️ | Primary Issue |
|---|---|---|---|---|
| 1 | `app/agent/main/nodes.py` | 3 | 3 | Module-level LLM globals, oversized `main_chatbot`, fragile handoff |
| 2 | `app/services/chat_service.py` | 4 | 2 | Phantom `inspect_*` fields, DRY violation, oversized `get_history` |
| 3 | `app/agent/graph.py` | 2 | 2 | SRP violation in `call_job_specialist`, wrong logger |
| 4 | `app/agent/onboarding/nodes.py` | 2 | 2 | Duplicate LLM globals, copy-pasted error handling |
| 5 | `app/agent/constants.py` | 2 | 1 | Dead `ROUTER_NODE`, missing `MAX_SEARCH_ATTEMPTS` |

## Cross-Cutting Issues (Systemic)

| Issue | Files Affected | Action |
|---|---|---|
| `logging` instead of `structlog` | `graph.py`, `job_search/graph.py`, `routes.py`, `admin_service.py`, `database.py`, `main.py` | Global find-and-replace |
| Module-level LLM instantiation | `main/nodes.py`, `onboarding/nodes.py` | DI refactor in `get_compiled_graph()` |
| Fragile `"Onboarding complete"` string detection | `main/nodes.py`, `onboarding/nodes.py` | Shared constant or structured signal |
| `active_agent` phantom state | `state.py` + 6 test fixtures | Delete field and clean fixtures |
| Dead Adzuna/inspect artifacts | `config.py`, `chat_service.py` | Delete dead fields and logic |

## Recommended Sprint Ordering

1. **Quick Wins (30 min)**: Delete dead code (`ROUTER_NODE`, `add_request_id_from_context`, Adzuna config, `verify_memory.py`, `active_agent` field, phantom `inspect_*` fields). Zero risk.
2. **Logger Fix (15 min)**: Global swap `logging` → `structlog` across 6 files. Mechanical.
3. **DRY Refactors (1h)**: Extract `_extract_ai_content()` helper, `_invoke_llm_with_fallback()` helper, `ONBOARDING_COMPLETE_SIGNAL` constant.
4. **DI Refactor (2h)**: Move LLM construction into `get_compiled_graph()` and inject via closures. Update all test patches.
5. **Architectural (2h)**: Decompose `main_chatbot`, decompose `get_history`, move feedback logic into `ProfileService`, add `MAX_SEARCH_ATTEMPTS` constant.
