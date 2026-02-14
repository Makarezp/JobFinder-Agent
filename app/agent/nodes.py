import logging
from typing import Annotated, Any

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import InjectedStore, ToolNode
from langgraph.store.base import BaseStore
from langsmith import traceable

from app.agent.constants import MESSAGES_KEY
from app.agent.memory_schema import Preference, UserProfile
from app.agent.prompts.agent_prompts import SYSTEM_PROMPT
from app.agent.prompts.onboarding_prompts import ONBOARDING_PROMPT
from app.agent.schemas import AgentResponse, JobListing
from app.agent.state import AgentState
from app.core.config import settings
from app.tools.adzuna_api import adzuna_api_search
from app.tools.memory import (
    delete_preference,
    finalize_profile,
    save_preference,
    update_my_profile,
)
from app.tools.scraper import scrape_website

logger = logging.getLogger(__name__)


# --- Tool: final_answer ---
@tool(args_schema=AgentResponse)
def final_answer(text_response: str, jobs: list[JobListing] | None = None) -> str:
    """Present the final response to the user with optional job listings."""
    if jobs is None:
        jobs = []
    return "Final Answer Processed"


# --- LLM initialization ---
llm = ChatGoogleGenerativeAI(
    model=settings.GEMINI_MODEL_NAME,
    temperature=0,
    google_api_key=settings.GEMINI_API_KEY,
)

# Onboarding agent tools (profile building + finalize)
onboarding_tools = [
    update_my_profile,
    save_preference,
    delete_preference,
    finalize_profile,
]
onboarding_llm = llm.bind_tools(onboarding_tools)

# Main agent tools (job hunting + memory)
main_tools = [
    adzuna_api_search,
    scrape_website,
    final_answer,
    update_my_profile,
    save_preference,
    delete_preference,
]
main_llm = llm.bind_tools(main_tools)


# --- Helper: format profile for system prompt ---
def _format_profile_summary(profile: dict[str, Any] | None) -> str:
    """Format user profile dict into a readable summary for the system prompt."""
    if not profile:
        return "No profile information available yet."

    parts: list[str] = []
    if profile.get("name"):
        parts.append(f"Name: {profile['name']}")
    if profile.get("role"):
        parts.append(f"Role: {profile['role']}")

    cv = profile.get("cv_summary")
    if cv:
        parts.append(f"Summary: {cv.get('professional_summary', 'N/A')}")
        parts.append(f"Seniority: {cv.get('seniority_level', 'N/A')}")
        parts.append(f"Experience: {cv.get('years_of_experience', 'N/A')} years")
        parts.append(f"Domain: {cv.get('primary_domain', 'N/A')}")
        skills = cv.get("skills", {})
        if skills.get("primary"):
            parts.append(f"Primary Skills: {', '.join(skills['primary'])}")
        if skills.get("secondary"):
            parts.append(f"Secondary Skills: {', '.join(skills['secondary'])}")
        if skills.get("tools"):
            parts.append(f"Tools: {', '.join(skills['tools'])}")

    return "\n".join(parts) if parts else "No profile information available yet."


def _format_preferences_summary(preferences: dict[str, Any] | None) -> str:
    """Format preferences dict into a readable summary for the system prompt."""
    if not preferences:
        return "No preferences set yet."

    lines: list[str] = []
    for _key, pref_data in preferences.items():
        if isinstance(pref_data, dict):
            cat = pref_data.get("category", "soft")
            lines.append(f"- {pref_data.get('key', _key)}: {pref_data.get('value', '?')} ({cat})")
        else:
            lines.append(f"- {_key}: {pref_data}")

    return "\n".join(lines) if lines else "No preferences set yet."


# --- Node: fetch_profile (main agent entry) ---
def fetch_profile(
    state: AgentState, config: RunnableConfig, store: Annotated[BaseStore, InjectedStore]
) -> dict[str, Any]:
    """
    Read user profile and preferences from Store and inject into state.
    Used as the entry point for the main agent path.
    """
    user_id = config.get("configurable", {}).get("user_id", "default_user")

    # Fetch Profile
    namespace_profile = (user_id, "profile")
    profile_item = store.get(namespace_profile, "data")
    profile = UserProfile(**profile_item.value) if profile_item else UserProfile()
    profile_dict = profile.model_dump()

    # Fetch Preferences
    namespace_prefs = (user_id, "preferences")
    prefs_items = store.search(namespace_prefs)

    preferences: dict[str, Any] = {}
    for item in prefs_items:
        if item.value:
            try:
                pref = Preference(**item.value)
                preferences[item.key] = pref.model_dump()
            except Exception:
                logger.warning(f"Skipping invalid preference: {item.key}")

    logger.info(f"Fetched profile: {profile_dict}")

    return {"user_profile": profile_dict, "preferences": preferences}


# --- Node: onboarding_chatbot ---
@traceable
def onboarding_chatbot(state: AgentState) -> dict[str, list[BaseMessage]]:
    """Onboarding agent node — builds user profile through conversation."""
    logger.info("Invoking onboarding_chatbot node")

    messages = state[MESSAGES_KEY]  # type: ignore

    system_parts = [ONBOARDING_PROMPT]

    # If CV raw text is available, add it as context
    cv_raw = state.get("cv_raw_text")
    if cv_raw:
        system_parts.append(
            f"\n\n**CV TEXT (uploaded by user — analyze this and store structured summary "
            f"via update_my_profile):**\n{cv_raw}"
        )

    system_messages = [SystemMessage(content="\n".join(system_parts))]
    all_messages = system_messages + messages
    return {"messages": [onboarding_llm.invoke(all_messages)]}


# --- Node: main_chatbot ---
@traceable
def main_chatbot(state: AgentState) -> dict[str, list[BaseMessage]]:
    """Main job-hunting agent node — uses structured profile and preferences."""
    logger.info("Invoking main_chatbot node")

    messages = state[MESSAGES_KEY]  # type: ignore

    profile = state.get("user_profile")
    preferences = state.get("preferences")

    formatted_prompt = SYSTEM_PROMPT.format(
        name=profile.get("name", "User") if profile else "User",
        role=profile.get("role", "Job Seeker") if profile else "Job Seeker",
        profile_summary=_format_profile_summary(profile),
        preferences_summary=_format_preferences_summary(preferences),
    )

    system_messages = [SystemMessage(content=formatted_prompt)]
    all_messages = system_messages + messages
    return {"messages": [main_llm.invoke(all_messages)]}


# --- Tool Nodes ---
onboarding_tool_node = ToolNode(tools=onboarding_tools)
main_tool_node = ToolNode(tools=main_tools)
