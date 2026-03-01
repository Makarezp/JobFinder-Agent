# [DONE] Ticket 001: Simplify Preference Schema — Replace `key`/`value`/`category` with `label`

## Overview

The current `Preference` schema has three problems: `value` is a raw Python type (bool, int, list) that renders as `"True"` or `"100000"` in the UI with no context; `category` (hard/soft) is never acted upon deterministically and adds unnecessary LLM decision burden; and `key` duplicates the store's own identity mechanism. This ticket replaces `value` + `category` with a single human-readable `label: str` field, giving the LLM one job: write a display-ready sentence. `sentiment` is retained as it does real work (UI split + LLM signal).

**Before:** `Preference(key="min_salary", value=100000, category="hard", sentiment="positive")`
**After:** `Preference(key="min_salary", label="Min salary £100k", sentiment="positive")`

---

## Touch Points (all five must be updated atomically)

> **No backwards compatibility required.** Clear the store/database before testing. Any stale entries from the old schema can be ignored.

1. `app/agent/memory_schema.py` — schema definition
2. `app/tools/memory.py` — `save_preference` tool (write path)
3. `app/agent/main/nodes.py` — `_format_preferences_summary` + `fetch_profile` (read path)
4. `app/services/profile_service.py` — `get_profile_data` (API serialisation)
5. `frontend/src/core/types/api.ts` + `frontend/src/components/ProfileView.tsx` — frontend type + render

---

## Implementation Steps

### 1. Backend Schema — `app/agent/memory_schema.py`

Replace the `Preference` model:

```python
# REMOVE:
key: str
value: Any
category: Literal["hard", "soft"]
sentiment: Literal["positive", "negative"]

# REPLACE WITH:
key: str = Field(..., description="Machine identifier used as store key and for delete routing, e.g. 'min_salary', 'remote'")
label: str = Field(..., description="Human-readable display sentence, e.g. 'Min salary £100k', 'Remote only', 'No agencies'")
sentiment: Literal["positive", "negative"] = Field("positive", description="'positive' = wants it, 'negative' = wants to avoid it")
```

### 2. Tool Write Path — `app/tools/memory.py`

Update `save_preference` signature and docstring. The `value` and `category` parameters are **removed**. `label` is added.

```python
@tool
async def save_preference(
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
    key: Annotated[str, "A short machine identifier for this preference, e.g. 'min_salary', 'remote', 'tech_stack'. Used for deduplication and deletion."],
    label: Annotated[str, "A human-readable sentence describing the preference, e.g. 'Min salary £100k', 'Remote only', 'No agencies'."],
    sentiment: Annotated[Literal["positive", "negative"], "Use 'positive' when user wants something, 'negative' when they want to avoid it."] = "positive",
) -> str:
    """
    Save a user preference or constraint.
    Example: User says "I only want remote jobs" → save_preference(key="remote", label="Remote only", sentiment="positive")
    Example: User says "No agencies" → save_preference(key="agencies", label="No agencies", sentiment="negative")
    Example: User says "Min £80k salary" → save_preference(key="min_salary", label="Min salary £80k", sentiment="positive")
    """
```

Internally, build `Preference(key=key, label=label, sentiment=sentiment)` and call `store.aput`.

### 3. Read Path — `app/agent/main/nodes.py`

Update `_format_preferences_summary` to use `label` instead of `value`/`key`:

```python
def _format_preferences_summary(preferences: dict[str, Any] | None) -> str:
    if not preferences:
        return "No preferences set yet."
    lines: list[str] = []
    for pref_data in preferences.values():
        if isinstance(pref_data, dict):
            sentiment = pref_data.get("sentiment", "positive")
            label = pref_data.get("label", "?")
            prefix = "WANT" if sentiment == "positive" else "AVOID"
            lines.append(f"- [{prefix}] {label}")
    return "\n".join(lines) if lines else "No preferences set yet."
```

No changes needed to `fetch_profile` — it already calls `Preference(**item.value)` and dumps; the Pydantic model change handles the rest.

### 4. API Serialisation — `app/services/profile_service.py`

`get_profile_data` already calls `Preference(**item.value).model_dump()`. No logic changes required — the schema change propagates automatically via Pydantic.

### 5. Frontend — `frontend/src/core/types/api.ts`

```typescript
// REMOVE:
export interface Preference {
  key: string;
  value: string | number | boolean | string[];
  category: "hard" | "soft";
  sentiment: "positive" | "negative";
}

// REPLACE WITH:
export interface Preference {
  key: string;
  label: string;
  sentiment: "positive" | "negative";
}
```

### 6. Frontend — `frontend/src/components/ProfileView.tsx`

Remove the `renderPreferenceValue` helper entirely — it only existed to handle the union type of `value`.

In `PreferencesCard`, replace `{renderPreferenceValue(pref.value)}` with `{pref.label}` directly.

---

## Explicit Constraints & Warnings

- **Do NOT bypass Pydantic.** All store reads must go through `Preference(**item.value)`. Do not read raw dicts into the system prompt.
- **Do NOT change `key` semantics.** The `key` field is the store item key used for deduplication (`store.aput(namespace, key, ...)`) and as the argument to `delete_preference`. It must remain a short machine token (no spaces, no punctuation). The `label` is separate.
- **Do NOT update `delete_preference`.** It operates on `key` only and is unaffected by this change.
- **No migration required.** Clear the store before testing. Stale entries from the old schema do not need to be handled.
- **Tool docstring is load-bearing.** The LLM reads the `save_preference` docstring to understand how to call it. If the docstring still references `value` or `category`, the LLM will hallucinate those parameters. The docstring examples in step 2 are mandatory.
- **Onboarding tools list.** `save_preference` is imported in both `app/agent/onboarding/tools.py` and `app/agent/main/tools.py`. The tool function is defined once in `app/tools/memory.py` — updating it there propagates to both. Do not duplicate the definition.
- **`[WANT]`/`[AVOID]` prefix format is load-bearing.** The `_format_preferences_summary` output format `- [WANT] label` / `- [AVOID] label` is used by the system prompt for LLM filtering logic. Do not change this prefix format.
- **Frontend delete button MUST send `key`, not `label`.** The `ProfileView.tsx` delete button sends `sendMessage('Remove my preference for "${key}"')`. This must remain the store `key` (e.g. `"min_salary"`), not the display `label` (e.g. `"Min salary £80k"`), because `delete_preference` routes on `key`.
- **Check onboarding prompts for stale examples.** Verify `app/agent/onboarding/prompts.py` does not contain `save_preference` examples referencing `value` or `category`. If it does, update them — the LLM will hallucinate old parameters during onboarding.
- **Testing requires a fresh backend process AND fresh thread_id.** Gemini may cache tool schemas within a session. Do not test against a running session that previously used the old `save_preference` signature.

---

## Acceptance Criteria

- **[Automated]** `pytest` passes. Update any test that constructs a `Preference` with `value=` or `category=` — replace with `label=`.
- **[Automated]** `mypy .` passes with no new errors on `memory_schema.py`, `memory.py`, `nodes.py`, and `profile_service.py`.
- **[Automated]** Frontend: `npm run type-check` passes with no errors on `api.ts` or `ProfileView.tsx`.
- **[Automated]** Frontend: existing `ProfileView.test.tsx` updated to pass `label` instead of `value` in mock preference fixtures.
- **[Manual]** Start a fresh session. Tell the agent "I only want remote jobs, minimum £80k, no Java." Verify three `save_preference` tool calls fire with `key`, `label`, and `sentiment` — no `value` or `category` in the payload.
- **[Manual]** Open the Profile panel. Under "Looking For", verify preferences render as human sentences (e.g. "Remote only", "Min salary £80k") not raw values ("True", "80000").
- **[Manual]** Hover a preference, click `×`. Verify the agent's `delete_preference` tool fires with the correct `key`.
