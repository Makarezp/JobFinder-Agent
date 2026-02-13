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
        # Check if the tool call is final_answer
        first_tool_call = ai_message.tool_calls[0]
        if first_tool_call["name"] == "final_answer":
            return END
        return "tools"
    return END


from langgraph.checkpoint.memory import MemorySaver

# Graph Definition
graph_builder = StateGraph(AgentState)

graph_builder.add_node("chatbot", chatbot)
graph_builder.add_node("tools", tool_node)

graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges(
    "chatbot", route_tools, {"tools": "tools", END: END}
)
graph_builder.add_edge("tools", "chatbot")

checkpointer = MemorySaver()
graph = graph_builder.compile(checkpointer=checkpointer)
