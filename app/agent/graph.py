import functools
import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.memory import InMemoryStore

from app.agent.constants import (
    CHECK_ONBOARDING_NODE,
    FETCH_PROFILE_NODE,
    MAIN_CHATBOT_NODE,
    MAIN_TOOLS_NODE,
    ONBOARDING_CHATBOT_NODE,
    ONBOARDING_TOOLS_NODE,
)
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
from app.agent.state import AgentState

logger = logging.getLogger(__name__)


# --- Router: pure conditional, no LLM ---
def router(state: AgentState) -> str:
    """Route to onboarding or main agent based on onboarding status."""
    if state.get("onboarding_complete"):
        return FETCH_PROFILE_NODE
    return ONBOARDING_CHATBOT_NODE


# --- Graph Definition ---
store = InMemoryStore()
graph_builder = StateGraph(AgentState)

# Nodes — store-dependent nodes need functools.partial (InjectedStore only works for tools)
graph_builder.add_node(CHECK_ONBOARDING_NODE, functools.partial(check_onboarding_status, store=store))
graph_builder.add_node(ONBOARDING_CHATBOT_NODE, onboarding_chatbot)
graph_builder.add_node(ONBOARDING_TOOLS_NODE, ToolNode(tools=onboarding_tools))
graph_builder.add_node(FETCH_PROFILE_NODE, functools.partial(fetch_profile, store=store))
graph_builder.add_node(MAIN_CHATBOT_NODE, main_chatbot)
graph_builder.add_node(MAIN_TOOLS_NODE, ToolNode(tools=main_tools))

# Entry: check onboarding status first, then route
graph_builder.add_edge(START, CHECK_ONBOARDING_NODE)
graph_builder.add_conditional_edges(
    CHECK_ONBOARDING_NODE,
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
    {ONBOARDING_CHATBOT_NODE: ONBOARDING_CHATBOT_NODE, FETCH_PROFILE_NODE: FETCH_PROFILE_NODE},
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
