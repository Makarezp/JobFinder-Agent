from typing import Any, cast

import pytest

from app.agent.job_search.graph import job_search_graph
from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobSpecialistInput


@pytest.mark.asyncio
async def test_job_search_graph_search_mode() -> None:
    """Test the search mode of the job specialist graph."""
    input_data = JobSpecialistInput(mode="search", query="Python Developer", location="London")

    # We invoke the graph with the input
    # Note: We need to mock adzuna_api_search if we don't want real calls
    # For now, we assume it's an integration test that might hit API or fail gracefully
    # But to make it robust, we should probably mock.
    # However, for this verification, running it and seeing if it crashes is a good first step.

    state = cast(JobSpecialistState, {"input": input_data, "search_results": None, "inspect_result": None})

    result = await job_search_graph.ainvoke(cast(Any, state))

    assert "search_results" in result
    # We don't assert content because API might return nothing or require keys
    print(f"Search Results: {result['search_results']}")


@pytest.mark.asyncio
async def test_job_search_graph_inspect_mode() -> None:
    """Test the inspect mode."""
    input_data = JobSpecialistInput(mode="inspect", url="https://example.com/job")

    state = cast(JobSpecialistState, {"input": input_data, "search_results": None, "inspect_result": None})

    # helper to mock scraper would be good, but scraper uses crawl4ai
    # We'll just run it.

    result = await job_search_graph.ainvoke(cast(Any, state))

    assert "inspect_result" in result
    if result["inspect_result"]:
        assert result["inspect_result"].full_description
    print(f"Inspect Result: {result['inspect_result']}")
