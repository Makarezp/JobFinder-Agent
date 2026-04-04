"""Integration tests for the Job Specialist 2-node subgraph (summarize → finalize)."""

from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.job_search.graph import job_search_graph
from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobListing, JobSpecialistInput, JobSummary, JobSummaryBatch


def _make_listing(job_id: str, description: str = "Raw snippet.") -> JobListing:
    return JobListing(
        id=job_id,
        title=f"Job {job_id}",
        company=f"Co {job_id}",
        location="London, GB",
        salary="$80k",
        description=description,
        full_description=f"Full description for {job_id}. " * 100,
        apply_link=f"https://{job_id}.com/apply",
    )


def _mock_summary_llm(listings: list[JobListing]) -> AsyncMock:
    """Return a mock LLM that produces valid summaries for any batch."""

    async def _ainvoke(messages: Any) -> JobSummaryBatch:
        import json

        jobs = json.loads(messages[-1].content)
        return JobSummaryBatch(summaries=[JobSummary(job_id=j["id"], recommend=True, description=f"AI summary for {j['id']}") for j in jobs])

    mock = AsyncMock(side_effect=_ainvoke)
    return mock


@pytest.mark.asyncio
async def test_subgraph_produces_job_payloads_and_tool_message() -> None:
    """The 2-node subgraph produces job_payloads with full data and tool_message_content without full_description."""
    import json

    listings = [_make_listing(str(i)) for i in range(3)]

    state: JobSpecialistState = {
        "input": JobSpecialistInput(query="test", country="gb"),
        "search_results": listings,
        "user_profile": None,
        "preferences": None,
    }

    with patch("app.agent.job_search.nodes._get_summary_llm") as mock_get:
        mock_get.return_value.ainvoke = _mock_summary_llm(listings)
        result = await job_search_graph.ainvoke(cast(Any, state))

    # job_payloads has full data
    assert len(result["job_payloads"]) == 3
    for payload in result["job_payloads"]:
        assert "full_description" in payload
        assert "apply_link" in payload
        assert payload["description"].startswith("AI summary for")

    # tool_message_content strips full_description
    content = result["tool_message_content"]
    assert "full_description" not in content
    parsed = json.loads(content)
    assert len(parsed["jobs"]) == 3


@pytest.mark.asyncio
async def test_subgraph_handles_empty_search_results() -> None:
    """The subgraph handles empty search_results gracefully."""
    import json

    state: JobSpecialistState = {
        "input": JobSpecialistInput(query="test", country="gb"),
        "search_results": [],
        "user_profile": None,
        "preferences": None,
    }

    result = await job_search_graph.ainvoke(cast(Any, state))

    assert result["job_payloads"] == []
    parsed = json.loads(result["tool_message_content"])
    assert parsed["jobs"] == []
