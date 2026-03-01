# [DONE] Ticket 004: LLM filters job results by CV fit and preferences before calling `final_answer`

## Overview

Currently the LLM passes all jobs returned by `job_specialist_tool` directly into `final_answer.jobs` with no filtering. The system prompt instructs it to "populate `jobs` with the structured job data returned by the specialist" — a pure pass-through. This ticket updates the system prompt to make the LLM an active filter using two signals it already has in context: the user's **CV** (seniority, tech stack, domain) and their **active preferences** (explicit wants and avoids). A job must pass both to be included.

**Prerequisite:** The `_format_preferences_summary` function must already output preferences in `- [WANT] label` / `- [AVOID] label` format. If preferences still use the old `(hard)` / `(soft)` format, do not implement this ticket — the filtering instructions below depend on `[WANT]` / `[AVOID]` prefixes.

---

## Touch Points

1. `app/agent/main/prompts.py` — system prompt only

---

## Implementation Steps

### 1. Replace "Present Results" instruction — `app/agent/main/prompts.py`

The current instruction:

```
3.  **Present Results:**
    *   **YOU MUST** call the `final_answer` tool to present results.
    *   Populate `text_response` with a helpful, conversational summary.
    *   Populate `jobs` with the structured job data returned by the specialist.
    *   For each job, write a concise 2-3 sentence `description` summarizing why it
        matches the user. Ensure `apply_link` is included exactly as returned.
```

Replace with:

```
3.  **Filter & Present Results:**
    *   Before calling `final_answer`, evaluate each job against two lenses:

    *   **Lens 1 — CV Fit.** Using the USER PROFILE above (seniority, tech stack,
        domain, experience), assess whether the role is a genuine match.
        Exclude roles that are a clear mismatch:
        - Wrong seniority (e.g. junior role for a senior engineer)
        - Mismatched tech stack (e.g. .NET role for a Python specialist with no .NET experience)
        - Unrelated domain when the user has a clear specialisation
        Do not exclude a job solely because its description is truncated — if the
        snippet does not reveal a clear mismatch, keep it.
        If the user profile contains no CV or skills information, skip this lens
        entirely — do not infer or assume the user's background.

    *   **Lens 2 — Preferences.**
        - `[AVOID]` preferences are hard exclusions. Drop any job that clearly
          matches one (e.g. if [AVOID] "No Java", exclude jobs whose title or
          description mentions Java). If you are uncertain whether a job matches
          an AVOID preference (e.g. unclear if a company is an agency vs. a direct
          employer), include the job but flag your uncertainty in the `description`
          — let the user decide.
        - `[WANT]` preferences are positive signals. Prefer jobs that match them,
          but do not exclude a job solely for lacking one.

    *   **YOU MUST** call the `final_answer` tool to present results.
    *   Populate `jobs` only with jobs that passed both lenses. If all jobs are
        filtered out, populate `jobs` with an empty list.
    *   Populate `text_response` with a helpful, conversational summary. If jobs
        were excluded, briefly note why (e.g. "I filtered out 2 junior roles and
        1 that required Java").
    *   For each included job, write a concise 2-3 sentence `description`
        explaining why it matches the user's profile and preferences.
        Ensure `apply_link` is included exactly as returned.
```

---

## Explicit Constraints & Warnings

- **Prerequisite: `[WANT]`/`[AVOID]` prefix format.** Before implementing, verify that `_format_preferences_summary` in `app/agent/main/nodes.py` outputs preferences as `- [WANT] label` / `- [AVOID] label`. If preferences still use `(hard)` / `(soft)` format, the filtering instructions will not work. Do not implement against the old format.
- **Prerequisite: `DecisionLog.description` should be removed first.** The `description` field in `final_answer` jobs is written by the LLM. If `DecisionLog` still stores `description` and feeds it back into the system prompt, the enhanced filtering-justification descriptions will create worse circular feedback. Verify that `DecisionLog` no longer has a `description` field before implementing.
- **CV fit is inference, not keyword matching.** The LLM must reason about fit from `cv_summary`, not just scan for exact keyword matches. A Python engineer who has never mentioned .NET should not receive .NET roles even if `.NET` isn't in their `[AVOID]` list.
- **AVOID = hard exclusion, WANT = soft signal.** Do not instruct the LLM to exclude jobs for failing to match a `[WANT]` preference — that would over-filter and produce empty results for nuanced preferences like "I like startups."
- **Uncertainty defers to the user.** When the LLM is unsure whether a job matches an AVOID preference, it must include the job and flag uncertainty — not silently filter. This is embedded in the Lens 2 instruction.
- **No CV uploaded = no CV fit filtering.** If `cv_summary` is null (user hasn't uploaded a CV), the LLM has no basis for CV fit assessment and must skip Lens 1, applying only Lens 2. This is embedded in the Lens 1 instruction.
- **Empty `jobs` list is valid.** If all results are filtered, `final_answer(jobs=[])` is the correct outcome. The LLM should explain what was filtered and may retry with a different query (within the 3-attempt limit).
- **Do not change the `final_answer` tool schema.** `jobs: list[JobListing] | None` already accepts an empty list. No backend changes required.
- **Prompt changes are not type-checked.** Manual verification is the only gate. The acceptance criteria below are therefore critical.

---

## Acceptance Criteria

- **[Automated]** `pytest` passes — no backend code changes so no test updates required.
- **[Manual]** Upload a CV for a senior Python engineer. Trigger a search that returns junior Python roles and senior .NET roles. Verify junior roles and .NET roles are excluded from `final_answer.jobs` and `text_response` explains the exclusions.
- **[Manual]** Set an `[AVOID]` preference for "Java". Trigger a job search that returns Java roles. Verify the LLM's `final_answer.jobs` does not include those roles and `text_response` mentions they were filtered.
- **[Manual]** Set a `[WANT]` preference for "startups". Trigger a job search. Verify the LLM does not exclude non-startup jobs entirely — it should still include relevant roles that don't explicitly mention startups.
- **[Manual]** Trigger a search where all results are filtered. Verify `final_answer.jobs` is empty, `text_response` explains what was filtered, and the agent does not claim success.
- **[Manual]** Trigger a search with no CV and no preferences. Verify all returned jobs appear in `final_answer.jobs` — no regression on the blank-slate path.
