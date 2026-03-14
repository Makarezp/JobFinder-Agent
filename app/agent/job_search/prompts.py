from typing import Any

from langchain_core.prompts import ChatPromptTemplate

SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a job listing analyst. Your task is to produce a concise, profile-aware analytical description for each job listing.

**USER PROFILE:**
{user_profile}

**USER PREFERENCES:**
{preferences}

**INSTRUCTIONS:**
For each job, produce:
- `job_id`: Echo the `id` from the input exactly.
- `description`: A ~500-character analytical summary covering:
  - **Essence**: What the role is and what the company does.
  - **Conditions**: Salary, location, contract type, remote availability.
  - **Limitations**: Any potential mismatches with the user's profile or preferences. Flag uncertainties rather than making definitive judgements.

**RULES:**
- Produce EXACTLY one summary per input job. Do not skip any.
- If a job's description is truncated or sparse, summarize what is available — do NOT penalize the job.
- If no user profile or CV is available, focus on Essence and Conditions only.
- You are a summarizer, NOT a filter. Do NOT make keep/drop decisions. Describe limitations factually — the user's agent will decide what to present.
- Keep each description close to 500 characters. Do not exceed 700.""",
        ),
        ("human", "{jobs_json}"),
    ]
)


def format_profile_for_summary(profile: dict[str, Any] | None) -> str:
    """Format user profile dict into a string for the summary prompt."""
    if not profile:
        return "No profile information available."

    lines: list[str] = []
    if name := profile.get("name"):
        lines.append(f"Name: {name}")
    if role := profile.get("role"):
        lines.append(f"Role: {role}")
    if cv_summary := profile.get("cv_summary"):
        lines.append(f"CV Summary: {cv_summary}")

    return "\n".join(lines) if lines else "No profile information available."


def format_preferences_for_summary(preferences: dict[str, Any] | None) -> str:
    """Format preferences dict into a [WANT]/[AVOID] string for the summary prompt."""
    if not preferences:
        return "No preferences set."

    lines: list[str] = []
    for pref_data in preferences.values():
        if isinstance(pref_data, dict):
            sentiment = pref_data.get("sentiment", "positive")
            label = pref_data.get("label", "?")
            prefix = "WANT" if sentiment == "positive" else "AVOID"
            lines.append(f"- [{prefix}] {label}")

    return "\n".join(lines) if lines else "No preferences set."
