import functools
import json
import logging
from typing import Any, cast

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

from app.agent.constants import (
    CHECK_ONBOARDING_NODE,
    FETCH_PROFILE_NODE,
    JOB_SPECIALIST_NODE,
    MAIN_CHATBOT_NODE,
    MAIN_TOOLS_NODE,
    ONBOARDING_CHATBOT_NODE,
    ONBOARDING_TOOLS_NODE,
)
from app.agent.job_search.graph import job_search_graph
from app.agent.job_search.state import JobSpecialistState
from app.agent.main.nodes import (
    fetch_profile,
    main_chatbot,
    route_main,
)
from app.agent.main.tools import main_tools
from app.agent.onboarding.nodes import (
    check_onboarding_status,
    onboarding_chatbot,
    route_after_onboarding_tools,
    route_onboarding,
)
from app.agent.onboarding.tools import onboarding_tools
from app.agent.schemas import JobSpecialistInput
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


# --- Node: call_job_specialist ---
async def call_job_specialist(state: AgentState) -> dict[str, Any]:
    """Invokes the Job Specialist subgraph based on the last tool call."""
    messages = state["messages"]
    last_message = messages[-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": []}

    tool_call = last_message.tool_calls[0]
    tool_call_id = tool_call["id"]

    try:
        args = tool_call["args"]
        input_data = JobSpecialistInput(**args)
    except Exception as e:
        return {"messages": [ToolMessage(content=f"Error parsing input: {e}", tool_call_id=tool_call_id)]}

    current_attempts = state.get("search_attempts", 0)

    subgraph_state: JobSpecialistState = {
        "input": input_data,
        "search_results": None,
    }
    result = await job_search_graph.ainvoke(cast(Any, subgraph_state))

    results = result.get("search_results", [])
    output_content = json.dumps([r.model_dump() for r in results], indent=2) if results else "No jobs found."
    return {
        "messages": [ToolMessage(content=output_content, tool_call_id=tool_call_id)],
        "search_attempts": current_attempts + 1,
    }


# --- Router: pure conditional, no LLM ---
def router(state: AgentState) -> str:
    """Route to onboarding or main agent based on onboarding status."""
    if state.get("onboarding_complete"):
        return FETCH_PROFILE_NODE
    return ONBOARDING_CHATBOT_NODE


# Compile
def get_compiled_graph(checkpointer: Any, store: BaseStore) -> Any:
    """Compiles the graph with the provided checkpointer and store."""
    builder = StateGraph(AgentState)

    # Nodes
    builder.add_node(CHECK_ONBOARDING_NODE, functools.partial(check_onboarding_status, store=store))
    builder.add_node(ONBOARDING_CHATBOT_NODE, onboarding_chatbot)
    builder.add_node(ONBOARDING_TOOLS_NODE, ToolNode(tools=onboarding_tools))
    builder.add_node(FETCH_PROFILE_NODE, functools.partial(fetch_profile, store=store))
    builder.add_node(MAIN_CHATBOT_NODE, main_chatbot)
    builder.add_node(MAIN_TOOLS_NODE, ToolNode(tools=main_tools))
    builder.add_node(JOB_SPECIALIST_NODE, call_job_specialist)

    # Entry
    builder.add_edge(START, CHECK_ONBOARDING_NODE)
    builder.add_conditional_edges(
        CHECK_ONBOARDING_NODE,
        router,
        {FETCH_PROFILE_NODE: FETCH_PROFILE_NODE, ONBOARDING_CHATBOT_NODE: ONBOARDING_CHATBOT_NODE},
    )

    # Onboarding path
    builder.add_conditional_edges(
        ONBOARDING_CHATBOT_NODE,
        route_onboarding,
        {ONBOARDING_TOOLS_NODE: ONBOARDING_TOOLS_NODE, END: END},
    )
    builder.add_conditional_edges(
        ONBOARDING_TOOLS_NODE,
        route_after_onboarding_tools,
        {ONBOARDING_CHATBOT_NODE: ONBOARDING_CHATBOT_NODE, FETCH_PROFILE_NODE: FETCH_PROFILE_NODE},
    )

    # Main agent path
    builder.add_edge(FETCH_PROFILE_NODE, MAIN_CHATBOT_NODE)
    builder.add_conditional_edges(
        MAIN_CHATBOT_NODE,
        route_main,
        {MAIN_TOOLS_NODE: MAIN_TOOLS_NODE, JOB_SPECIALIST_NODE: JOB_SPECIALIST_NODE, END: END},
    )
    builder.add_edge(MAIN_TOOLS_NODE, MAIN_CHATBOT_NODE)
    builder.add_edge(JOB_SPECIALIST_NODE, MAIN_CHATBOT_NODE)

    return builder.compile(checkpointer=checkpointer, store=store)
