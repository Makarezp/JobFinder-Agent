import pytest
from langchain_core.messages import ToolMessage

from app.agent.graph import call_job_specialist
from app.agent.state import AgentState


@pytest.mark.asyncio
async def test_call_job_specialist_increments_attempts() -> None:
    """Test that call_job_specialist increments search_attempts when searching."""
    # Setup state
    state: AgentState = {
        "search_attempts": 0,
        "messages": [
            ToolMessage(
                content="",
                tool_call_id="call_1",
            )
        ],
    }  # type: ignore

    # We need to mock the last message to have tool_calls
    from langchain_core.messages import AIMessage

    # 1. First Attempt
    msg = AIMessage(
        content="", tool_calls=[{"name": "job_specialist_tool", "args": {"mode": "search", "query": "Python", "location": "London"}, "id": "call_1"}]
    )
    state = {"search_attempts": 0, "messages": [msg]}  # type: ignore

    # Mock the subgraph invocation?
    # call_job_specialist calls `job_search_graph.ainvoke`. We need to patch it.
    from unittest.mock import AsyncMock, patch

    with patch("app.agent.graph.job_search_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value={"search_results": [], "inspect_result": None})

        # ACT
        result = await call_job_specialist(state)  # type: ignore

        # ASSERT
        assert result["search_attempts"] == 1
        assert "messages" in result


@pytest.mark.asyncio
async def test_call_job_specialist_blocks_fourth_attempt() -> None:
    """Test that call_job_specialist blocks execution when attempts >= 3."""
    # Setup state with 3 attempts already
    from langchain_core.messages import AIMessage

    msg = AIMessage(
        content="",
        tool_calls=[{"name": "job_specialist_tool", "args": {"mode": "search", "query": "Python", "location": "London"}, "id": "call_blocked"}],
    )
    state = {"search_attempts": 3, "messages": [msg]}  # type: ignore

    # ACT
    # We don't even need to patch the graph because it should return early
    result = await call_job_specialist(state)  # type: ignore

    # ASSERT
    # Should NOT satisfy the increment logic (or rather, it returns early)
    # The return value from the block is: {"messages": [ToolMessage(...)]}
    # It does NOT return "search_attempts" key (so it stays same in state? No, Reducer?)
    # Wait, check logic:
    # if current_attempts >= 3: return {"messages": [...]}
    # It does NOT return new_attempts.

    assert "search_attempts" not in result
    assert "messages" in result
    tool_msg = result["messages"][0]
    assert isinstance(tool_msg, ToolMessage)
    assert "SYSTEM ALERT" in tool_msg.content
    assert "Maximum search attempts" in tool_msg.content


@pytest.mark.asyncio
async def test_call_job_specialist_blocks_sixth_inspect_attempt() -> None:
    """call_job_specialist returns SYSTEM ALERT when inspect_attempts >= 5, without invoking subgraph."""
    from langchain_core.messages import AIMessage

    msg = AIMessage(
        content="",
        tool_calls=[{"name": "job_specialist_tool", "args": {"mode": "inspect", "url": "http://foo.com"}, "id": "call_inspect_blocked"}],
    )
    state = {"inspect_attempts": 5, "search_attempts": 0, "messages": [msg]}  # type: ignore

    from unittest.mock import AsyncMock, patch

    with patch("app.agent.graph.job_search_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock()

        result = await call_job_specialist(state)  # type: ignore

        mock_graph.ainvoke.assert_not_called()
        assert "messages" in result
        tool_msg = result["messages"][0]
        assert isinstance(tool_msg, ToolMessage)
        assert "SYSTEM ALERT" in tool_msg.content
        assert "Maximum inspect attempts" in tool_msg.content


@pytest.mark.asyncio
async def test_inspect_stores_full_description_in_inspect_results() -> None:
    """After a successful inspect, the returned dict has inspect_results keyed by URL."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from langchain_core.messages import AIMessage

    url = "http://example.com/job"
    msg = AIMessage(
        content="",
        tool_calls=[{"name": "job_specialist_tool", "args": {"mode": "inspect", "url": url}, "id": "call_insp"}],
    )
    state = {"inspect_attempts": 0, "search_attempts": 0, "messages": [msg]}  # type: ignore

    with patch("app.agent.graph.job_search_graph") as mock_graph:
        mock_detail = MagicMock()
        mock_detail.full_description = "Full job description text."
        mock_detail.model_dump_json.return_value = '{"full_description": "Full job description text."}'
        mock_graph.ainvoke = AsyncMock(return_value={"search_results": [], "inspect_result": mock_detail})

        result = await call_job_specialist(state)  # type: ignore

        assert "inspect_results" in result
        assert result["inspect_results"][url] == "Full job description text."


@pytest.mark.asyncio
async def test_inspect_does_not_increment_attempts() -> None:
    """Test that 'inspect' mode does NOT increment search_attempts."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from langchain_core.messages import AIMessage

    msg = AIMessage(
        content="", tool_calls=[{"name": "job_specialist_tool", "args": {"mode": "inspect", "url": "http://foo.com"}, "id": "call_inspect"}]
    )
    state = {"search_attempts": 1, "messages": [msg]}  # type: ignore

    with patch("app.agent.graph.job_search_graph") as mock_graph:
        mock_inspect_result = MagicMock()
        mock_inspect_result.model_dump_json.return_value = '{"detail": "content"}'
        mock_graph.ainvoke = AsyncMock(return_value={"search_results": [], "inspect_result": mock_inspect_result})

        # ACT
        result = await call_job_specialist(state)  # type: ignore

        # ASSERT
        # Logic: else: new_attempts = state.get("search_attempts", 0)
        # return { ..., "search_attempts": new_attempts }

        assert result["search_attempts"] == 1  # Should remain 1
