# [DONE] Ticket 003: Trim message history to 40k token cap in `main_chatbot`

## Overview

Each job search appends a `ToolMessage` of ~3,750 tokens (10 jobs × 375 tokens) to the message history permanently. After ~10 searches this exceeds 40k tokens, causing attention degradation — the LLM starts losing track of instructions and may reference stale results. This ticket applies LangChain's `trim_messages` inside `main_chatbot` to cap the message history at 40k tokens before invoking the LLM, keeping context lean without losing the persistent memory that lives in the system prompt (profile, preferences, decisions).

---

## Touch Points

1. `app/agent/main/nodes.py` — `main_chatbot` node only

---

## Implementation Steps

### 1. Apply `trim_messages` inside `main_chatbot` — `app/agent/main/nodes.py`

Import and apply trimming before the LLM invocation. Use `strategy="last"` to keep the most recent messages (the LLM needs recent context, not old job blobs):

```python
from langchain_core.messages import trim_messages


def main_chatbot(state: AgentState) -> dict[str, list[BaseMessage]]:
    messages = state[MESSAGES_KEY]

    trimmed_messages = trim_messages(
        messages,
        max_tokens=160_000,  # ~40k tokens × ~4 chars/token
        strategy="last",
        token_counter=len,  # character count — free, local, no API call
        include_system=False,  # system prompt is added separately, do not count it here
        allow_partial=False,  # never split a message mid-content
        start_on="human",  # always start trimmed history on a HumanMessage
    )

    system_messages = [SystemMessage(content=formatted_prompt)]
    all_messages = system_messages + trimmed_messages
    response = main_llm.invoke(all_messages)
    ...
```

**Key parameter rationale:**
- `max_tokens=160_000` — ~40k tokens × ~4 chars/token. Uses character count as a free approximation. The ~5% imprecision is irrelevant for trimming — we're deciding which old messages to drop, not billing
- `token_counter=len` — counts characters per message. No API calls, no latency, runs in microseconds. Do NOT use the LLM as a token counter — `ChatGoogleGenerativeAI.get_num_tokens()` may call the Gemini `countTokens` API (adding ~200-500ms per message) or raise `NotImplementedError` depending on version. Also, `main_llm` is a `RunnableBinding` (tool-bound wrapper), not a raw LLM — it does not expose `get_num_tokens`
- `strategy="last"` — drops oldest messages first, preserving the most recent conversational context
- `include_system=False` — system prompt is prepended separately and must not be double-counted
- `start_on="human"` — ensures trimmed history never starts with a dangling `AIMessage` or `ToolMessage` which would confuse the LLM
- `allow_partial=False` — never truncates a message mid-way; drops the whole message instead

### 2. No other changes required

- `AgentState.messages` is **not modified** — trimming is applied only at invocation time, the full history is preserved in the checkpointer for continuity
- `fetch_profile`, `SYSTEM_PROMPT`, routing logic — all untouched
- Profile, preferences, and decisions survive trimming because they live in the store and are re-injected via the system prompt on every turn, not in the message history

---

## Explicit Constraints & Warnings

- **Do NOT mutate `state[MESSAGES_KEY]` directly.** Apply `trim_messages` to a local variable only. The full history must remain in the checkpointer.
- **Do NOT trim in the onboarding path.** The onboarding chatbot (`onboarding_chatbot` node) does not accumulate job blobs and does not need trimming. Only `main_chatbot` is in scope.
- **Use `token_counter=len`, NOT the LLM.** `main_llm` is a `RunnableBinding` (tool-bound wrapper) that does not expose `get_num_tokens`. Even the raw `llm` object (`ChatGoogleGenerativeAI`) may call Gemini's `countTokens` API — adding latency on every turn — or raise `NotImplementedError`. Character-count approximation via `len` is free and accurate enough for trimming.
- **`start_on="human"` is critical.** Without it, a trimmed history could begin with a `ToolMessage` referencing a tool call that no longer exists in the trimmed window, which causes Gemini to error.
- **Orphaned tool-call pairs at trim boundaries.** `start_on="human"` ensures the window starts on a `HumanMessage`, but does not guarantee that every `AIMessage(tool_calls=[...])` within the window has a matching `ToolMessage`. If an `AIMessage` with `tool_calls` survives but its `ToolMessage` was trimmed, Gemini returns `400 Bad Request: tool call id not found`. In practice this is unlikely because `HumanMessage` typically follows a complete tool cycle, but be aware of this edge case during testing.
- **Log when trimming activates.** Add a log line when `len(trimmed_messages) < len(messages)` to make the manual acceptance criterion verifiable:
  ```python
  if len(trimmed_messages) < len(messages):
      logger.info("Messages trimmed", original=len(messages), trimmed=len(trimmed_messages))
  ```

---

## Acceptance Criteria

- **[Automated]** `pytest` passes — no existing tests broken. No new unit tests required for the trimming logic itself (`trim_messages` is a LangChain built-in, not custom code). The real validation is behavioral and covered by manual criteria below.
- **[Automated]** `mypy .` passes with no new errors.
- **[Manual]** Simulate 15 consecutive job searches in one session. Check logs — the token count passed to the LLM must not exceed ~42k tokens (40k history + ~2k system prompt).
- **[Manual]** After trimming kicks in, verify the LLM still responds correctly to a new job search request — it should not reference jobs from early in the session that have been trimmed.
- **[Manual]** Verify preferences and profile are still correctly applied after trimming — they survive because they come from the system prompt, not the message history.
