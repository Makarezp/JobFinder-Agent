# [DONE] Ticket 002: Remove `description` from `DecisionLog` and omit empty feedback section from prompt

## Overview

Two related prompt quality issues. First: `DecisionLog.description` stores the LLM's own AI match summary for a job, then feeds it back to the LLM as "user feedback." This is circular — the LLM wrote it, not the user. The only signal that belongs in feedback is the user's optional `reason`. Second: when no decisions exist, the system prompt currently injects `"No feedback history yet."` under the `RECENT USER FEEDBACK` heading — the instruction to "use this history" is directly contradicted by "there is no history," adding noise with zero information value. Both are fixed here.

---

## Touch Points (all must be updated atomically)

> **No backwards compatibility required.** Clear the store before testing.

1. `app/agent/memory_schema.py` — schema definition
2. `app/api/schemas.py` — `FeedbackRequest` (API ingress)
3. `app/services/profile_service.py` — `log_decision` method signature
4. `app/api/routes.py` — `feedback_page` route handler
5. `app/agent/main/nodes.py` — `_format_decisions_summary`
6. `frontend/src/core/types/api.ts` — `DecisionLogEntry` + `FeedbackRequest` interfaces
7. `frontend/src/core/store/useJobStore.ts` — `submitFeedback` payload construction
8. `frontend/src/components/ProfileView.tsx` — `DecisionLogCard` render
9. **Tests** — backend unit + integration, frontend store tests

---

## Implementation Steps

### 1. Backend Schema — `app/agent/memory_schema.py`

Remove `description` from `DecisionLog`:

```python
# REMOVE:
description: str | None = None


# Result:
class DecisionLog(BaseModel):
    job_title: str
    company: str
    action: Literal["pass", "pursue"]
    reason: str | None = None
    timestamp: str
```

### 2. API Ingress — `app/api/schemas.py`

Remove `description` from `FeedbackRequest`:

```python
# REMOVE:
description: str | None = None


# Result:
class FeedbackRequest(BaseModel):
    job_title: str
    company: str
    action: Literal["pass", "pursue"]
    reason: str | None = None
    job_id: str
```

### 3. Service — `app/services/profile_service.py`

Remove `description` parameter from `log_decision`:

```python
# BEFORE:
async def log_decision(self, job_title, company, action, description, reason, user_id) -> None:

# AFTER:
async def log_decision(self, job_title, company, action, reason, user_id) -> None:
```

Update the `DecisionLog(...)` construction inside to remove `description=description`.

### 4. Route Handler — `app/api/routes.py`

Remove `description` from the `log_decision` call:

```python
# BEFORE:
await service.log_decision(
    job_title=body.job_title,
    company=body.company,
    action=body.action,
    description=body.description,
    reason=body.reason,
    user_id=DEFAULT_USER_ID,
)

# AFTER:
await service.log_decision(
    job_title=body.job_title,
    company=body.company,
    action=body.action,
    reason=body.reason,
    user_id=DEFAULT_USER_ID,
)
```

### 5. System Prompt Formatter — `app/agent/main/nodes.py`

Two changes here.

**5a. Remove `description` from `_format_decisions_summary` and return `None` when empty.**

The function must return `str | None` — `None` signals "no decisions" so the caller can omit the section entirely:

```python
def _format_decisions_summary(decisions: list[dict[str, Any]]) -> str | None:
    if not decisions:
        return None
    lines: list[str] = []
    for d in decisions:
        action = d.get("action", "").upper()
        title = d.get("job_title", "?")
        company = d.get("company", "?")
        reason = d.get("reason")
        if reason:
            lines.append(f'- {action} "{title}" at {company}: "{reason}"')
        else:
            lines.append(f'- {action} "{title}" at {company}')
    return "Recent Feedback:\n" + "\n".join(lines)
```

**5b. Gate the `RECENT USER FEEDBACK` block in `main_chatbot` on the return value.**

`main_chatbot` currently builds the system prompt via `SYSTEM_PROMPT.format(decisions_summary=...)`. The prompt template must be updated so the entire feedback section is conditional. Change `main_chatbot` to build the prompt differently:

```python
decisions_summary = _format_decisions_summary(decisions)

feedback_block = (
    f"\n**RECENT USER FEEDBACK:**\n{decisions_summary}\n"
    "Use this history to avoid suggesting similar jobs. "
    "Do not mention this feedback log explicitly unless the user asks about it.\n"
    if decisions_summary
    else ""
)

formatted_prompt = SYSTEM_PROMPT.format(
    name=...,
    role=...,
    profile_summary=...,
    preferences_summary=...,
    feedback_block=feedback_block,
)
```

Update `app/agent/main/prompts.py` `SYSTEM_PROMPT` to replace the static feedback section with `{feedback_block}`:

```python
# REMOVE these lines from SYSTEM_PROMPT:
**RECENT USER FEEDBACK:**
{decisions_summary}
Use this history to avoid suggesting similar jobs. Do not mention this feedback log explicitly unless the user asks about it.

# REPLACE WITH:
{feedback_block}
```

This way when `decisions` is empty, `{feedback_block}` is an empty string and the section is absent entirely from the prompt.

### 6. Frontend Types — `frontend/src/core/types/api.ts`

Remove `description` from both interfaces:

```typescript
// DecisionLogEntry: remove description field
export interface DecisionLogEntry {
  job_title: string;
  company: string;
  action: "pass" | "pursue";
  reason: string | null;
  timestamp: string;
}

// FeedbackRequest: remove description field
export interface FeedbackRequest {
  job_title: string;
  company: string;
  action: "pass" | "pursue";
  reason: string | null;
  job_id: string;
}
```

### 7. Frontend Store — `frontend/src/core/store/useJobStore.ts`

Remove `description: job.description ?? null` from the `submitFeedbackRequest` payload in `submitFeedback`:

```typescript
await submitFeedbackRequest({
  job_title: job.title,
  company: job.company,
  action,
  reason,
  job_id: job.id,
});
```

### 8. Frontend Component — `frontend/src/components/ProfileView.tsx`

Remove the `description` render block from `DecisionLogCard`:

```tsx
// REMOVE entirely:
{entry.description && (
  <p className="text-xs text-slate-400 italic">
    {entry.description}
  </p>
)}
```

---

## Tests to Update

### `tests/unit/test_decision_log.py`

- **Delete** `test_decision_log_description_optional` — tests a field that no longer exists.
- **Delete** `test_decision_log_description_stored` — tests a field that no longer exists.
- **Update** `test_decision_log_serializes_correctly` — remove `description` from the `DecisionLog(...)` constructor call and remove the `assert dumped["description"] == ...` assertion.

### `tests/integration/test_feedback_route.py`

- **Update** `test_post_feedback_stores_decision_log` — remove `"description": "A Python role building internal tooling."` from the POST JSON body and remove `assert entry.description == ...`.
- **Update** `test_post_feedback_without_reason` — remove `assert items[0].value["description"] is None`.

---

## Explicit Constraints & Warnings

- **Do NOT remove `reason`.** It is user-authored and is the entire point of the feedback loop.
- **`description` appears in `app/agent/schemas.py` (`JobListing`) and `app/agent/job_search/` — do NOT touch those.** The word "description" exists in job listing schemas (e.g. `JobListing.description`). Only remove it from `DecisionLog` and `FeedbackRequest`.
- **`_format_decisions_summary` is the only node that reads `DecisionLog` for the prompt.** `fetch_profile` in `main/nodes.py` already reconstructs via `DecisionLog(**item.value).model_dump()` — the Pydantic change propagates automatically.
- **Runtime `KeyError` risk on `SYSTEM_PROMPT.format()`.** Step 5b renames the template variable from `{decisions_summary}` to `{feedback_block}`. This rename must be applied to BOTH `app/agent/main/prompts.py` (the template) AND `app/agent/main/nodes.py` (the `.format()` call) atomically. If only one file is updated, `str.format()` raises `KeyError` at runtime — not caught by mypy or pytest unless a test exercises `main_chatbot`. Verify both files are updated before testing.
- **Frontend: apply type changes (step 6) before store changes (step 7).** Updating `FeedbackRequest` type first ensures TypeScript catches any remaining `description` references in the store code.

---

## Acceptance Criteria

- **[Automated]** `pytest` passes. The two deleted test functions are gone; the two updated ones pass without referencing `description`.
- **[Automated]** `mypy .` passes — no `description` attribute access on `DecisionLog` or `FeedbackRequest`.
- **[Automated]** Frontend: `npm run type-check` passes — no `description` field access on `DecisionLogEntry` or `FeedbackRequest`.
- **[Automated]** Frontend: `useJobStore.test.ts` updated — `submitFeedbackRequest` mock call no longer expects a `description` key.
- **[Manual]** Click "Pass" on a job, enter a reason, submit. Check Network tab — `POST /api/feedback` body must contain only `job_title`, `company`, `action`, `reason`, `job_id`. No `description` key.
- **[Manual]** Open the Profile panel → Passed Jobs Feedback. Each entry shows title, company, date, and reason (if provided). No AI summary text beneath the title.
- **[Manual]** On a fresh session (no decisions yet), check the system prompt in logs. The `RECENT USER FEEDBACK` heading must be **absent entirely** — not present with a "No feedback history yet." placeholder.
- **[Manual]** After passing a job with a reason, check the system prompt. The `RECENT USER FEEDBACK` block must now appear and show `PASS "Title" at Company: "reason"` — no long job description text.
