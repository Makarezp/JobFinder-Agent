from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END
from langgraph.store.memory import InMemoryStore

from app.agent.constants import JOB_SPECIALIST_NODE, MAIN_TOOLS_NODE
from app.agent.graph import call_job_specialist
from app.agent.main.nodes import route_main
from app.services.profile_service import ProfileService


def _make_job_specialist_ai_message(search_attempts: int = 0) -> dict:  # type: ignore[type-arg]
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "job_specialist_tool",
                "args": {"query": "Python engineer in London"},
                "id": "call_1",
            }
        ],
    )
    return {"search_attempts": search_attempts, "messages": [msg]}


# --- route_main loop protection ---


def test_route_main_routes_to_job_specialist_when_under_limit() -> None:
    """route_main routes to JOB_SPECIALIST_NODE when search_attempts < 3."""
    state = _make_job_specialist_ai_message(search_attempts=0)
    result = route_main(state)  # type: ignore[arg-type]
    assert result == JOB_SPECIALIST_NODE


def test_route_main_routes_to_job_specialist_at_two_attempts() -> None:
    """route_main still routes to JOB_SPECIALIST_NODE at 2 attempts (limit is 3)."""
    state = _make_job_specialist_ai_message(search_attempts=2)
    result = route_main(state)  # type: ignore[arg-type]
    assert result == JOB_SPECIALIST_NODE


def test_route_main_blocks_at_three_attempts() -> None:
    """route_main returns END when search_attempts >= 3, blocking further subgraph calls."""
    state = _make_job_specialist_ai_message(search_attempts=3)
    result = route_main(state)  # type: ignore[arg-type]
    assert result == str(END)


def test_route_main_blocks_above_three_attempts() -> None:
    """route_main returns END for any search_attempts >= 3."""
    state = _make_job_specialist_ai_message(search_attempts=10)
    result = route_main(state)  # type: ignore[arg-type]
    assert result == str(END)


def test_route_main_routes_other_tools_to_main_tools_node() -> None:
    """route_main routes non-job-specialist tool calls to MAIN_TOOLS_NODE regardless of search_attempts."""
    msg = AIMessage(
        content="",
        tool_calls=[{"name": "some_other_tool", "args": {}, "id": "call_other"}],
    )
    state = {"search_attempts": 5, "messages": [msg]}
    result = route_main(state)  # type: ignore[arg-type]
    assert result == MAIN_TOOLS_NODE


# --- call_job_specialist increments counter ---


@pytest.mark.asyncio
async def test_call_job_specialist_increments_search_attempts() -> None:
    """call_job_specialist increments search_attempts by 1 on each invocation."""
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "job_specialist_tool",
                "args": {"query": "Python engineer"},
                "id": "call_1",
            }
        ],
    )
    state = {"search_attempts": 1, "messages": [msg]}

    with patch("app.agent.graph.job_search_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value={"search_results": []})
        service = ProfileService(InMemoryStore())
        result = await call_job_specialist(state, profile_service=service)  # type: ignore[arg-type]

        assert result["search_attempts"] == 2
        assert "messages" in result
