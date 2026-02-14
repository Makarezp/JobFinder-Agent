from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.graph import graph
from app.agent.nodes import chatbot
from app.agent.prompts.agent_prompts import SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_agent_graph_initialization() -> None:
    """Test that the graph compiles and can handle a basic input structure."""
    assert graph is not None


@pytest.mark.asyncio
async def test_agent_graph_execution_mock() -> None:
    """
    Smoke test for graph execution.
    Note: Real execution requires keys, so we mock or just check structure.
    This test ensures imports and wiring are correct.
    """
    # Simply verify the graph keys
    assert "chatbot" in graph.nodes
    assert "tools" in graph.nodes


@pytest.mark.asyncio
async def test_chatbot_node_adds_system_prompt() -> None:
    """Test that the chatbot node prepends the system prompt."""
    state = {"messages": [HumanMessage(content="Hello")]}

    # Patch the llm_with_tools object itself, so we can mock its invoke method
    with patch("app.agent.nodes.llm_with_tools") as mock_llm:
        mock_llm.invoke.return_value = AIMessage(content="Response")

        chatbot(state)

        # Check that invoke was called with SystemMessage first
        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 2
        assert isinstance(call_args[0], SystemMessage)

        # The chatbot node formats the system prompt with defaults if no profile is present
        expected_prompt = SYSTEM_PROMPT.format(name="User", role="Job Seeker")
        assert call_args[0].content == expected_prompt
        assert call_args[1].content == "Hello"
