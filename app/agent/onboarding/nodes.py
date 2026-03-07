from typing import Annotated, Any, cast

import structlog
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore
from langsmith import traceable

from app.agent.constants import (
    FETCH_PROFILE_NODE,
    MESSAGES_KEY,
    ONBOARDING_CHATBOT_NODE,
    ONBOARDING_COMPLETE_SIGNAL,
    ONBOARDING_TOOLS_NODE,
)
from app.agent.onboarding.prompts import ONBOARDING_PROMPT
from app.agent.onboarding.tools import onboarding_tools
from app.agent.profile.state import ProfileAgentState
from app.core.config import settings
from app.core.node_logging_utils import log_node_completed

logger = structlog.get_logger(__name__)

# --- LLM initialization ---
llm = ChatGoogleGenerativeAI(
    model=settings.GEMINI_MODEL_NAME,
    temperature=0,
    google_api_key=settings.GEMINI_API_KEY,
)

onboarding_llm = llm.bind_tools(onboarding_tools)


# --- Node: check_onboarding_status (graph entry) ---
async def check_onboarding_status(state: ProfileAgentState, config: RunnableConfig, store: Annotated[BaseStore, InjectedStore]) -> dict[str, Any]:
    """
    Read onboarding status from Store and hydrate into graph state.
    Runs at graph entry on every invocation to bridge store → state.
    """
    logger.info("Node Started: check_onboarding_status")
    user_id = config.get("configurable", {}).get("user_id", "default_user")
    status_item = await store.aget((user_id, "onboarding"), "status")

    is_complete = False
    if status_item and status_item.value.get("onboarding_complete"):
        is_complete = True

    logger.info("Node Completed: check_onboarding_status", onboarding_complete=is_complete)
    return {"onboarding_complete": is_complete}


# --- Node: onboarding_chatbot ---
@traceable
def onboarding_chatbot(state: ProfileAgentState) -> dict[str, list[BaseMessage]]:
    """Onboarding agent node — builds user profile through conversation."""
    logger.info("Node Started: onboarding_chatbot")

    messages = state[MESSAGES_KEY]  # type: ignore

    system_parts = [ONBOARDING_PROMPT]

    cv_raw = state.get("cv_raw_text")
    if cv_raw:
        system_parts.append(f"\n\n**CV TEXT (uploaded by user — analyze this and store structured summary via update_my_profile):**\n{cv_raw}")

    system_messages = [SystemMessage(content="\n".join(system_parts))]
    all_messages = system_messages + messages
    try:
        response = onboarding_llm.invoke(all_messages)
        logger.debug("LLM Response", content=response.content)
        log_node_completed("onboarding_chatbot", response)
        return {"messages": [response]}
    except Exception as e:
        logger.error("LLM Execution Failed in onboarding_chatbot", error=str(e))
        fallback_msg = AIMessage(
            content=(
                "I'm sorry, but my connection to the AI network is currently "
                "experiencing heavy load. Please give me a second and try your request again."
            )
        )
        return {"messages": [fallback_msg]}


# --- Routing: onboarding agent ---
def route_onboarding(state: ProfileAgentState) -> str:
    """Route onboarding agent output: tool calls or end."""
    messages = cast(list[BaseMessage], state.get(MESSAGES_KEY, []))
    ai_message = messages[-1] if messages else None

    if isinstance(ai_message, AIMessage) and ai_message.tool_calls:
        return ONBOARDING_TOOLS_NODE
    return str(END)


# --- After onboarding tools: check if finalize was called ---
def route_after_onboarding_tools(state: ProfileAgentState) -> str:
    """
    After onboarding tools execute, check if we should continue onboarding
    or hand off to the main agent immediately.
    """
    messages = cast(list[BaseMessage], state.get(MESSAGES_KEY, []))

    for msg in reversed(messages):
        if hasattr(msg, "content") and ONBOARDING_COMPLETE_SIGNAL in str(msg.content):
            return FETCH_PROFILE_NODE
        if isinstance(msg, AIMessage):
            break

    return ONBOARDING_CHATBOT_NODE
