from typing import Any

import structlog

from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobListing
from app.tools.adzuna_api import adzuna_api_search

logger = structlog.get_logger(__name__)


def search_jobs(state: JobSpecialistState) -> dict[str, Any]:
    """
    Execute the search using Adzuna API.
    NOTE: Adzuna will be replaced by jsearch_api_search in Ticket 6.3.
    """
    logger.info("Node Started: search_jobs")
    input_data = state["input"]
    if input_data.mode != "search":
        return {}

    logger.info(f"Job Specialist: Searching for '{input_data.query}' in '{input_data.location}'")

    try:
        raw_results = adzuna_api_search.invoke(
            {
                "what": input_data.query or "",
                "where": input_data.location,
                "country": input_data.country,
                "results_per_page": input_data.results_per_page,
                "sort_by": input_data.sort_by,
                "max_days_old": input_data.max_days_old,
                "salary_min": input_data.salary_min,
                "full_time": input_data.full_time,
                "part_time": input_data.part_time,
                "permanent": input_data.permanent,
                "contract": input_data.contract,
            }
        )
        logger.debug("Adzuna Raw Results", results=raw_results)
    except Exception as e:
        logger.error(f"Adzuna search failed: {e}")
        return {"search_results": []}

    listings: list[JobListing] = []
    for r in raw_results:
        if "error" in r:
            logger.warning(f"Adzuna error in result: {r}")
            continue
        try:
            # Remap Adzuna-specific field names to JobListing contract
            listing = JobListing(
                id=r.get("id", ""),
                title=r.get("title", "N/A"),
                company=r.get("company", "N/A"),
                location=r.get("location", "N/A"),
                salary=r.get("salary"),
                description=r.get("snippet", ""),
                apply_link=r.get("url", ""),
            )
            listings.append(listing)
        except Exception as e:
            logger.warning(f"Failed to parse JobListing: {e}. Data: {r}")

    logger.info("Node Completed: search_jobs", extra={"result_count": len(listings)})
    return {"search_results": listings}


async def inspect_job(state: JobSpecialistState) -> dict[str, Any]:
    """
    Inspect node — removed as part of JSearch migration (Ticket 6.3).
    This stub exists only to maintain graph compilation during the transition.
    """
    logger.info("Node Started: inspect_job (stub — pending removal in Ticket 6.3)")
    return {}
