from typing import Any, cast
from unittest.mock import patch

import pytest

from app.agent.job_search.graph import job_search_graph
from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobSpecialistInput


@pytest.mark.asyncio
async def test_job_search_graph_returns_search_results() -> None:
    """The job_search subgraph invokes jsearch_api_search and returns search_results."""
    input_data = JobSpecialistInput(query="Python Developer in London")
    state = cast(JobSpecialistState, {"input": input_data, "search_results": None})

    mock_jsearch_response = [
        {
            "id": "job_123",
            "title": "Python Developer",
            "company": "Acme Ltd",
            "location": "London, England, GB",
            "salary": "$70,000 - $90,000 per YEAR",
            "description": "Great Python role...",
            "full_description": "Full description here.",
            "apply_link": "https://example.com/apply",
        }
    ]

    with patch("app.agent.job_search.nodes.jsearch_api_search") as mock_tool:
        mock_tool.invoke.return_value = mock_jsearch_response

        result = await job_search_graph.ainvoke(cast(Any, state))

        assert "search_results" in result
        assert len(result["search_results"]) == 1
        assert result["search_results"][0].title == "Python Developer"


@pytest.mark.asyncio
async def test_job_search_graph_handles_tool_error_gracefully() -> None:
    """The job_search subgraph returns an empty list when jsearch_api_search returns an error string."""
    input_data = JobSpecialistInput(query="Python Developer in London")
    state = cast(JobSpecialistState, {"input": input_data, "search_results": None})

    with patch("app.agent.job_search.nodes.jsearch_api_search") as mock_tool:
        mock_tool.invoke.return_value = "Error: JSearch API returned status 429."

        result = await job_search_graph.ainvoke(cast(Any, state))

        assert "search_results" in result
        assert result["search_results"] == []
