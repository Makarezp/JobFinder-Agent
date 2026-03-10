import asyncio
from typing import Annotated, Any

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, trim_messages
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore
from langsmith import traceable

from app.agent.constants import (
    DISCOVERY_JOB_SPECIALIST_NODE,
    DISCOVERY_TOOLS_NODE,
    MAX_SEARCH_ATTEMPTS,
)
from app.agent.discovery.state import DiscoveryAgentState
from app.agent.main.prompts import SYSTEM_PROMPT
from app.agent.main.tools import main_tools
from app.agent.memory_schema import DecisionLog, Preference, UserProfile
from app.core.llm import get_active_model
from app.core.node_logging_utils import log_node_completed

logger = structlog.get_logger(__name__)

# --- LLM initialization ---
base_llm: BaseChatModel = get_active_model(temperature=0)
main_llm = base_llm.bind_tools(main_tools)


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
        parts.append(f"CV Summary:\n{cv}")

    return "\n".join(parts) if parts else "No profile information available yet."


def _format_decisions_summary(decisions: list[dict[str, Any]]) -> str | None:
    """Format decision log into a readable summary for the system prompt.
    Returns None when empty so the caller can omit the section entirely.
    """
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


def _format_preferences_summary(preferences: dict[str, Any] | None) -> str:
    """Format preferences dict into a readable summary for the system prompt."""
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


# --- Node: fetch_profile (main agent entry) ---
async def fetch_profile(state: DiscoveryAgentState, config: RunnableConfig, store: Annotated[BaseStore, InjectedStore]) -> dict[str, Any]:
    """
    Read user profile and preferences from Store and inject into state.
    Used as the entry point for the main agent path.
    """
    logger.info("Node Started: fetch_profile")
    user_id = config.get("configurable", {}).get("user_id", "default_user")

    namespace_profile = (user_id, "profile")
    namespace_prefs = (user_id, "preferences")
    namespace_decisions = (user_id, "decisions")

    profile_item, prefs_items, decisions_items = await asyncio.gather(
        store.aget(namespace_profile, "data"),
        store.asearch(namespace_prefs),
        store.asearch(namespace_decisions),
    )

    profile = UserProfile(**profile_item.value) if profile_item else UserProfile()
    profile_dict = profile.model_dump()

    preferences: dict[str, Any] = {}
    for item in prefs_items:
        if item.value:
            try:
                pref = Preference(**item.value)
                preferences[item.key] = pref.model_dump()
            except Exception:
                logger.warning("Skipping invalid preference", key=item.key)
    recent_decisions = sorted(
        [DecisionLog(**item.value).model_dump() for item in decisions_items if item.value],
        key=lambda d: d["timestamp"],
        reverse=True,
    )[:10]

    logger.info(
        "Node Completed: fetch_profile",
        profile=profile_dict,
        pref_count=len(preferences),
        decisions_count=len(recent_decisions),
    )

    patch: dict[str, Any] = {
        "user_profile": profile_dict,
        "preferences": preferences,
        "recent_decisions": recent_decisions,
    }

    return patch


# --- Node: main_chatbot ---
@traceable
def main_chatbot(state: DiscoveryAgentState) -> dict[str, list[BaseMessage]]:
    """Main job-hunting agent node — uses structured profile and preferences."""
    logger.info("Node Started: main_chatbot")

    messages = state["messages"]

    profile = state.get("user_profile")
    preferences = state.get("preferences")
    decisions = state.get("recent_decisions", [])

    decisions_summary = _format_decisions_summary(decisions)
    feedback_block = (
        f"\n**RECENT USER FEEDBACK:**\n{decisions_summary}\n"
        "Use this history to avoid suggesting similar jobs. "
        "Do not mention this feedback log explicitly unless the user asks about it.\n"
        if decisions_summary
        else ""
    )

    formatted_prompt = SYSTEM_PROMPT.format(
        name=profile.get("name", "User") if profile else "User",
        role=profile.get("role", "Job Seeker") if profile else "Job Seeker",
        profile_summary=_format_profile_summary(profile),
        preferences_summary=_format_preferences_summary(preferences),
        feedback_block=feedback_block,
        max_search_attempts=MAX_SEARCH_ATTEMPTS,
    )

    # Trim history to ~40k tokens (160k chars @ ~4 chars/token) before invoking.
    # Uses character count (token_counter=len) — free, local, zero latency.
    # Does NOT mutate state; the full history is preserved in the checkpointer.
    trimmed_messages = trim_messages(
        messages,
        max_tokens=160_000,
        strategy="last",
        token_counter=len,
        include_system=False,
        allow_partial=False,
        start_on="human",
    )
    if len(trimmed_messages) < len(messages):
        logger.info(
            "Messages trimmed before LLM invocation",
            original=len(messages),
            trimmed=len(trimmed_messages),
        )

    system_messages = [SystemMessage(content=formatted_prompt)]
    all_messages = system_messages + trimmed_messages
    try:
        response = main_llm.invoke(all_messages)
        logger.debug("LLM Response", content=response.content)
        for tc in response.tool_calls:
            logger.info("LLM Intent: Tool Selected", tool_name=tc["name"], tool_args=tc["args"])
        for itc in response.invalid_tool_calls:
            logger.warning("LLM Intent: Invalid Tool Selected", tool_name=itc.get("name"), tool_args=itc.get("args"), error=itc.get("error"))
        log_node_completed("main_chatbot", response)
        return {"messages": [response]}
    except Exception as e:
        logger.error("LLM Execution Failed in main_chatbot", error=str(e))
        fallback_msg = AIMessage(
            content=(
                "I'm sorry, I'm having trouble connecting to my processing network "
                "right now due to high demand. Could you please try your request again in a moment?"
            )
        )
        return {"messages": [fallback_msg]}


# --- Routing: main agent ---
def route_main(state: DiscoveryAgentState) -> str:
    """Route main agent output: tool calls, final_answer, or end."""
    messages = state["messages"]
    ai_message = messages[-1] if messages else None

    if not (isinstance(ai_message, AIMessage) and ai_message.tool_calls):
        return str(END)

    tool_names = {tc["name"] for tc in ai_message.tool_calls}

    if "job_specialist_tool" in tool_names:
        return DISCOVERY_JOB_SPECIALIST_NODE

    return DISCOVERY_TOOLS_NODE
