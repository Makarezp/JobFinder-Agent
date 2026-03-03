from typing import cast
from unittest.mock import patch

from app.agent.job_search.nodes import search_jobs
from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobListing, JobSpecialistInput


def _make_state(query: str = "python developer", page: int = 1) -> JobSpecialistState:
    return cast(
        JobSpecialistState,
        {"input": JobSpecialistInput(query=query, page=page), "search_results": None},
    )


def test_search_jobs_returns_empty_on_tool_error() -> None:
    """search_jobs returns empty list when jsearch_api_search returns an error string."""
    state = _make_state(query="fail")

    with patch("app.agent.job_search.nodes.jsearch_api_search") as mock_tool:
        mock_tool.invoke.return_value = "Error: JSearch API returned status 429."

        result = search_jobs(state)

        assert "search_results" in result
        assert result["search_results"] == []


def test_search_jobs_maps_jsearch_fields_correctly() -> None:
    """search_jobs correctly maps JSearch-shaped dicts to JobListing objects."""
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

        result = search_jobs(state)

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


def test_search_jobs_applies_defaults_for_missing_fields() -> None:
    """search_jobs applies defaults (e.g. title='N/A') for partially-filled entries."""
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

        result = search_jobs(state)

        assert len(result["search_results"]) == 2
        assert result["search_results"][0].title == "Good Job"
        assert result["search_results"][1].title == "N/A"


def test_search_jobs_passes_correct_args_to_tool() -> None:
    """search_jobs forwards all JobSpecialistInput fields to jsearch_api_search."""
    state = cast(
        JobSpecialistState,
        {
            "input": JobSpecialistInput(
                query="golang engineer",
                date_posted="week",
                employment_types="FULLTIME,CONTRACTOR",
                remote_only=True,
                page=2,
            ),
            "search_results": None,
        },
    )

    with patch("app.agent.job_search.nodes.jsearch_api_search") as mock_tool:
        mock_tool.invoke.return_value = []

        search_jobs(state)

        mock_tool.invoke.assert_called_once_with(
            {
                "query": "golang engineer",
                "country": "us",
                "date_posted": "week",
                "employment_types": "FULLTIME,CONTRACTOR",
                "remote_only": True,
                "page": 2,
            }
        )
