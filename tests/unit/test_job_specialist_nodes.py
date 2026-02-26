from typing import cast
from unittest.mock import patch

import pytest

from app.agent.job_search.nodes import inspect_job, search_jobs
from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobListing, JobSpecialistInput


def test_search_jobs_invalid_mode() -> None:
    """Test that search_jobs returns empty dict if mode is not 'search'."""
    state = cast(
        JobSpecialistState,
        {"input": JobSpecialistInput(mode="inspect", url="http://example.com"), "search_results": None},
    )
    result = search_jobs(state)
    assert result == {}


def test_search_jobs_adzuna_error() -> None:
    """Test search_jobs handles Adzuna API failure gracefully."""
    state = cast(
        JobSpecialistState,
        {"input": JobSpecialistInput(mode="search", query="fail", location="London"), "search_results": None},
    )

    with patch("app.agent.job_search.nodes.adzuna_api_search") as mock_tool:
        mock_tool.invoke.side_effect = Exception("API Down")

        result = search_jobs(state)

        assert "search_results" in result
        assert result["search_results"] == []


def test_search_jobs_parsing_error() -> None:
    """Test search_jobs handles malformed API input gracefully."""
    state = cast(
        JobSpecialistState,
        {"input": JobSpecialistInput(mode="search", query="python", location="London"), "search_results": None},
    )

    with patch("app.agent.job_search.nodes.adzuna_api_search") as mock_tool:
        # Adzuna returns dicts with 'snippet' and 'url' fields
        mock_tool.invoke.return_value = [
            {"id": "1", "title": "Good Job", "company": "Co", "location": "Loc", "url": "http://co.com", "snippet": "snippet"},
            {"error": "some api error line"},  # Should be skipped — has "error" key
            {},  # Parsed with defaults — title="N/A", description="", apply_link=""
        ]

        result = search_jobs(state)

        assert len(result["search_results"]) == 2
        listing: JobListing = result["search_results"][0]
        assert listing.title == "Good Job"
        assert listing.description == "snippet"
        assert listing.apply_link == "http://co.com"


@pytest.mark.asyncio
async def test_inspect_job_stub_returns_empty_dict() -> None:
    """inspect_job is a stub pending removal in Ticket 6.3 — always returns {}."""
    state = cast(
        JobSpecialistState,
        {"input": JobSpecialistInput(mode="inspect", url="http://example.com"), "search_results": None},
    )
    result = await inspect_job(state)
    assert result == {}
