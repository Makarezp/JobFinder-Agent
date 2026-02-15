from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from app.agent.job_search.nodes import inspect_job, search_jobs
from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobSpecialistInput


def test_search_jobs_invalid_mode() -> None:
    """Test that search_jobs returns empty dict if mode is not 'search'."""
    state = cast(
        JobSpecialistState, {"input": JobSpecialistInput(mode="inspect", url="http://example.com"), "search_results": None, "inspect_result": None}
    )
    result = search_jobs(state)
    assert result == {}


def test_search_jobs_adzuna_error() -> None:
    """Test search_jobs handles Adzuna API failure gracefully."""
    state = cast(
        JobSpecialistState,
        {"input": JobSpecialistInput(mode="search", query="fail", location="London"), "search_results": None, "inspect_result": None},
    )

    with patch("app.agent.job_search.nodes.adzuna_api_search") as mock_tool:
        # Mock invoke to raise an exception
        mock_tool.invoke.side_effect = Exception("API Down")

        result = search_jobs(state)

        assert "search_results" in result
        assert result["search_results"] == []


def test_search_jobs_parsing_error() -> None:
    """Test search_jobs handles malformed API input gracefully."""
    state = cast(
        JobSpecialistState,
        {"input": JobSpecialistInput(mode="search", query="python", location="London"), "search_results": None, "inspect_result": None},
    )

    with patch("app.agent.job_search.nodes.adzuna_api_search") as mock_tool:
        # Return a list with one valid and one malformed result
        mock_tool.invoke.return_value = [
            {"id": "1", "title": "Good Job", "company": "Co", "location": "Loc", "url": "url", "snippet": "snippet"},
            {"error": "some api error line"},  # Should be skipped
            {"title": "Missing ID"},  # Should raise validation error and be skipped
        ]

        result = search_jobs(state)

        assert len(result["search_results"]) == 1
        assert result["search_results"][0].title == "Good Job"


@pytest.mark.asyncio
async def test_inspect_job_invalid_mode() -> None:
    """Test inspect_job returns empty dict if mode is not 'inspect'."""
    state = cast(JobSpecialistState, {"input": JobSpecialistInput(mode="search", query="python"), "search_results": None, "inspect_result": None})
    result = await inspect_job(state)
    assert result == {}


@pytest.mark.asyncio
async def test_inspect_job_scraping_error() -> None:
    """Test inspect_job handles scraping failure."""
    state = cast(
        JobSpecialistState, {"input": JobSpecialistInput(mode="inspect", url="http://fail.com"), "search_results": None, "inspect_result": None}
    )

    with patch("app.agent.job_search.nodes.scrape_website") as mock_scraper:
        # Mock ainvoke (async)
        mock_scraper.ainvoke = AsyncMock(side_effect=Exception("Scrape Timeout"))

        result = await inspect_job(state)

        assert "inspect_result" in result
        detail = result["inspect_result"]
        # Should contain error message in description
        assert "Error scraping" in detail.full_description


@pytest.mark.asyncio
async def test_inspect_job_invalid_context() -> None:
    """Test inspect_job with invalid summary_context falls back to minimal."""
    state = cast(
        JobSpecialistState,
        {
            "input": JobSpecialistInput(
                mode="inspect",
                url="http://example.com",
                summary_context={"invalid_field": "oops"},  # Invalid schema
            ),
            "search_results": None,
            "inspect_result": None,
        },
    )

    with patch("app.agent.job_search.nodes.scrape_website") as mock_scraper:
        mock_scraper.ainvoke = AsyncMock(return_value="Scraped content")

        result = await inspect_job(state)

        detail = result["inspect_result"]
        assert detail.summary.title == "Unknown Title"
        assert detail.full_description == "Scraped content"
