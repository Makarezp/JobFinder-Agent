from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.agent.discovery.graph import call_job_specialist
from app.agent.discovery.state import DiscoveryAgentState
from app.agent.job_search.nodes import fetch_jobs
from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobListing, JobSpecialistInput


def _make_state(query: str = "python developer", page: int = 1) -> JobSpecialistState:
    return cast(
        JobSpecialistState,
        {
            "input": JobSpecialistInput(query=query, country="us", page=page),
            "search_results": None,
            "user_profile": None,
            "preferences": None,
        },
    )


def test_fetch_jobs_returns_empty_on_tool_error() -> None:
    """fetch_jobs returns empty list when jsearch_api_search returns an error string."""
    state = _make_state(query="fail")

    with patch("app.agent.job_search.nodes.jsearch_api_search") as mock_tool:
        mock_tool.invoke.return_value = "Error: JSearch API returned status 429."

        result = fetch_jobs(state)

        assert "search_results" in result
        assert result["search_results"] == []


def test_fetch_jobs_maps_jsearch_fields_correctly() -> None:
    """fetch_jobs correctly maps JSearch-shaped dicts to JobListing objects."""
    state = _make_state(query="python developer")

    with patch("app.agent.job_search.nodes.jsearch_api_search") as mock_tool:
        mock_tool.invoke.return_value = [
            {
                "id": "job_abc123",
                "title": "Senior Python Developer",
                "company": "Acme Corp",
                "location": "London, England, GB",
                "salary": "$80,000 - $100,000 per YEAR",
                "description": "We are looking for a Python developer...",
                "full_description": "Full description text here.",
                "apply_link": "https://example.com/apply",
            }
        ]

        result = fetch_jobs(state)

        assert len(result["search_results"]) == 1
        listing: JobListing = result["search_results"][0]
        assert listing.id == "job_abc123"
        assert listing.title == "Senior Python Developer"
        assert listing.company == "Acme Corp"
        assert listing.location == "London, England, GB"
        assert listing.salary == "$80,000 - $100,000 per YEAR"
        assert listing.description == "We are looking for a Python developer..."
        assert listing.full_description == "Full description text here."
        assert listing.apply_link == "https://example.com/apply"


def test_fetch_jobs_applies_defaults_for_missing_fields() -> None:
    """fetch_jobs applies defaults (e.g. title='N/A') for partially-filled entries."""
    state = _make_state(query="python developer")

    with patch("app.agent.job_search.nodes.jsearch_api_search") as mock_tool:
        mock_tool.invoke.return_value = [
            {
                "id": "job_1",
                "title": "Good Job",
                "company": "Co",
                "location": "London, GB",
                "description": "Good snippet.",
                "apply_link": "https://co.com/apply",
            },
            # Sparse entry — node supplies defaults so it still parses
            {"id": "sparse"},
        ]

        result = fetch_jobs(state)

        assert len(result["search_results"]) == 2
        assert result["search_results"][0].title == "Good Job"
        assert result["search_results"][1].title == "N/A"


def test_fetch_jobs_passes_correct_args_to_tool() -> None:
    """fetch_jobs forwards all JobSpecialistInput fields to jsearch_api_search without employment_types."""
    state = cast(
        JobSpecialistState,
        {
            "input": JobSpecialistInput(
                query="golang engineer contract",
                country="us",
                date_posted="week",
                remote_only=True,
                page=2,
            ),
            "search_results": None,
            "user_profile": None,
            "preferences": None,
        },
    )

    with patch("app.agent.job_search.nodes.jsearch_api_search") as mock_tool:
        mock_tool.invoke.return_value = []

        fetch_jobs(state)

        mock_tool.invoke.assert_called_once_with(
            {
                "query": "golang engineer contract",
                "date_posted": "week",
                "remote_only": True,
                "page": 2,
                "num_pages": 1,
                "country": "us",
            }
        )


def test_fetch_jobs_logs_job_summaries() -> None:
    """fetch_jobs logs job_summaries (title @ company) in the Node Completed event."""
    state = _make_state(query="python developer")

    raw_jobs = [
        {
            "id": "job_1",
            "title": "Senior Python Developer",
            "company": "Acme Corp",
            "location": "London, GB",
            "description": "A great role.",
            "apply_link": "https://acme.com/apply",
        },
        {
            "id": "job_2",
            "title": "Backend Engineer",
            "company": "Beta Ltd",
            "location": "Remote",
            "description": "Another role.",
            "apply_link": "https://beta.com/apply",
        },
    ]

    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_tool,
        patch("app.agent.job_search.nodes.logger") as mock_logger,
    ):
        mock_tool.invoke.return_value = raw_jobs

        fetch_jobs(state)

        mock_logger.info.assert_any_call(
            "Node Completed: fetch_jobs",
            result_count=2,
            job_summaries=["Senior Python Developer @ Acme Corp", "Backend Engineer @ Beta Ltd"],
        )


def test_fetch_jobs_returns_all_api_results() -> None:
    """fetch_jobs returns all results from the API without capping."""
    state = _make_state(query="python developer")
    raw_jobs = [
        {
            "id": f"job_{i}",
            "title": f"Job {i}",
            "company": f"Co {i}",
            "location": "London, GB",
            "description": f"Description {i}.",
            "apply_link": f"https://co{i}.com/apply",
        }
        for i in range(15)
    ]

    with patch("app.agent.job_search.nodes.jsearch_api_search") as mock_tool:
        mock_tool.invoke.return_value = raw_jobs

        result = fetch_jobs(state)

        assert len(result["search_results"]) == 15


# ---------------------------------------------------------------------------
# call_job_specialist — parallel execution
# ---------------------------------------------------------------------------


def _make_tool_call(name: str, query: str, tc_id: str) -> dict[str, Any]:
    return {"name": name, "args": {"query": query}, "id": tc_id}


def _make_agent_state(tool_calls: list[dict[str, Any]]) -> DiscoveryAgentState:
    ai_msg = AIMessage(content="")
    ai_msg.tool_calls = tool_calls  # type: ignore[attr-defined, assignment]
    return cast(
        DiscoveryAgentState,
        {
            "messages": [ai_msg],
            "search_attempts": 0,
            "user_profile": None,
            "preferences": None,
        },
    )


def _make_profile_service_mock() -> MagicMock:
    ps = MagicMock()
    ps.get_seen_job_ids = AsyncMock(return_value=set())
    ps.mark_jobs_seen = AsyncMock(return_value=None)
    return ps


@pytest.mark.asyncio
async def test_call_job_specialist_processes_all_parallel_calls() -> None:
    """call_job_specialist returns one ToolMessage per job_specialist_tool call."""
    tool_calls = [
        _make_tool_call("job_specialist_tool", "python developer", "tc-1"),
        _make_tool_call("job_specialist_tool", "backend engineer", "tc-2"),
        _make_tool_call("job_specialist_tool", "data scientist", "tc-3"),
    ]
    state = _make_agent_state(tool_calls)

    with patch("app.agent.discovery.graph.job_search_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value={"search_results": []})
        result = await call_job_specialist(state, _make_profile_service_mock())

    assert len(result["messages"]) == 3
    assert all(isinstance(m, ToolMessage) for m in result["messages"])
    assert result["search_attempts"] == 1


@pytest.mark.asyncio
async def test_call_job_specialist_single_call_unchanged() -> None:
    """call_job_specialist with 1 tool_call returns 1 ToolMessage and search_attempts=1."""
    tool_calls = [_make_tool_call("job_specialist_tool", "python developer", "tc-1")]
    state = _make_agent_state(tool_calls)

    with patch("app.agent.discovery.graph.job_search_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value={"search_results": []})
        result = await call_job_specialist(state, _make_profile_service_mock())

    assert len(result["messages"]) == 1
    assert isinstance(result["messages"][0], ToolMessage)
    assert result["search_attempts"] == 1
