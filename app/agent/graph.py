import logging
from typing import cast

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

from app.agent.constants import (
    FETCH_PROFILE_NODE,
    FINAL_ANSWER_TOOL_NAME,
    MAIN_CHATBOT_NODE,
    MAIN_TOOLS_NODE,
    MESSAGES_KEY,
    ONBOARDING_CHATBOT_NODE,
    ONBOARDING_TOOLS_NODE,
)
from app.agent.nodes import (
    fetch_profile,
    main_chatbot,
    main_tool_node,
    onboarding_chatbot,
    onboarding_tool_node,
)
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


# --- Router: pure conditional, no LLM ---
def router(state: AgentState) -> str:
    """Route to onboarding or main agent based on onboarding status."""
    if state.get("onboarding_complete"):
        return FETCH_PROFILE_NODE
    return ONBOARDING_CHATBOT_NODE


# --- Routing: onboarding agent ---
def route_onboarding(state: AgentState) -> str:
    """Route onboarding agent output: tool calls or end."""
    messages = cast(list[BaseMessage], state.get(MESSAGES_KEY, []))
    ai_message = messages[-1] if messages else None

    if isinstance(ai_message, AIMessage) and hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
        # Check if finalize_profile was called
        for tc in ai_message.tool_calls:
            if tc["name"] == "finalize_profile":
                # Still need to execute the tool, then end
                return ONBOARDING_TOOLS_NODE
        return ONBOARDING_TOOLS_NODE
    return str(END)


# --- Routing: main agent ---
def route_main(state: AgentState) -> str:
    """Route main agent output: tool calls, final_answer, or end."""
    messages = cast(list[BaseMessage], state.get(MESSAGES_KEY, []))
    ai_message = messages[-1] if messages else None

    if isinstance(ai_message, AIMessage) and hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
        first_tool_call = ai_message.tool_calls[0]
        if first_tool_call["name"] == FINAL_ANSWER_TOOL_NAME:
            return str(END)
        return MAIN_TOOLS_NODE
    return str(END)


# --- After onboarding tools: check if finalize was called ---
def route_after_onboarding_tools(state: AgentState) -> str:
    """After onboarding tools execute, check if we should end or continue."""
    messages = cast(list[BaseMessage], state.get(MESSAGES_KEY, []))

    # Look at tool results — if finalize_profile was just executed, end turn
    # The finalize_profile tool returns a specific message
    for msg in reversed(messages):
        if hasattr(msg, "content") and "Onboarding complete" in str(msg.content):
            return str(END)
        # Stop searching after we pass non-tool messages
        if isinstance(msg, AIMessage):
            break

    return ONBOARDING_CHATBOT_NODE


# --- Graph Definition ---
store = InMemoryStore()
graph_builder = StateGraph(AgentState)

# Nodes
graph_builder.add_node(ONBOARDING_CHATBOT_NODE, onboarding_chatbot)
graph_builder.add_node(ONBOARDING_TOOLS_NODE, onboarding_tool_node)
graph_builder.add_node(FETCH_PROFILE_NODE, fetch_profile)
graph_builder.add_node(MAIN_CHATBOT_NODE, main_chatbot)
graph_builder.add_node(MAIN_TOOLS_NODE, main_tool_node)

# Entry: router decides which path
graph_builder.add_conditional_edges(
    START,
    router,
    {FETCH_PROFILE_NODE: FETCH_PROFILE_NODE, ONBOARDING_CHATBOT_NODE: ONBOARDING_CHATBOT_NODE},
)

# Onboarding path
graph_builder.add_conditional_edges(
    ONBOARDING_CHATBOT_NODE,
    route_onboarding,
    {ONBOARDING_TOOLS_NODE: ONBOARDING_TOOLS_NODE, END: END},
)
graph_builder.add_conditional_edges(
    ONBOARDING_TOOLS_NODE,
    route_after_onboarding_tools,
    {ONBOARDING_CHATBOT_NODE: ONBOARDING_CHATBOT_NODE, END: END},
)

# Main agent path
graph_builder.add_edge(FETCH_PROFILE_NODE, MAIN_CHATBOT_NODE)
graph_builder.add_conditional_edges(
    MAIN_CHATBOT_NODE,
    route_main,
    {MAIN_TOOLS_NODE: MAIN_TOOLS_NODE, END: END},
)
graph_builder.add_edge(MAIN_TOOLS_NODE, MAIN_CHATBOT_NODE)

# Compile
checkpointer = MemorySaver()
graph = graph_builder.compile(checkpointer=checkpointer, store=store)
