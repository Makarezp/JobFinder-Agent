import asyncio
from typing import Annotated, Any, cast

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage, trim_messages
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
    MAX_SEARCH_ATTEMPTS,
    MESSAGES_KEY,
    ONBOARDING_COMPLETE_SIGNAL,
)
from app.agent.discovery.state import DiscoveryAgentState
from app.agent.main.prompts import SYSTEM_PROMPT
from app.agent.main.tools import main_tools
from app.agent.memory_schema import DecisionLog, Preference, UserProfile
from app.core.config import settings
from app.core.node_logging_utils import log_node_completed

logger = structlog.get_logger(__name__)

# --- LLM initialization ---
llm = ChatGoogleGenerativeAI(
    model=settings.GEMINI_MODEL_NAME,
    temperature=0,
    google_api_key=settings.GEMINI_API_KEY,
)

main_llm = llm.bind_tools(main_tools)


# --- Helper: detect onboarding handoff ---
def _is_fresh_onboarding_handoff(messages: list[BaseMessage]) -> bool:
    """
    Returns True when the most recent message in state is the ToolMessage
    emitted by finalize_profile (content contains "Onboarding complete").
    This is the signal that the graph has just transitioned from onboarding.

    NOTE: This relies on no intermediate node existing between
    ONBOARDING_TOOLS_NODE and FETCH_PROFILE_NODE in graph.py. If a node
    is ever inserted there, this detection will break silently.
    """
    if not messages:
        return False
    last = messages[-1]
    return isinstance(last, ToolMessage) and ONBOARDING_COMPLETE_SIGNAL in str(last.content)


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


# --- Helper: strip onboarding history from main agent context ---
def _strip_onboarding_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Remove all messages predating the onboarding handoff from the context window.
    The handoff boundary is the first HumanMessage starting with '[SYSTEM TRIGGER]'.
    If no such marker exists, the full list is returned unchanged.
    """
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage) and str(msg.content).startswith("[SYSTEM TRIGGER]"):
            return messages[i:]
    return messages


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

    current_messages: list[BaseMessage] = state.get(MESSAGES_KEY, [])  # type: ignore
    if _is_fresh_onboarding_handoff(current_messages):
        trigger = HumanMessage(
            content=(
                "[SYSTEM TRIGGER] Onboarding is now complete. "
                "The user's profile and preferences have been loaded above. "
                "Begin searching for matching jobs immediately using job_specialist_tool. "
                "Do NOT greet the user or ask clarifying questions — go straight to searching."
            )
        )
        patch["messages"] = [trigger]
        logger.info("Onboarding handoff detected: injecting search trigger into messages")

    return patch


# --- Node: main_chatbot ---
@traceable
def main_chatbot(state: DiscoveryAgentState) -> dict[str, list[BaseMessage]]:
    """Main job-hunting agent node — uses structured profile and preferences."""
    logger.info("Node Started: main_chatbot")

    messages = state[MESSAGES_KEY]  # type: ignore

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

    # Strip onboarding history before trimming — reduces token count significantly
    # for post-onboarding turns. Full history remains in the checkpointer.
    messages = _strip_onboarding_messages(messages)

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
    messages = cast(list[BaseMessage], state.get(MESSAGES_KEY, []))
    ai_message = messages[-1] if messages else None

    if not (isinstance(ai_message, AIMessage) and ai_message.tool_calls):
        return str(END)

    tool_names = {tc["name"] for tc in ai_message.tool_calls}

    if FINAL_ANSWER_TOOL_NAME in tool_names:
        return str(END)

    if "job_specialist_tool" in tool_names:
        if state.get("search_attempts", 0) >= MAX_SEARCH_ATTEMPTS:
            logger.warning("Loop protection: max search attempts reached, forcing END")
            return str(END)
        return JOB_SPECIALIST_NODE

    return MAIN_TOOLS_NODE
