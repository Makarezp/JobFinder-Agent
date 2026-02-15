import logging
from typing import Annotated, Any, cast

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore
from langsmith import traceable

from app.agent.constants import (
    FINAL_ANSWER_TOOL_NAME,
    JOB_SPECIALIST_NODE,
    MAIN_TOOLS_NODE,
    MESSAGES_KEY,
)
from app.agent.main.prompts import SYSTEM_PROMPT
from app.agent.main.tools import main_tools
from app.agent.memory_schema import Preference, UserProfile
from app.agent.state import AgentState
from app.core.config import settings

logger = logging.getLogger(__name__)

# --- LLM initialization ---
llm = ChatGoogleGenerativeAI(
    model=settings.GEMINI_MODEL_NAME,
    temperature=0,
    google_api_key=settings.GEMINI_API_KEY,
)

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
        # cv is now just a string
        parts.append(f"CV Summary:\n{cv}")

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
def fetch_profile(state: AgentState, config: RunnableConfig, store: Annotated[BaseStore, InjectedStore]) -> dict[str, Any]:
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


# --- Routing: main agent ---
def route_main(state: AgentState) -> str:
    """Route main agent output: tool calls, final_answer, or end."""
    messages = cast(list[BaseMessage], state.get(MESSAGES_KEY, []))
    ai_message = messages[-1] if messages else None

    if isinstance(ai_message, AIMessage) and hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
        first_tool_call = ai_message.tool_calls[0]
        name = first_tool_call["name"]
        if name == FINAL_ANSWER_TOOL_NAME:
            return str(END)
        if name == "job_specialist_tool":
            return JOB_SPECIALIST_NODE
        return MAIN_TOOLS_NODE
    return str(END)
