from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.agent.discovery.graph import call_job_specialist
from app.agent.discovery.state import DiscoveryAgentState
from app.agent.job_search.nodes import (
    _chunk_listings,
    _summarize_batch,
    fetch_jobs,
    finalize_state,
    summarize_jobs_parallel,
)
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
# _chunk_listings
# ---------------------------------------------------------------------------


def _make_listing(job_id: str) -> JobListing:
    return JobListing(
        id=job_id,
        title=f"Job {job_id}",
        company=f"Co {job_id}",
        location="London, GB",
        description=f"Desc {job_id}",
        apply_link=f"https://{job_id}.com/apply",
    )


def test_chunk_listings_even_split() -> None:
    listings = [_make_listing(str(i)) for i in range(8)]
    chunks = _chunk_listings(listings, 4)
    assert len(chunks) == 2
    assert all(len(c) == 4 for c in chunks)


def test_chunk_listings_remainder() -> None:
    listings = [_make_listing(str(i)) for i in range(10)]
    chunks = _chunk_listings(listings, 4)
    assert len(chunks) == 3
    assert [len(c) for c in chunks] == [4, 4, 2]


def test_chunk_listings_empty() -> None:
    assert _chunk_listings([], 4) == []


# ---------------------------------------------------------------------------
# summarize_jobs_parallel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summarize_jobs_parallel_empty_results() -> None:
    state = _make_state()
    state["search_results"] = []
    result = await summarize_jobs_parallel(state)
    assert result == {"summaries": []}


@pytest.mark.asyncio
async def test_summarize_jobs_parallel_calls_llm_per_chunk() -> None:
    """10 jobs with batch size 4 should produce 3 LLM calls."""
    from app.agent.schemas import JobSummary, JobSummaryBatch

    listings = [_make_listing(str(i)) for i in range(10)]
    state = _make_state()
    state["search_results"] = listings

    def make_batch_response(messages: Any) -> JobSummaryBatch:
        # Return summaries matching the job_ids in the prompt
        import json as _json

        jobs_text = messages[-1].content
        jobs = _json.loads(jobs_text)
        return JobSummaryBatch(summaries=[JobSummary(job_id=j["id"], description=f"Summary for {j['id']}") for j in jobs])

    mock_llm = AsyncMock(side_effect=make_batch_response)

    with patch("app.agent.job_search.nodes._get_summary_llm") as mock_get:
        mock_get.return_value.ainvoke = mock_llm
        result = await summarize_jobs_parallel(state)

    assert mock_llm.call_count == 3
    assert len(result["summaries"]) == 10


@pytest.mark.asyncio
async def test_summarize_batch_handles_llm_exception() -> None:
    batch = [_make_listing("1"), _make_listing("2")]
    with patch("app.agent.job_search.nodes._get_summary_llm") as mock_get:
        mock_get.return_value.ainvoke = AsyncMock(side_effect=Exception("LLM down"))
        result = await _summarize_batch(batch, None, None)
    assert result == []


@pytest.mark.asyncio
async def test_summarize_batch_handles_count_mismatch() -> None:
    """LLM returns 3 summaries for a batch of 4 — only matching IDs kept."""
    from app.agent.schemas import JobSummary, JobSummaryBatch

    batch = [_make_listing(str(i)) for i in range(4)]

    mock_response = JobSummaryBatch(
        summaries=[
            JobSummary(job_id="0", description="Summary 0"),
            JobSummary(job_id="1", description="Summary 1"),
            JobSummary(job_id="2", description="Summary 2"),
        ]
    )

    with patch("app.agent.job_search.nodes._get_summary_llm") as mock_get:
        mock_get.return_value.ainvoke = AsyncMock(return_value=mock_response)
        result = await _summarize_batch(batch, None, None)

    assert len(result) == 3
    assert {s["job_id"] for s in result} == {"0", "1", "2"}


@pytest.mark.asyncio
async def test_summarize_batch_handles_timeout() -> None:
    """Batch that exceeds timeout returns [] instead of hanging."""
    import asyncio as _asyncio

    batch = [_make_listing("1")]

    async def slow_invoke(*args: Any, **kwargs: Any) -> None:
        await _asyncio.sleep(60)

    with patch("app.agent.job_search.nodes._get_summary_llm") as mock_get:
        mock_get.return_value.ainvoke = slow_invoke
        with patch("app.agent.job_search.nodes.SUMMARY_LLM_TIMEOUT", 0.1):
            state = _make_state()
            state["search_results"] = batch
            result = await summarize_jobs_parallel(state)

    assert result == {"summaries": []}


# ---------------------------------------------------------------------------
# finalize_state
# ---------------------------------------------------------------------------


def _make_listing_with_full_desc(job_id: str, description: str = "raw snippet") -> JobListing:
    return JobListing(
        id=job_id,
        title=f"Job {job_id}",
        company=f"Co {job_id}",
        location="London, GB",
        salary="$80k",
        description=description,
        full_description=f"Full description for {job_id} " * 50,
        apply_link=f"https://{job_id}.com/apply",
    )


def test_finalize_state_merges_ai_descriptions() -> None:
    listings = [_make_listing_with_full_desc(str(i)) for i in range(3)]
    summaries = [{"job_id": str(i), "description": f"AI summary {i}"} for i in range(3)]
    state = _make_state()
    state["search_results"] = listings
    state["summaries"] = summaries

    result = finalize_state(state)

    assert len(result["job_payloads"]) == 3
    for i, payload in enumerate(result["job_payloads"]):
        assert payload["description"] == f"AI summary {i}"
        assert "full_description" in payload
        assert "apply_link" in payload


def test_finalize_state_tool_message_strips_full_description() -> None:
    listings = [_make_listing_with_full_desc(str(i)) for i in range(3)]
    summaries = [{"job_id": str(i), "description": f"AI summary {i}"} for i in range(3)]
    state = _make_state()
    state["search_results"] = listings
    state["summaries"] = summaries

    result = finalize_state(state)

    import json

    content = result["tool_message_content"]
    assert "full_description" not in content
    parsed = json.loads(content)
    assert len(parsed["jobs"]) == 3
    for entry in parsed["jobs"]:
        assert "id" in entry
        assert "title" in entry
        assert "company" in entry
        assert "location" in entry
        assert "salary" in entry
        assert "description" in entry
        assert "apply_link" in entry


def test_finalize_state_keeps_raw_snippet_on_summary_miss() -> None:
    listings = [_make_listing_with_full_desc(str(i), description=f"raw {i}") for i in range(3)]
    summaries = [
        {"job_id": "0", "description": "AI summary 0"},
        {"job_id": "1", "description": "AI summary 1"},
    ]
    state = _make_state()
    state["search_results"] = listings
    state["summaries"] = summaries

    result = finalize_state(state)

    assert result["job_payloads"][0]["description"] == "AI summary 0"
    assert result["job_payloads"][1]["description"] == "AI summary 1"
    assert result["job_payloads"][2]["description"] == "raw 2"


def test_finalize_state_empty_search_results() -> None:
    state = _make_state()
    state["search_results"] = []
    state["summaries"] = []

    result = finalize_state(state)

    import json

    assert result["job_payloads"] == []
    parsed = json.loads(result["tool_message_content"])
    assert parsed["jobs"] == []
    assert "No jobs found" in parsed["note"]


def test_finalize_state_empty_summaries() -> None:
    listings = [_make_listing_with_full_desc(str(i), description=f"raw {i}") for i in range(3)]
    state = _make_state()
    state["search_results"] = listings
    state["summaries"] = []

    result = finalize_state(state)

    assert len(result["job_payloads"]) == 3
    for i, payload in enumerate(result["job_payloads"]):
        assert payload["description"] == f"raw {i}"
        assert "full_description" in payload


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
