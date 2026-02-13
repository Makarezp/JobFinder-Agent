import asyncio
import logging
from typing import Annotated, Any

from crawl4ai import AsyncWebCrawler
from langchain_core.tools import tool
from pydantic import BaseModel, BeforeValidator, Field

logger = logging.getLogger(__name__)


def ensure_string(v: str | list[str] | None) -> str | None:
    """Coerces a list of strings to a single string, or returns the original string."""
    if v is None:
        return None
    if isinstance(v, list):
        # Join with space (or comma, but space is generally safer for search queries)
        # For location, comma might be better, but Adzuna handles spaces well enough
        return " ".join([str(i) for i in v if i])
    return str(v)


class AdzunaSearchArgs(BaseModel):
    # We use Annotated + BeforeValidator to sanitize inputs BEFORE Pydantic validation
    # This simplifies the schema for the LLM (it sees 'string') but handles lists gracefully.
    keywords: Annotated[str, BeforeValidator(ensure_string)] = Field(
        ..., description="The job title or keywords to search for."
    )
    location: Annotated[str, BeforeValidator(ensure_string)] | None = Field(
        default=None, description="The location to search for jobs (e.g., 'London')."
    )
    country: str = Field(
        default="gb",
        description="The country code to search in (e.g., 'gb' for UK, 'us' for USA).",
    )
    results_per_page: int = Field(default=10, description="Number of results to return (approximate).")


@tool(args_schema=AdzunaSearchArgs)
def adzuna_search(
    keywords: str,
    location: str | None = None,
    country: str = "gb",
    results_per_page: int = 10,
) -> str:
    """
    Searches for jobs by scraping the Adzuna website.
    Best for UK-based job searches as it captures significantly more results than the API.
    To find remote jobs, include 'remote' in your keywords.
    """
    # Construct the Adzuna search URL
    # Example: https://www.adzuna.co.uk/jobs/search?q=android%20developer%20remote&w=London
    base_url = "https://www.adzuna.co.uk/jobs/search"

    # Inputs are already ensured to be strings by Pydantic BeforeValidator

    # Simple query parameter construction
    query_parts = [f"q={keywords.replace(' ', '%20')}"]

    if location:
        query_parts.append(f"w={location.replace(' ', '%20')}")

    # Add remote filter if "remote" is in keywords, as website supports this
    if "remote" in keywords.lower():
        # This is the "magic" param found during research that boosts results
        query_parts.append("remote_only=1")

    full_url = f"{base_url}?{'&'.join(query_parts)}"

    # Check country support
    if country.lower() not in ["gb", "uk"]:
        msg = "Error: This scraping tool currently is optimized for UK searches (country='gb')."
        logger.warning(msg)
        return msg

    try:
        logger.info(f"Scraping Adzuna URL: {full_url}")

        # We need to run the async crawler in a sync context for the tool
        async def run_crawl() -> Any:
            async with AsyncWebCrawler(verbose=True) as crawler:
                return await crawler.arun(url=full_url)

        result = asyncio.run(run_crawl())

        if not result.success:
            msg = f"Failed to scrape Adzuna: {result.error_message}"
            logger.error(msg)
            return msg

        content = str(result.markdown)

        output = f"**Scraped Adzuna Results for '{keywords}'**\n"
        output += f"Source URL: {full_url}\n\n"

        # Simple extraction heuristic - find the job list section
        # We look for the first occurrence of a job listing pattern or a header
        # Based on test output, jobs often start after "## [Company ]"

        start_idx = content.find("## [Company ]")
        if start_idx != -1:
            # Just take a chunk of text starting from there
            extracted_jobs = content[start_idx : start_idx + 8000]  # Increased buffer
            output += extracted_jobs
        else:
            # Fallback: return the beginning of the markdown if specific header not found
            output += content[:5000]

        logger.info(f"Adzuna search result: {output}")
        return output

    except Exception as e:
        logger.error(f"Adzuna scraping error: {e}")
        return f"Error scraping Adzuna: {str(e)}"
