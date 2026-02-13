import logging

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.core.config import settings

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
) -> str:
    """
    Searches for jobs using the Adzuna API.
    Returns a structured list of jobs including title, company, location, salary, and link.
    """
    app_id = settings.ADZUNA_APP_ID
    app_key = settings.ADZUNA_APP_KEY

    if not app_id or not app_key:
        return "Error: Adzuna API credentials (ADZUNA_APP_ID, ADZUNA_APP_KEY) not found."

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
        logger.info(f"Calling Adzuna API: {base_url} with params={params}")

        # Use httpx for the request
        with httpx.Client() as client:
            response = client.get(base_url, params=params, timeout=10.0)

            if response.status_code != 200:
                return f"Error: Adzuna API returned status code {response.status_code}. Details: {response.text}"

            data = response.json()
            results = data.get("results", [])

            if not results:
                return f"No jobs found for '{what}' in '{where}'."

            # Get total count
            total_count = data.get("count", 0)

            # Format results
            formatted_jobs = [f"Found {total_count} total jobs (showing top {results_per_page}):\n"]
            for job in results:
                title = job.get("title", "N/A")
                company = job.get("company", {}).get("display_name", "N/A")
                location = job.get("location", {}).get("display_name", "N/A")
                salary_min = job.get("salary_min")
                salary_max = job.get("salary_max")
                url = job.get("redirect_url")
                description = job.get("description", "")[:200] + "..."  # Truncate description

                # Extra fields
                category = job.get("category", {}).get("label", "N/A")
                created = job.get("created", "N/A")

                # Format Contract/Time info
                c_time = job.get("contract_time", "").replace("_", " ").title()
                c_type = job.get("contract_type", "").replace("_", " ").title()
                type_info = ", ".join(filter(None, [c_type, c_time])) or "N/A"

                salary_str = "Negotiable"
                if salary_min and salary_max:
                    salary_str = f"£{salary_min} - £{salary_max}"
                elif salary_min:
                    salary_str = f"From £{salary_min}"

                job_card = (
                    f"**Title:** {title}\n"
                    f"**Company:** {company}\n"
                    f"**Location:** {location}\n"
                    f"**Salary:** {salary_str}\n"
                    f"**Type:** {type_info}\n"
                    f"**Category:** {category}\n"
                    f"**Posted:** {created}\n"
                    f"**Link:** [Apply Here]({url})\n"
                    f"**Summary:** {description}\n"
                    "---"
                )
                formatted_jobs.append(job_card)

            return "\n".join(formatted_jobs)

    except Exception as e:
        logger.error(f"Adzuna API Error: {e}")
        return f"Error: {str(e)}"
