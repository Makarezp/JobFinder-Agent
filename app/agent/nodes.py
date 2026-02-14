import logging
from typing import Annotated, Any

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import InjectedStore, ToolNode
from langgraph.store.base import BaseStore
from langsmith import traceable

from app.agent.constants import (
    CV_TEXT_KEY,
    MESSAGES_KEY,
)
from app.agent.memory_schema import Preference, UserProfile
from app.agent.prompts.agent_prompts import SYSTEM_PROMPT
from app.agent.schemas import AgentResponse, JobListing
from app.agent.state import AgentState
from app.core.config import settings
from app.tools.adzuna_api import adzuna_api_search
from app.tools.memory import delete_preference, save_preference, update_my_profile
from app.tools.scraper import scrape_website

logger = logging.getLogger(__name__)


@tool(args_schema=AgentResponse)
def final_answer(text_response: str, jobs: list[JobListing] | None = None) -> str:
    """Present the final response to the user with optional job listings."""
    if jobs is None:
        jobs = []
    return "Final Answer Processed"


# Initialize Model
llm = ChatGoogleGenerativeAI(
    model=settings.GEMINI_MODEL_NAME,
    temperature=0,
    google_api_key=settings.GEMINI_API_KEY,
)
tools = [
    adzuna_api_search,
    scrape_website,
    final_answer,
    update_my_profile,
    save_preference,
    delete_preference,
]
llm_with_tools = llm.bind_tools(tools)


# Nodes
def fetch_profile(
    state: AgentState, config: RunnableConfig, store: Annotated[BaseStore, InjectedStore]
) -> dict[str, Any]:
    """
    Read user profile and preferences from Store and inject into state.
    """
    user_id = config.get("configurable", {}).get("user_id", "default_user")

    # Fetch Profile
    namespace_profile = (user_id, "profile")
    profile_item = store.get(namespace_profile, "data")
    profile = UserProfile(**profile_item.value) if profile_item else UserProfile()
    profile_dict = profile.model_dump()

    # Fetch Preferences
    namespace_prefs = (user_id, "preferences")
    # Fetch all preferences in user's namespace.
    prefs_items = store.search(namespace_prefs)

    preferences = {}
    for item in prefs_items:
        # item.key is the preference key, item.value is the dict or model dump
        # We can validate it back to Preference model if needed, but for state injection dict is fine.
        # But let's be safe and validate.
        if item.value:
            try:
                # If it was saved as dict from model_dump
                pref = Preference(**item.value)
                preferences[item.key] = pref.model_dump()
            except Exception:
                logger.warning(f"Skipping invalid preference: {item.key}")

    logger.info(f"Fetched profile: {profile_dict}")

    # Hydrate state from DB
    updates: dict[str, Any] = {"user_profile": profile_dict, "preferences": preferences}

    # If CV exists in DB, ensure it's in the state's main text field
    if profile.cv_text:
        updates[CV_TEXT_KEY] = profile.cv_text

    return updates


@traceable
def chatbot(state: AgentState) -> dict[str, list[BaseMessage]]:
    logger.info("Invoking chatbot node")

    messages = state[MESSAGES_KEY]  # type: ignore

    # Add System Prompt
    messages = state[MESSAGES_KEY]  # type: ignore

    # Dynamic System Prompt
    profile = state.get("user_profile")
    preferences = state.get("preferences")

    # Format the global SYSTEM_PROMPT string if it's a template,
    # OR construct a new one here. For now, we'll assume SYSTEM_PROMPT
    # will be updated to be a function or we format it here.
    # Let's try to format it if it has placeholders, otherwise append context.

    formatted_system_prompt = SYSTEM_PROMPT
    try:
        # Check if SYSTEM_PROMPT is a format string (simple check)
        if "{name}" in SYSTEM_PROMPT or "{role}" in SYSTEM_PROMPT:
            formatted_system_prompt = SYSTEM_PROMPT.format(
                name=profile.get("name", "User") if profile else "User",
                role=profile.get("role", "Job Seeker") if profile else "Job Seeker",
            )
    except Exception:
        logger.warning("Failed to format SYSTEM_PROMPT, using raw.")

    system_messages = [SystemMessage(content=formatted_system_prompt)]

    # Add Preference Context
    if preferences:
        pref_str = "\n".join([f"- {k}: {v}" for k, v in preferences.items()])
        pref_context = f"\n\nUser Preferences (Constraints):\n{pref_str}"
        system_messages.append(SystemMessage(content=pref_context))

    # Add CV Context if available
    if state.get(CV_TEXT_KEY):
        cv_context = f"\n\nUser's CV Content:\n{state[CV_TEXT_KEY]}\n\nUse this to personalize job recommendations."  # type: ignore
        system_messages.append(SystemMessage(content=cv_context))

    messages = system_messages + messages
    return {"messages": [llm_with_tools.invoke(messages)]}


tool_node = ToolNode(tools=tools)
