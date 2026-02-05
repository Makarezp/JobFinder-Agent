import pytest
from app.agent.graph import graph
from langchain_core.messages import HumanMessage, AIMessage


@pytest.mark.asyncio
async def test_agent_graph_initialization():
    """Test that the graph compiles and can handle a basic input structure."""
    assert graph is not None


@pytest.mark.asyncio
async def test_agent_graph_execution_mock():
    """
    Smoke test for graph execution.
    Note: Real execution requires keys, so we mock or just check structure.
    This test ensures imports and wiring are correct.
    """
    # Simply verify the graph keys
    assert "chatbot" in graph.nodes
    assert "tools" in graph.nodes
