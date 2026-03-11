from typing import Any

import httpx
import structlog
from langchain_core.tools import tool
from langsmith import traceable

from app.agent.schemas import JobSpecialistInput
from app.core.config import settings
from app.core.logging import log_timing

logger = structlog.get_logger(__name__)

_JSEARCH_BASE_URL = "https://jsearch.p.rapidapi.com/search"
_JSEARCH_HOST = "jsearch.p.rapidapi.com"
_FULL_DESCRIPTION_MAX_CHARS = 1_000
_DESCRIPTION_SNIPPET_CHARS = 300


def _format_salary(job: dict[str, Any]) -> str | None:
    salary_min = job.get("job_min_salary")
    salary_max = job.get("job_max_salary")
    period = job.get("job_salary_period") or "YEAR"

    if salary_min and salary_max:
        return f"${salary_min:,.0f} - ${salary_max:,.0f} per {period}"
    if salary_min:
        return f"From ${salary_min:,.0f} per {period}"
    if salary_max:
        return f"Up to ${salary_max:,.0f} per {period}"

    fallback = job.get("job_salary")
    if fallback:
        return str(fallback)

    return None


def _format_location(job: dict[str, Any]) -> str:
    parts = [job.get("job_city"), job.get("job_state"), job.get("job_country")]
    return ", ".join(p for p in parts if p)


def _format_apply_link(job: dict[str, Any]) -> str:
    link = job.get("job_apply_link")
    if not link:
        apply_options = job.get("apply_options") or []
        if apply_options:
            link = apply_options[0].get("apply_link")
    return link or ""


@tool("jsearch_api_search", args_schema=JobSpecialistInput)
@traceable
def jsearch_api_search(
    query: str,
    country: str,
    date_posted: str = "month",
    remote_only: bool = False,
    page: int = 1,
    num_pages: int = 2,
) -> list[dict[str, Any]] | str:
    """
    Searches for jobs using the JSearch API (RapidAPI).
    Returns a list of JobListing-shaped dictionaries, or an error string on failure.
    """
    api_key = settings.JSEARCH_API_KEY

    logger.info("Tool Started: jsearch_api_search", query=query, page=page, remote_only=remote_only)

    if not api_key:
        return "Error: JSEARCH_API_KEY is not configured."

    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": _JSEARCH_HOST,
    }

    params: dict[str, Any] = {
        "query": query,
        "page": str(page),
        "num_pages": str(num_pages),
        "date_posted": date_posted,
        "country": country,
    }

    if remote_only:
        params["work_from_home"] = "true"

    try:
        with log_timing("jsearch_api_search", logger):
            with httpx.Client() as client:
                response = client.get(_JSEARCH_BASE_URL, headers=headers, params=params, timeout=15.0)
            response.raise_for_status()

        data = response.json()
        raw_jobs: list[dict[str, Any]] = data.get("data") or []

        if not raw_jobs:
            logger.info("Tool Completed: jsearch_api_search", result_count=0)
            return []

        listings: list[dict[str, Any]] = []
        for job in raw_jobs:
            full_desc: str = job.get("job_description") or ""
            snippet = full_desc[:_DESCRIPTION_SNIPPET_CHARS]
            truncated_full = full_desc[:_FULL_DESCRIPTION_MAX_CHARS]

            listing: dict[str, Any] = {
                "id": job.get("job_id", ""),
                "title": job.get("job_title", "N/A"),
                "company": job.get("employer_name", "N/A"),
                "location": _format_location(job),
                "salary": _format_salary(job),
                "description": snippet,
                "full_description": truncated_full,
                "apply_link": _format_apply_link(job),
            }
            listings.append(listing)

        logger.info("Tool Completed: jsearch_api_search", result_count=len(listings))
        return listings

    except httpx.HTTPStatusError as e:
        logger.error("jsearch_api_search HTTP error", status_code=e.response.status_code, detail=str(e))
        return f"Error: JSearch API returned status {e.response.status_code}. Details: {e.response.text[:200]}"

    except httpx.RequestError as e:
        logger.error("jsearch_api_search request error", detail=str(e))
        return f"Error: Failed to connect to JSearch API. Details: {e}"
