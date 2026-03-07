from typing import Any, TypeAlias

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore

from app.agent.profile.graph import get_profile_graph
from app.agent.profile.state import ProfileAgentState

_Graph: TypeAlias = CompiledStateGraph[Any, Any, Any, Any]


@pytest.fixture(scope="module")
def profile_graph() -> _Graph:
    return get_profile_graph(checkpointer=MemorySaver(), store=InMemoryStore())


def test_profile_graph_compiles(profile_graph: _Graph) -> None:
    assert profile_graph is not None


def test_profile_graph_has_correct_nodes(profile_graph: _Graph) -> None:
    assert "fetch_profile_data" in profile_graph.nodes
    assert "profile_chatbot" in profile_graph.nodes
    assert "profile_tools" in profile_graph.nodes


def test_profile_graph_does_not_contain_discovery_nodes(profile_graph: _Graph) -> None:
    assert "main_chatbot" not in profile_graph.nodes
    assert "job_specialist_node" not in profile_graph.nodes
    assert "discovery_chatbot" not in profile_graph.nodes


def test_profile_state_has_no_discovery_fields() -> None:
    annotations = ProfileAgentState.__annotations__
    assert "search_attempts" not in annotations
    assert "recent_decisions" not in annotations
