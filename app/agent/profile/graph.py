import functools
from typing import Any, TypeAlias

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

from app.agent.constants import (
    ONBOARDING_TOOLS_NODE,
    PROFILE_CHATBOT_NODE,
    PROFILE_FETCH_NODE,
    PROFILE_TOOLS_NODE,
)
from app.agent.onboarding.nodes import onboarding_chatbot, route_onboarding
from app.agent.onboarding.tools import onboarding_tools
from app.agent.profile.nodes import fetch_profile_data
from app.agent.profile.state import ProfileAgentState

_ProfileGraph: TypeAlias = CompiledStateGraph[Any, Any, Any, Any]


def get_profile_graph(checkpointer: Any, store: BaseStore) -> _ProfileGraph:
    """Build and compile the standalone Profile Agent graph."""
    builder = StateGraph(ProfileAgentState)

    builder.add_node(PROFILE_FETCH_NODE, functools.partial(fetch_profile_data, store=store))
    builder.add_node(PROFILE_CHATBOT_NODE, onboarding_chatbot)
    builder.add_node(PROFILE_TOOLS_NODE, ToolNode(tools=onboarding_tools))

    builder.add_edge(START, PROFILE_FETCH_NODE)
    builder.add_edge(PROFILE_FETCH_NODE, PROFILE_CHATBOT_NODE)
    builder.add_conditional_edges(
        PROFILE_CHATBOT_NODE,
        route_onboarding,
        {ONBOARDING_TOOLS_NODE: PROFILE_TOOLS_NODE, END: END},
    )
    builder.add_edge(PROFILE_TOOLS_NODE, PROFILE_CHATBOT_NODE)

    return builder.compile(checkpointer=checkpointer, store=store)
