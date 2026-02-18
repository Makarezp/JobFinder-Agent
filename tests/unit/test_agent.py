from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.agent.constants import (
    FETCH_PROFILE_NODE,
    MAIN_CHATBOT_NODE,
    MAIN_TOOLS_NODE,
    ONBOARDING_CHATBOT_NODE,
    ONBOARDING_TOOLS_NODE,
)
from app.agent.graph import get_compiled_graph
from app.agent.main.nodes import main_chatbot
from app.agent.onboarding.nodes import onboarding_chatbot
from app.agent.state import AgentState

# Initialize graph for testing with in-memory storage
graph = get_compiled_graph(checkpointer=MemorySaver(), store=InMemoryStore())


@pytest.mark.asyncio
async def test_agent_graph_initialization() -> None:
    """Test that the graph compiles and can handle a basic input structure."""
    assert graph is not None


@pytest.mark.asyncio
async def test_agent_graph_has_correct_nodes() -> None:
    """Verify the graph contains all expected nodes for the dual-agent topology."""
    assert ONBOARDING_CHATBOT_NODE in graph.nodes
    assert ONBOARDING_TOOLS_NODE in graph.nodes
    assert FETCH_PROFILE_NODE in graph.nodes
    assert MAIN_CHATBOT_NODE in graph.nodes
    assert MAIN_TOOLS_NODE in graph.nodes


@pytest.mark.asyncio
async def test_main_chatbot_node_adds_system_prompt() -> None:
    """Test that the main chatbot node prepends the system prompt."""
    state = {
        "messages": [HumanMessage(content="Hello")],
        "user_profile": None,
        "preferences": None,
    }

    with patch("app.agent.main.nodes.main_llm") as mock_llm:
        mock_llm.invoke.return_value = AIMessage(content="Response")

        main_chatbot(state)

        call_args = mock_llm.invoke.call_args[0][0]
        assert len(call_args) == 2
        assert isinstance(call_args[0], SystemMessage)
        # Main agent prompt should have profile/preferences placeholders filled
        assert "User" in call_args[0].content
        assert "Job Seeker" in call_args[0].content
        assert call_args[1].content == "Hello"


@pytest.mark.asyncio
async def test_onboarding_chatbot_uses_onboarding_prompt() -> None:
    """Test that the onboarding chatbot uses its own prompt."""
    state = {
        "messages": [HumanMessage(content="Hi")],
        "cv_raw_text": None,
    }

    with patch("app.agent.onboarding.nodes.onboarding_llm") as mock_llm:
        mock_llm.invoke.return_value = AIMessage(content="Welcome!")

        onboarding_chatbot(state)

        call_args = mock_llm.invoke.call_args[0][0]
        assert isinstance(call_args[0], SystemMessage)
        assert isinstance(call_args[0].content, str)
        assert "onboarding" in call_args[0].content.lower()


@pytest.mark.asyncio
async def test_onboarding_chatbot_includes_cv_raw_text() -> None:
    """Test that onboarding chatbot includes CV raw text when available."""
    state = {
        "messages": [HumanMessage(content="Analyze my CV")],
        "cv_raw_text": "John Doe\nSenior Developer\n5 years experience",
    }

    with patch("app.agent.onboarding.nodes.onboarding_llm") as mock_llm:
        mock_llm.invoke.return_value = AIMessage(content="I see your CV!")

        onboarding_chatbot(state)

        call_args = mock_llm.invoke.call_args[0][0]
        system_content = call_args[0].content
        assert "John Doe" in system_content
        assert "Senior Developer" in system_content


@pytest.mark.asyncio
async def test_router_routes_to_onboarding() -> None:
    """Test that router sends new users to onboarding."""
    from app.agent.graph import router

    state: AgentState = {
        "onboarding_complete": False,
        "messages": [],
        "user_profile": None,
        "preferences": None,
        "cv_raw_text": None,
        "active_agent": "onboarding",
    }  # type: ignore[typeddict-item]
    result = router(state)
    assert result == ONBOARDING_CHATBOT_NODE


@pytest.mark.asyncio
async def test_router_routes_to_main() -> None:
    """Test that router sends onboarded users to main agent."""
    from app.agent.graph import router

    state: AgentState = {
        "onboarding_complete": True,
        "messages": [],
        "user_profile": None,
        "preferences": None,
        "cv_raw_text": None,
        "active_agent": "main",
    }  # type: ignore[typeddict-item]
    result = router(state)
    assert result == FETCH_PROFILE_NODE
