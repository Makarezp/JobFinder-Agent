import functools
from typing import cast

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

from app.agent.constants import (
    FINAL_ANSWER_TOOL_NAME,
    MESSAGES_KEY,
)
from app.agent.nodes import chatbot, fetch_profile, tool_node
from app.agent.state import AgentState

CHATBOT_NODE = "chatbot"
FETCH_PROFILE_NODE = "fetch_profile"
TOOLS_NODE = "tools"


def route_tools(state: AgentState) -> str:
    """
    Check if the last message is a tool call.
    """
    # It's a dict/AgentState
    messages = cast(list[BaseMessage], state.get(MESSAGES_KEY, []))
    ai_message = messages[-1] if messages else None

    if isinstance(ai_message, AIMessage) and hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
        # Check if the tool call is final_answer
        first_tool_call = ai_message.tool_calls[0]
        if first_tool_call["name"] == FINAL_ANSWER_TOOL_NAME:
            return str(END)
        return TOOLS_NODE
    return str(END)


# Graph Definition
graph_builder = StateGraph(AgentState)
store = InMemoryStore()

graph_builder.add_node(CHATBOT_NODE, chatbot)
graph_builder.add_node(FETCH_PROFILE_NODE, functools.partial(fetch_profile, store=store))
graph_builder.add_node(TOOLS_NODE, tool_node)

graph_builder.add_edge(START, FETCH_PROFILE_NODE)
graph_builder.add_edge(FETCH_PROFILE_NODE, CHATBOT_NODE)
graph_builder.add_conditional_edges(CHATBOT_NODE, route_tools, {TOOLS_NODE: TOOLS_NODE, END: END})
graph_builder.add_edge(TOOLS_NODE, CHATBOT_NODE)

checkpointer = MemorySaver()
graph = graph_builder.compile(checkpointer=checkpointer, store=store)
