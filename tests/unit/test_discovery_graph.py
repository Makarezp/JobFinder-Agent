import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore

from app.agent.constants import (
    DISCOVERY_CHATBOT_NODE,
    DISCOVERY_FETCH_PROFILE_NODE,
    DISCOVERY_JOB_SPECIALIST_NODE,
    DISCOVERY_TOOLS_NODE,
)
from app.agent.discovery.graph import _run_single_job_search, call_job_specialist, get_discovery_graph
from app.agent.discovery.state import DiscoveryAgentState
from app.services.profile_service import ProfileService


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


def test_route_after_tools_routes_to_end_on_final_answer() -> None:
    from langchain_core.messages import AIMessage

    from app.agent.constants import FINAL_ANSWER_TOOL_NAME
    from app.agent.discovery.graph import route_after_tools

    msg = AIMessage(
        content="",
        tool_calls=[{"name": FINAL_ANSWER_TOOL_NAME, "args": {}, "id": "1"}],
    )
    assert route_after_tools({"messages": [msg]}) == "__end__"  # type: ignore


def test_route_after_tools_routes_to_chatbot_on_other_tools() -> None:
    from langchain_core.messages import AIMessage

    from app.agent.constants import DISCOVERY_CHATBOT_NODE
    from app.agent.discovery.graph import route_after_tools

    msg = AIMessage(
        content="",
        tool_calls=[{"name": "some_other_tool", "args": {}, "id": "1"}],
    )
    assert route_after_tools({"messages": [msg]}) == DISCOVERY_CHATBOT_NODE  # type: ignore


# ---------------------------------------------------------------------------
# _run_single_job_search — ledger logging (Ticket 3)
# ---------------------------------------------------------------------------


def _raw_job(job_id: str) -> dict[str, Any]:
    return {
        "id": job_id,
        "title": f"Job {job_id}",
        "company": f"Co {job_id}",
        "location": "London, GB",
        "salary": None,
        "description": f"Desc {job_id}.",
        "full_description": "",
        "apply_link": f"https://example.com/{job_id}",
    }


def _job_tool_call(query: str = "python dev", tc_id: str = "tc-1") -> dict[str, Any]:
    return {"id": tc_id, "name": "job_specialist_tool", "args": {"query": query, "country": "gb"}}


def _mock_ps() -> MagicMock:
    mock = MagicMock()
    mock.log_search = AsyncMock()
    return mock


@pytest.mark.asyncio
async def test_run_single_job_search_logs_to_ledger() -> None:
    """log_search called with results_count=8, fresh_count=5 (3 of 8 seen)."""
    raw_jobs = [_raw_job(str(i)) for i in range(8)]
    seen_ids = {"0", "1", "2"}  # 3 overlap → 5 fresh
    ps = _mock_ps()

    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_jsearch,
        patch("app.agent.discovery.graph.job_search_graph") as mock_sg,
    ):
        mock_jsearch.invoke.return_value = raw_jobs
        mock_sg.ainvoke = AsyncMock(return_value={"job_payloads": [], "tool_message_content": json.dumps({"jobs": []})})
        await _run_single_job_search(_job_tool_call(), seen_ids, None, None, ps)

    ps.log_search.assert_called_once()
    kw = ps.log_search.call_args.kwargs
    assert kw["results_count"] == 8
    assert kw["fresh_count"] == 5


@pytest.mark.asyncio
async def test_run_single_job_search_logs_even_on_zero_results() -> None:
    """log_search called with results_count=0, fresh_count=0 when nothing returned."""
    ps = _mock_ps()

    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_jsearch,
        patch("app.agent.discovery.graph.job_search_graph") as mock_sg,
    ):
        mock_jsearch.invoke.return_value = []
        mock_sg.ainvoke = AsyncMock(return_value={"job_payloads": [], "tool_message_content": json.dumps({"jobs": []})})
        await _run_single_job_search(_job_tool_call(), set(), None, None, ps)

    ps.log_search.assert_called_once()
    kw = ps.log_search.call_args.kwargs
    assert kw["results_count"] == 0
    assert kw["fresh_count"] == 0


@pytest.mark.asyncio
async def test_run_single_job_search_logs_before_subgraph() -> None:
    """log_search is called even when job_search_graph.ainvoke raises."""
    ps = _mock_ps()

    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_jsearch,
        patch("app.agent.discovery.graph.job_search_graph") as mock_sg,
    ):
        mock_jsearch.invoke.return_value = [_raw_job("x")]
        mock_sg.ainvoke = AsyncMock(side_effect=Exception("subgraph boom"))
        with pytest.raises(Exception, match="subgraph boom"):
            await _run_single_job_search(_job_tool_call(), set(), None, None, ps)

    # log_search ran BEFORE ainvoke, so it must have been called
    ps.log_search.assert_called_once()


@pytest.mark.asyncio
async def test_call_job_specialist_passes_profile_service() -> None:
    """call_job_specialist forwards profile_service to _run_single_job_search."""
    ps = MagicMock(spec=ProfileService)
    ps.get_seen_job_ids = AsyncMock(return_value=set())
    ps.mark_jobs_seen = AsyncMock()

    tc_id = "tc-ps"
    ai_msg = AIMessage(content="")
    ai_msg.tool_calls = [  # type: ignore[attr-defined]
        {"name": "job_specialist_tool", "args": {"query": "python dev", "country": "gb"}, "id": tc_id}
    ]
    state: dict[str, Any] = {"messages": [ai_msg], "search_attempts": 0, "user_profile": None, "preferences": None}
    fake_msg = ToolMessage(content=json.dumps({"jobs": []}), tool_call_id=tc_id)

    with patch("app.agent.discovery.graph._run_single_job_search", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = (fake_msg, [], [])
        await call_job_specialist(state, ps)  # type: ignore[arg-type]

    mock_run.assert_called_once()
    # profile_service is the 5th positional argument
    assert mock_run.call_args.args[4] is ps
