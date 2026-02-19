from typing import Any

import structlog

from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobDetail, JobSummary
from app.tools.adzuna_api import adzuna_api_search
from app.tools.scraper import scrape_website

logger = structlog.get_logger(__name__)


def search_jobs(state: JobSpecialistState) -> dict[str, Any]:
    """
    Execute the search using Adzuna API.
    """
    logger.info("Node Started: search_jobs")
    input_data = state["input"]
    # We trust the input mode is verified by router, but we can double check
    if input_data.mode != "search":
        return {}

    logger.info(f"Job Specialist: Searching for '{input_data.query}' in '{input_data.location}'")

    # Call the tool (which now returns list[dict])
    try:
        raw_results = adzuna_api_search.invoke(
            {
                "what": input_data.query or "",  # Handle None
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

    # validate and convert to JobSummary objects
    summaries = []
    for r in raw_results:
        if "error" in r:
            logger.warning(f"Adzuna error in result: {r}")
            continue
        try:
            # Ensure ID is present. The tool sets it.
            summaries.append(JobSummary(**r))
        except Exception as e:
            logger.warning(f"Failed to parse JobSummary: {e}. Data: {r}")

    logger.info("Node Completed: search_jobs", extra={"result_count": len(summaries)})
    return {"search_results": summaries}


async def inspect_job(state: JobSpecialistState) -> dict[str, Any]:
    """
    Inspect a specific job URL by scraping it.
    """
    logger.info("Node Started: inspect_job")
    input_data = state["input"]
    if input_data.mode != "inspect" or not input_data.url:
        return {}

    logger.info(f"Job Specialist: Inspecting URL {input_data.url}")

    # Scrape
    try:
        scraped_content = await scrape_website.ainvoke({"url": input_data.url})
    except Exception as e:
        logger.error(f"Scrape failed: {e}")
        scraped_content = f"Error scraping: {e}"

    # Construct JobDetail
    # Use summary_context if available, otherwise creaate a minimal one
    summary_data = input_data.summary_context
    if summary_data:
        try:
            summary = JobSummary(**summary_data)
        except Exception as e:
            logger.warning(f"Invalid summary context: {e}")
            summary = _create_minimal_summary(input_data.url)
    else:
        summary = _create_minimal_summary(input_data.url)

    # For now, we populate full_description with scraped content
    detail = JobDetail(
        summary=summary,
        full_description=str(scraped_content),
        requirements=[],  # Placeholder
        benefits=[],  # Placeholder
    )

    logger.info("Node Completed: inspect_job", extra={"url": input_data.url, "has_content": bool(scraped_content)})
    return {"inspect_result": detail}


def _create_minimal_summary(url: str) -> JobSummary:
    return JobSummary(
        id=url, title="Unknown Title", company="Unknown Company", location="Unknown Location", snippet="No summary provided.", url=url, created=None
    )
