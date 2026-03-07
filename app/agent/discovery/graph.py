import functools
from typing import Any, TypeAlias

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

from app.agent.constants import (
    DISCOVERY_CHATBOT_NODE,
    DISCOVERY_FETCH_PROFILE_NODE,
    DISCOVERY_JOB_SPECIALIST_NODE,
    DISCOVERY_TOOLS_NODE,
    MAIN_TOOLS_NODE,
)
from app.agent.discovery.state import DiscoveryAgentState
from app.agent.graph import call_job_specialist
from app.agent.main.nodes import fetch_profile, main_chatbot, route_main
from app.agent.main.tools import main_tools
from app.services.profile_service import ProfileService

_DiscoveryGraph: TypeAlias = CompiledStateGraph[Any, Any, Any, Any]  # noqa: UP040


def get_discovery_graph(checkpointer: Any, store: BaseStore) -> _DiscoveryGraph:
    """Build and compile the standalone Discovery Agent graph."""
    profile_service = ProfileService(store)
    builder = StateGraph(DiscoveryAgentState)

    builder.add_node(DISCOVERY_FETCH_PROFILE_NODE, functools.partial(fetch_profile, store=store))
    builder.add_node(DISCOVERY_CHATBOT_NODE, main_chatbot)
    builder.add_node(DISCOVERY_TOOLS_NODE, ToolNode(tools=main_tools))
    builder.add_node(DISCOVERY_JOB_SPECIALIST_NODE, functools.partial(call_job_specialist, profile_service=profile_service))

    builder.add_edge(START, DISCOVERY_FETCH_PROFILE_NODE)
    builder.add_edge(DISCOVERY_FETCH_PROFILE_NODE, DISCOVERY_CHATBOT_NODE)
    builder.add_conditional_edges(
        DISCOVERY_CHATBOT_NODE,
        route_main,
        {
            MAIN_TOOLS_NODE: DISCOVERY_TOOLS_NODE,
            DISCOVERY_JOB_SPECIALIST_NODE: DISCOVERY_JOB_SPECIALIST_NODE,
            END: END,
        },
    )
    builder.add_edge(DISCOVERY_TOOLS_NODE, DISCOVERY_CHATBOT_NODE)
    builder.add_edge(DISCOVERY_JOB_SPECIALIST_NODE, DISCOVERY_CHATBOT_NODE)

    return builder.compile(checkpointer=checkpointer, store=store)
