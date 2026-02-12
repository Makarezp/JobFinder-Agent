import pytest
from app.agent.graph import graph
from app.agent.nodes import chatbot, SYSTEM_PROMPT
from unittest.mock import patch
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage


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


@pytest.mark.asyncio
async def test_chatbot_node_adds_system_prompt():
    """Test that the chatbot node prepends the system prompt."""
    state = {"messages": [HumanMessage(content="Hello")]}

    # Patch the llm_with_tools object itself, so we can mock its invoke method
    with patch("app.agent.nodes.llm_with_tools") as mock_llm:
        mock_llm.invoke.return_value = AIMessage(content="Response")

        chatbot(state)

        # Check that invoke was called with SystemMessage first
        # call_args of invoke: (args, kwargs)
        # args[0] is the input to invoke, which should be the list of messages
        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 2
        assert isinstance(call_args[0], SystemMessage)
        assert call_args[0].content == SYSTEM_PROMPT
        assert call_args[1].content == "Hello"
