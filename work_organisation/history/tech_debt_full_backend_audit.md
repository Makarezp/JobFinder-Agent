# Tech Debt Audit: Full Backend Sweep

**Auditor**: Clean Code Auditor (Senior Python Architect)
**Date**: 2026-03-05
**Scope**: All backend source (`app/`) and tests (`tests/`)

---

## File 1: `app/agent/state.py` - done

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[state.py:17] - `active_agent` is phantom state**: This field is defined in `AgentState` but never read by any production code. Routing is driven by `onboarding_complete` via the `router()` function in `graph.py`. Tests set it as filler but no node or router inspects it. Violates Design Principle #7 (No Phantom State). **Action**: Delete the `active_agent` field. Remove from all test fixtures.
- [ ] **[state.py:13-14] - Weak typing on `user_profile` and `preferences`**: Both are `dict[str, Any] | None`. The project has Pydantic models (`UserProfile`, `Preference`) for these. Using `dict[str, Any]` defeats contract stability (Design Principle #2). **Action**: Consider using `UserProfile | None` and `dict[str, Preference] | None` or at minimum add a comment explaining why raw dicts are needed here (LangGraph serialisation constraint).
- [ ] **[state.py:19] - `recent_decisions` typed as `list[dict[str, Any]]`**: Same issue — `DecisionLog` exists but is not used as the type. **Action**: Same approach as above.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[state.py:8-9] - Docstring is redundant**: `"""State for the agent graph."""` adds zero information beyond what the class name already communicates. **Action**: Either delete or replace with a meaningful docstring explaining the field lifecycle.

---

## File 2: `app/agent/schemas.py` - done

### 🚨 Critical Tech Debt (Must Fix)
_None found. This file is clean._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### 🔍 Nitpicks
- [ ] **[schemas.py:31] - Misleading `id` field description**: Description says `"Computed in _parse_agent_result, not by the LLM"` — this leaks internal implementation detail into a Pydantic schema that could be exposed externally. The field description should describe the data, not the pipeline. **Action**: Shorten to `"Unique identifier for frontend tracking."`.
- [ ] **[schemas.py:45] - `jobs` default is mutable `[]`**: `Field(default=[], ...)` — Pydantic handles this safely, but the semantic intent is `None` (no jobs) vs `[]` (searched but found nothing). Having `default=[]` with type `list | None` is ambiguous. **Action**: Change default to `None` to be explicit, or remove `| None` and always use `[]` for empty. Pick one semantic.

### ✅ Verdict: **Mostly clean.** Well-structured Pydantic models with clear field descriptions.

---

## File 3: `app/agent/graph.py` - done

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

## File 4: `app/agent/constants.py` - done

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[constants.py:25] - `ROUTER_NODE` is dead code**: `ROUTER_NODE: Final[str] = "router"` is defined but never imported or used anywhere in the codebase. The `router` function in `graph.py` is a conditional edge callback, not a registered node. Violates Design Principle #7 (No Dead Code). **Action**: Delete.
- [ ] **[constants.py] - Missing `MAX_SEARCH_ATTEMPTS` constant**: The magic number `3` appears in `route_main` (main/nodes.py:271) and in the system prompt (`SYSTEM_PROMPT` mentions "3 total search attempts"). This coupling between router logic and prompt text is held together by nothing but hope. **Action**: Add `MAX_SEARCH_ATTEMPTS: Final[int] = 3` here and reference it in both `route_main` and the prompt template.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[constants.py:14-18] - State key constants are inconsistently used**: `MESSAGES_KEY`, `CV_RAW_TEXT_KEY`, `ONBOARDING_COMPLETE_KEY`, `ACTIVE_AGENT_KEY` are defined, but production code frequently accesses state via string literals instead (e.g., `state.get("search_attempts")`, `state.get("user_profile")`). Either use the constants everywhere or delete them. **Action**: Audit all state access and pick one approach.

### ✅ Verdict: **Has dead code and a dangerous magic number.**

---

## File 5: `app/agent/memory_schema.py` - skipped

### 🚨 Critical Tech Debt (Must Fix)
_None found. This file is clean._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### 🔍 Nitpicks
- [ ] **[memory_schema.py:11] - Hardcoded `id: int = 1`**: `UserProfile.id` defaults to `1`. In a single-user MVP this works, but it's a latent bug for multi-tenancy. The `user_id` is already managed as a string in the store namespaces (`"default_user"`). This integer id is unused by any store logic. **Action**: Consider removing or aligning with the string-based `user_id`.

### ✅ Verdict: **Excellent.** Clean Pydantic models with proper field descriptions and Literal constraints.

---

## File 6: `app/agent/main/nodes.py` — ⚠️ PARTIALLY DONE

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[nodes.py:29-35] - Module-level LLM instantiation violates Dependency Injection** — **SKIPPED: Needs dedicated refactor ticket.** Affects both `main/nodes.py` and `onboarding/nodes.py`, changes graph wiring in `get_compiled_graph()`, and requires updating all test patches. Too risky for a cleanup sweep.
- [x] **[nodes.py:186-253] - `main_chatbot` is ~67 lines and does 5 things** — **DONE.** Extracted `_build_system_prompt(profile, preferences, decisions) -> str` helper.
- [x] **[nodes.py:39-52] - `_is_fresh_onboarding_handoff` has fragile coupling** — **DONE.** Added `ONBOARDING_COMPLETE_SIGNAL` constant in `constants.py`. Used in both `main/nodes.py` and `onboarding/nodes.py`.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [x] **[nodes.py:69] - Stale comment** — **DONE.** Deleted.
- [x] **[nodes.py:170] - Inline `type: ignore` with string key access** — **SKIPPED.** LangGraph TypedDict limitation; wrapper adds complexity without safety gain.
- [x] **[nodes.py:199-204] - Ternary-formatted multiline block** — **DONE.** Absorbed into `_build_system_prompt` extraction.

### 🔍 Nitpicks
- [x] **[nodes.py:241] - `main_llm.invoke` is synchronous** — **SKIPPED.** LangGraph handles via thread executor; no functional benefit.

### ✅ Verdict: **Partially resolved.** Remaining: module-level LLM globals need a dedicated DI refactor ticket (affects `main/nodes.py` + `onboarding/nodes.py` + `graph.py` + all test patches).

---

## File 7: `app/agent/main/prompts.py` - done

### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[prompts.py:98-99] - Hardcoded "3 searches" in prompt text**: `"You have a strict budget of 3 searches per conversation turn"` — this number must match `route_main`'s `>= 3` threshold. If either changes independently, the agent and the router will disagree. **Action**: Use a template variable `{max_search_attempts}` and inject from the shared constant proposed for `constants.py`.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[prompts.py:103] - Prompt is not terminated with `\n`**: The `SYSTEM_PROMPT` string ends on line 103 with `\"\"\"` but the last content line (102) has no trailing newline. Minor, but some LLMs are sensitive to trailing whitespace. **Action**: Ensure consistent trailing newline.

### 🔍 Nitpicks
- [ ] **[prompts.py:1] - Docstring is generic**: `"""Agent related prompts."""` — could be more descriptive: `"""System prompt for the main job-hunting agent."""`. **Action**: Improve.

### ✅ Verdict: **Well-written prompt.** Only real issue is the hardcoded `3` that must stay in sync with router logic.

---

## File 8: `app/agent/main/tools.py` -done

### 🚨 Critical Tech Debt (Must Fix)
_None found. This file is clean._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### 🔍 Nitpicks
- [ ] **[tools.py:25] - `job_specialist_tool` returns a throwaway string**: `return "Job Specialist invoked."` — this stub return is never read because `call_job_specialist` in `graph.py` intercepts the tool call before it executes. The function body exists only to satisfy LangChain's `@tool` decorator. **Action**: Add a one-line comment explaining why this return value is unused (it's a routing sentinel, not a real tool).
- [ ] **[tools.py:34] - Same for `final_answer`**: `return "Final Answer Processed"` — same situation. The return is never consumed; `_parse_agent_result` reads the tool call args, not the result. **Action**: Same — add a comment.

### ✅ Verdict: **Clean.** Thin registration file doing its job. Stub returns are intentional.

---

## File 9: `app/agent/job_search/` (nodes.py, state.py, graph.py)Mo

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

## File 10: `app/agent/onboarding/` (nodes.py, prompts.py, tools.py) — ⚠️ PARTIALLY DONE

### `onboarding/prompts.py` — ✅ **Clean.** No findings.

### `onboarding/tools.py` — ✅ **Clean.** No findings.

### `onboarding/nodes.py`

#### 🚨 Critical Tech Debt (Must Fix)
- [ ] **[nodes.py:27-33] - Duplicate module-level LLM instantiation** — **SKIPPED: Same dedicated DI refactor ticket as File 6.** Affects both `main/nodes.py` and `onboarding/nodes.py`.
- [x] **[nodes.py:93] - `hasattr(ai_message, "tool_calls")` is defensive band-aid** — **DONE.** Replaced with `isinstance(ai_message, AIMessage) and ai_message.tool_calls` (fixed during File 6 implementation).

#### ⚠️ Maintainability & Clean Code (Should Fix)
- [x] **[nodes.py:107-113] - `route_after_onboarding_tools` uses fragile string detection** — **DONE.** Now uses `ONBOARDING_COMPLETE_SIGNAL` constant (fixed during File 6 implementation).
- [x] **[nodes.py:56-84] - Copy-pasted error handling** — **SKIPPED.** Fallback messages are intentionally different between nodes. Extracting a shared helper would require parameterising the message, adding complexity for 8 lines of duplication.

### 🔍 Nitpicks
- [x] **[nodes.py:56] - Sync `def` but could be async** — **SKIPPED.** LangGraph handles via thread executor; no functional benefit.

### ✅ Verdict: **Partially resolved.** Remaining: module-level LLM globals (same dedicated DI refactor ticket as File 6).

---

## File 11: `app/tools/jsearch_api.py` — DONE

### 🚨 Critical Tech Debt (Must Fix)
- [x] **[jsearch_api.py:19-38] - `JSearchApiArgs` duplicates `JobSpecialistInput`** — **DONE.** Deleted `JSearchApiArgs`, replaced with `JobSpecialistInput` as `args_schema`.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [x] **[jsearch_api.py:115-116] - Synchronous `httpx.Client`** — **SKIPPED.** Low priority per audit; no perf issue.
- [x] **[jsearch_api.py:87] - `settings.JSEARCH_API_KEY` read inside function body** — **SKIPPED.** Pragmatic for now per audit.

### 🔍 Nitpicks
- [x] **[jsearch_api.py:41-57] - `_format_salary` early return** — **SKIPPED.** Readable as-is.

### ✅ Verdict: **Resolved.** Duplicate schema eliminated.

---

## File 12: `app/tools/memory.py` — DONE

### ⚠️ Maintainability & Clean Code (Should Fix)
- [x] **[memory.py:55-57, 92-93, 121-122, 152-154] - Bare `except Exception`** — **SKIPPED.** Correct per CONVENTIONS.md §2 (tools must not raise). Narrowing risks missing store errors.

### 🔍 Nitpicks
- [x] **[memory.py:36] - Redundant comment** — **DONE.** Deleted.
- [x] **[memory.py:84-87] - Redundant comments** — **DONE.** Deleted.

### ✅ Verdict: **Resolved.** Redundant comments removed.

---

## File 13: `app/services/chat_service.py` — DONE

### 🚨 Critical Tech Debt (Must Fix)
- [x] **[chat_service.py:43-44, 84-85] - Phantom state fields `inspect_attempts` and `inspect_results`** — **DONE.** Deleted from both `process_message` and `process_cv` inputs.
- [x] **[chat_service.py:132-136] - `inspect_results` stitching is dead logic** — **DONE.** Deleted dead code and removed corresponding test (`test_parse_agent_result_stitches_full_description_from_inspect_results`).
- [x] **[chat_service.py:108-127 vs 201-220] - DRY violation in AI message parsing** — **DONE.** Extracted `_extract_ai_content(msg) -> tuple[str, list]` helper, used in both `_parse_agent_result` and `get_history`. Also fixed `hasattr` band-aids.
- [x] **[chat_service.py:157-236] - `get_history` is ~80 lines** — **DONE (partial).** Reduced via `_extract_ai_content` extraction. Further decomposition skipped — acceptable size now.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [x] **[chat_service.py:119-127] - Multipart content handling undocumented** — **DONE.** Added Gemini multipart comment in `_extract_ai_content` docstring.
- [x] **[chat_service.py:141-142] - MD5 hash for job id** — **SKIPPED.** Works fine, noqa is documented.

### 🔍 Nitpicks
- [x] **[chat_service.py:53] - `final_state = inputs` naming** — **DONE.** Renamed to `last_state`.
- [x] **[chat_service.py:144] - Stale Jinja2 comment** — **DONE.** Deleted.

### ✅ Verdict: **Resolved.** All phantom state, dead logic, and DRY violations eliminated.

---

## File 14: `app/services/profile_service.py` — SKIPPED (already excellent, no actionable items)

### ✅ Verdict: **No changes needed.**

---

## File 15: `app/services/admin_service.py` — DONE

### ⚠️ Maintainability & Clean Code (Should Fix)
- [x] **[admin_service.py:1] - Uses `logging` instead of `structlog`** — **DONE.** Replaced.

### ✅ Verdict: **Resolved.**

---

## File 16: `app/api/routes.py` — DONE

### 🚨 Critical Tech Debt (Must Fix)
- [x] **[routes.py:1] - Uses `logging` instead of `structlog`** — **DONE.** Replaced. Also removed `traceback` import.
- [x] **[routes.py:63, 78] - Hardcoded `DEFAULT_USER_ID`** — **SKIPPED.** Multi-tenancy prep; acceptable for MVP.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [x] **[routes.py:89-95] - Broad `except Exception`** — **DONE.** Replaced manual `traceback.format_exc()` with `logger.exception()`.
- [x] **[routes.py:37-49] - `/api/feedback` route bypasses service layer** — **ALREADY FIXED.** Route now delegates to `ProfileService.log_decision()` (audit was stale).

### ✅ Verdict: **Resolved.**

---

## File 17: `app/api/schemas.py` — SKIPPED (clean, no actionable items)

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### ✅ Verdict: **Perfect.** 22 lines, clean Pydantic models. No findings.

---

## File 18: `app/api/dependencies.py` — SKIPPED (clean, nitpick only)

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### 🔍 Nitpicks
- [ ] **[dependencies.py:25-35] - Services reconstructed on every request**: `get_chat_service()` creates a new `ChatService` and `ProfileService` on every call. These are stateless wrappers, so this is functionally fine, but it means object creation overhead on every request. **Action**: Accept — the objects are lightweight. If performance becomes an issue, consider `@lru_cache` or app-state caching.

### ✅ Verdict: **Clean.** Single wiring point, correct DI pattern.

---

## File 19: `app/api/middleware.py` — SKIPPED (excellent, no findings)

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### ✅ Verdict: **Excellent.** 47 lines, clean middleware. Request correlation, timing, structured logging — all textbook.

---

## File 20: `app/core/config.py` — DONE

### 🚨 Critical Tech Debt (Must Fix)
- [x] **[config.py:24-26] - Dead Adzuna config fields**: `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` remain in `Settings`. The Adzuna API was fully replaced by JSearch in Sprint 6. The legacy tools (`adzuna_api.py`, `scraper.py`) were deleted. These fields are dead config violating Design Principle #7. **Action**: Delete both fields.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [x] **[config.py:9] - `APP_NAME` says `"AI Scraper Bot"`**: This name is from the project's early prototype days. The project is now "CVviewer". **Action**: Update to `"CVviewer"` or read from an env var.
- [x] **[config.py:47-50] - `STATE_LOG_PATH` imports `tempfile` inside a property**: Lazy import inside a property is unusual. It works but is surprising. **Action**: Move `import tempfile` to the top of the file.

### 🔍 Nitpicks
- [ ] **[config.py:55] - Module-level `settings = Settings()` singleton**: This is a common pattern but means settings are resolved at import time. Tests that need different settings must monkeypatch the object. **Action**: Accept — standard for FastAPI projects.

### ✅ Verdict: **Has dead Adzuna config.** Otherwise solid settings management.

---

## File 21: `app/core/logging.py` — DONE

### 🚨 Critical Tech Debt (Must Fix)
- [x] **[logging.py:21-23] - `add_request_id_from_context` is a dead no-op**: This function takes `logger`, `method_name`, `event_dict` and returns `event_dict` unchanged. It does nothing. It is not referenced in the `shared_processors` list (lines 49-58). Dead code. **Action**: Delete.

### ⚠️ Maintainability & Clean Code (Should Fix)
- [x] **[logging.py:99] - File truncation pattern is non-obvious**: `settings.STATE_LOG_PATH.open("w").close()` truncates the log file at startup. This works but is obscure. **Action**: Replace with `settings.STATE_LOG_PATH.write_text("")` for clarity.

### ✅ Verdict: **Solid logging setup.** One dead function to remove.

---

## File 22: `app/core/database.py` — DONE

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
- [x] **[database.py:1] - Uses `logging` instead of `structlog`**: Convention violation. **Action**: Replace.

### ✅ Verdict: **Clean.** Well-structured async database management. Proper connection pooling.

---

## File 23: `app/core/node_logging_utils.py` — SKIPPED (perfect, no findings)

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### ✅ Verdict: **Perfect.** 17 lines, single responsibility, clean structured logging.

---

## File 24: `app/core/snapshot_logging_utils.py` — SKIPPED (excellent, no findings)

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
_None found._

### ✅ Verdict: **Excellent.** Clean recursive sanitization with Pydantic v1/v2 compat.

---

## File 25: `app/main.py` — DONE

### 🚨 Critical Tech Debt (Must Fix)
_None found._

### ⚠️ Maintainability & Clean Code (Should Fix)
- [ ] **[main.py:55] - CORS origin hardcoded to `localhost:3000`** — **SKIPPED.** Needs `settings.CORS_ORIGINS` config field; separate ticket.: `allow_origins=["http://localhost:3000"]` — this will break in production. **Action**: Move to `settings.CORS_ORIGINS: list[str]` and read from env.
- [x] **[main.py:1] - Uses `logging` instead of `structlog`**: Convention violation. **Action**: Replace.

### 🔍 Nitpicks
- [ ] **[main.py:29] - Pool `max_size=20` duplicated**: Same pool config (`max_size=20, kwargs={"autocommit": True}`) appears here and in `database.py:39`. **Action**: Extract pool creation into `database.py` and call it from `lifespan`.

### ✅ Verdict: **Clean entrypoint.** CORS hardcoding is the main concern.

---

## Files 26-34: Tests (`tests/`)

### `tests/unit/test_agent.py` — DONE

#### 🚨 Critical Tech Debt (Must Fix)
- [x] **[test_agent.py:22] - Module-level graph compilation**: `graph = get_compiled_graph(checkpointer=MemorySaver(), store=InMemoryStore())` runs at **import time**. If the graph ever fails to compile, every test in this module fails with an obscure import error. **Action**: Move into a `@pytest.fixture(scope="module")`.

#### ⚠️ Test Quality (Should Fix)
- [ ] **[test_agent.py:42-61] - Tests patch deep internal paths**: `patch("app.agent.main.nodes.main_llm")` — this is a symptom of the module-level LLM globals issue flagged in File 6. When DI is fixed, these patches become simpler.
- [x] **[test_agent.py:107-116] - Test fixtures include `active_agent`** — **DONE.** Already removed in earlier passes.: Tests set `"active_agent": "onboarding"` — a phantom state field. When `active_agent` is deleted from state, these fixtures must be cleaned.

### `tests/unit/test_main_nodes.py` — DONE

#### 🚨 Critical Tech Debt (Must Fix)
- [x] **[test_main_nodes.py:9-10] - Double import of `AIMessage`**: `from langchain_core.messages import AIMessage as AIMsg` AND `from langchain_core.messages import AIMessage as _AIMessage` — two aliases for the exact same class. Pick one. **Action**: Use `AIMessage` everywhere, delete the aliases.

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

### `tests/test_logging.py` — DONE

#### ⚠️ Test Quality (Should Fix)
- [x] **[test_logging.py:121] - Duplicate assertion**: `assert len(caplog.records) == 1` appears twice on consecutive lines (120 and 121). Copy-paste error. **Action**: Delete the duplicate.

### `tests/verify_memory.py` — DONE

#### 🚨 Critical Tech Debt (Must Fix)
- [x] **[verify_memory.py] - Entire file is broken dead code** — **DONE.** Deleted.: This manual verification script calls `save_preference` with the old API signature (`value`, `category` kwargs instead of `key`, `label`, `sentiment`). It would crash if run. It's not a pytest test (runs via `__main__`), bypasses the test framework, and requires a live Postgres instance. Violates Design Principle #7 (No Dead Code). **Action**: Delete this file entirely. Its functionality is already covered by `test_memory_tools.py`.

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
