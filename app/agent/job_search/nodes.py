import logging
from typing import Any

from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobDetail, JobSummary
from app.tools.adzuna_api import adzuna_api_search
from app.tools.scraper import scrape_website

logger = logging.getLogger(__name__)


def search_jobs(state: JobSpecialistState) -> dict[str, Any]:
    """
    Execute the search using Adzuna API.
    """
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
                "results_per_page": 10,  # Default
            }
        )
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

    return {"search_results": summaries}


async def inspect_job(state: JobSpecialistState) -> dict[str, Any]:
    """
    Inspect a specific job URL by scraping it.
    """
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

    return {"inspect_result": detail}


def _create_minimal_summary(url: str) -> JobSummary:
    return JobSummary(
        id=url, title="Unknown Title", company="Unknown Company", location="Unknown Location", snippet="No summary provided.", url=url, created=None
    )
