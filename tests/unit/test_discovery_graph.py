from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore

from app.agent.constants import (
    DISCOVERY_CHATBOT_NODE,
    DISCOVERY_FETCH_PROFILE_NODE,
    DISCOVERY_JOB_SPECIALIST_NODE,
    DISCOVERY_TOOLS_NODE,
)
from app.agent.discovery.graph import get_discovery_graph
from app.agent.discovery.state import DiscoveryAgentState


@pytest.fixture(scope="module")
def discovery_graph() -> CompiledStateGraph[Any]:
    return get_discovery_graph(checkpointer=MemorySaver(), store=InMemoryStore())


def test_discovery_graph_compiles(discovery_graph: CompiledStateGraph[Any]) -> None:
    assert discovery_graph is not None


def test_discovery_graph_has_correct_nodes(discovery_graph: CompiledStateGraph[Any]) -> None:
    assert DISCOVERY_FETCH_PROFILE_NODE in discovery_graph.nodes
    assert DISCOVERY_CHATBOT_NODE in discovery_graph.nodes
    assert DISCOVERY_TOOLS_NODE in discovery_graph.nodes
    assert DISCOVERY_JOB_SPECIALIST_NODE in discovery_graph.nodes


def test_discovery_graph_does_not_contain_onboarding_nodes(discovery_graph: CompiledStateGraph[Any]) -> None:
    assert "onboarding_chatbot" not in discovery_graph.nodes
    assert "onboarding_tools" not in discovery_graph.nodes
    assert "check_onboarding_status" not in discovery_graph.nodes


def test_discovery_state_has_no_onboarding_fields() -> None:
    annotations = DiscoveryAgentState.__annotations__
    assert "onboarding_complete" not in annotations
    assert "cv_raw_text" not in annotations
