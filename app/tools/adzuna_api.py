import logging
from typing import Any

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import log_timing

logger = logging.getLogger(__name__)


class AdzunaApiArgs(BaseModel):
    what: str = Field(..., description="The job title or keywords to search for.")
    where: str | None = Field(default=None, description="The location to search for jobs.")
    country: str = Field(default="gb", description="The country code (e.g., 'gb').")
    results_per_page: int = Field(default=10, description="Number of results to return.")
    sort_by: str | None = Field(default=None, description="Sort by 'date' or 'salary'.")
    max_days_old: int | None = Field(default=None, description="Filter jobs posted within these many days.")
    salary_min: int | None = Field(default=None, description="Minimum salary.")
    full_time: bool | None = Field(default=None, description="Filter for full-time jobs.")
    part_time: bool | None = Field(default=None, description="Filter for part-time jobs.")
    permanent: bool | None = Field(default=None, description="Filter for permanent jobs.")
    contract: bool | None = Field(default=None, description="Filter for contract jobs.")


@tool("adzuna_api_search", args_schema=AdzunaApiArgs)
def adzuna_api_search(
    what: str,
    where: str | None = None,
    country: str = "gb",
    results_per_page: int = 10,
    sort_by: str | None = None,
    max_days_old: int | None = None,
    salary_min: int | None = None,
    full_time: bool | None = None,
    part_time: bool | None = None,
    permanent: bool | None = None,
    contract: bool | None = None,
) -> list[dict[str, Any]]:
    """
    Searches for jobs using the Adzuna API.
    Returns a list of JobSummary dictionaries.
    """
    app_id = settings.ADZUNA_APP_ID
    app_key = settings.ADZUNA_APP_KEY

    if not app_id or not app_key:
        return [{"error": "Adzuna API credentials (ADZUNA_APP_ID, ADZUNA_APP_KEY) not found."}]

    # Adzuna API endpoint: https://api.adzuna.com/v1/api/jobs/{country}/search/1
    base_url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"

    params: dict[str, str | int] = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": int(results_per_page),
        "what": what,
        "content-type": "application/json",
    }

    if where:
        params["where"] = where

    if sort_by:
        params["sort_by"] = sort_by

    if max_days_old:
        params["max_days_old"] = max_days_old

    if salary_min:
        params["salary_min"] = salary_min

    # Handle contract_time (full_time/part_time) - API takes 1 for yes
    if full_time:
        params["full_time"] = 1
    if part_time:
        params["part_time"] = 1

    # Handle contract_type (permanent/contract) - API takes 1 for yes
    if permanent:
        params["permanent"] = 1
    if contract:
        params["contract"] = 1

    try:
        with log_timing("adzuna_api_search", logger):
            # Use httpx for the request
            with httpx.Client() as client:
                response = client.get(base_url, params=params, timeout=10.0)

            if response.status_code != 200:
                logger.error(f"Adzuna API Error: Status {response.status_code}. Raw Response: {response.text}")
                return [{"error": f"Adzuna API returned status code {response.status_code}. Details: {response.text}"}]

            data = response.json()
            logger.debug(f"Adzuna Raw Response Data: {data}")
            results = data.get("results", [])

            if not results:
                return []

            # Format results
            job_summaries = []
            for job in results:
                # Basic fields
                title = job.get("title", "N/A")
                company = job.get("company", {}).get("display_name", "N/A")
                location = job.get("location", {}).get("display_name", "N/A")
                url = job.get("redirect_url", "")
                job_id = str(job.get("id", "")) or url
                created = job.get("created", None)

                # Description snippet
                description = job.get("description", "")
                snippet = description[:200] + "..." if len(description) > 200 else description

                # Salary
                salary_min_val = job.get("salary_min")
                salary_max_val = job.get("salary_max")
                is_predicted = job.get("salary_is_predicted")
                salary_str = "Negotiable"
                if salary_min_val and salary_max_val:
                    salary_str = f"£{salary_min_val} - £{salary_max_val}"
                elif salary_min_val:
                    salary_str = f"From £{salary_min_val}"

                if is_predicted:
                    salary_str += " (Predicted)"

                # Construct JobSummary dict (avoiding full Pydantic validation for speed in tool, but matching schema)
                summary = {
                    "id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "salary": salary_str,
                    "snippet": snippet,
                    "url": url,
                    "created": created,
                }
                job_summaries.append(summary)

            return job_summaries

    except Exception as e:
        logger.error(f"Adzuna API Error: {e}")
        return [{"error": str(e)}]
