from typing import Any

import structlog

from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobListing
from app.tools.jsearch_api import jsearch_api_search

logger = structlog.get_logger(__name__)


def search_jobs(state: JobSpecialistState) -> dict[str, Any]:
    """Execute the job search using the JSearch API."""
    logger.info("Node Started: search_jobs")
    input_data = state["input"]

    logger.info("Job Specialist: Searching", query=input_data.query, page=input_data.page)

    raw_results = jsearch_api_search.invoke(
        {
            "query": input_data.query,
            "date_posted": input_data.date_posted,
            "remote_only": input_data.remote_only,
            "page": input_data.page,
            "country": input_data.country,
        }
    )

    if isinstance(raw_results, str):
        logger.error("JSearch tool returned an error", error=raw_results)
        return {"search_results": []}

    listings: list[JobListing] = []
    for r in raw_results:
        try:
            listing = JobListing(
                id=r.get("id", ""),
                title=r.get("title", "N/A"),
                company=r.get("company", "N/A"),
                location=r.get("location", ""),
                salary=r.get("salary"),
                description=r.get("description", ""),
                full_description=r.get("full_description"),
                apply_link=r.get("apply_link", ""),
            )
            listings.append(listing)
        except (ValueError, TypeError) as e:
            logger.warning("Failed to parse JobListing", error=str(e), data=r)

    job_summaries = [f"{job.title} @ {job.company}" for job in listings]
    logger.info("Node Completed: search_jobs", result_count=len(listings), job_summaries=job_summaries)
    return {"search_results": listings}
