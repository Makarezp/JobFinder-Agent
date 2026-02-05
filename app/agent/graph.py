from langgraph.graph import StateGraph, START, END
from app.agent.state import AgentState
from app.agent.nodes import chatbot, tool_node
from langchain_core.messages import AIMessage


def route_tools(state: AgentState):
    """
    Check if the last message is a tool call.
    """
    # It's a dict/AgentState
    messages = state.get("messages", [])
    ai_message = messages[-1] if messages else None

    if (
        isinstance(ai_message, AIMessage)
        and hasattr(ai_message, "tool_calls")
        and len(ai_message.tool_calls) > 0
    ):
        return "tools"
    return END


# Graph Definition
graph_builder = StateGraph(AgentState)

graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tools", tool_node)

graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges(
    "chatbot", route_tools, {"tools": "tools", END: END}
)
graph_builder.add_edge("tools", "chatbot")

graph = graph_builder.compile()
