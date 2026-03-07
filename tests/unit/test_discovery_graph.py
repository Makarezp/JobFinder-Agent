from typing import Any, TypeAlias

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore

from app.agent.discovery.graph import get_discovery_graph
from app.agent.discovery.state import DiscoveryAgentState

_Graph: TypeAlias = CompiledStateGraph[Any, Any, Any, Any]


@pytest.fixture(scope="module")
def discovery_graph() -> _Graph:
    return get_discovery_graph(checkpointer=MemorySaver(), store=InMemoryStore())


def test_discovery_graph_compiles(discovery_graph: _Graph) -> None:
    assert discovery_graph is not None


def test_discovery_graph_has_correct_nodes(discovery_graph: _Graph) -> None:
    assert "fetch_profile" in discovery_graph.nodes
    assert "discovery_chatbot" in discovery_graph.nodes
    assert "discovery_tools" in discovery_graph.nodes
    assert "job_specialist_node" in discovery_graph.nodes


def test_discovery_graph_does_not_contain_onboarding_nodes(discovery_graph: _Graph) -> None:
    assert "onboarding_chatbot" not in discovery_graph.nodes
    assert "onboarding_tools" not in discovery_graph.nodes
    assert "check_onboarding_status" not in discovery_graph.nodes


def test_discovery_state_has_no_onboarding_fields() -> None:
    annotations = DiscoveryAgentState.__annotations__
    assert "onboarding_complete" not in annotations
    assert "cv_raw_text" not in annotations
