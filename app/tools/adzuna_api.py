import logging
import httpx
from typing import Optional, List
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from app.core.config import settings
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class AdzunaApiArgs(BaseModel):
    what: str = Field(..., description="The job title or keywords to search for.")
    where: Optional[str] = Field(
        default=None, description="The location to search for jobs."
    )
    country: str = Field(default="gb", description="The country code (e.g., 'gb').")
    results_per_page: int = Field(
        default=10, description="Number of results to return."
    )


@tool("adzuna_api_search", args_schema=AdzunaApiArgs)
def adzuna_api_search(
    what: str,
    where: Optional[str] = None,
    country: str = "gb",
    results_per_page: int = 10,
) -> str:
    """
    Searches for jobs using the Adzuna API.
    Returns a structured list of jobs including title, company, location, salary, and link.
    """
    # Try to get from os.environ first (loaded by dotenv), fallback to settings if possible
    app_id = os.getenv("ADZUNA_APP_ID")
    app_key = os.getenv("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        return (
            "Error: Adzuna API credentials (ADZUNA_APP_ID, ADZUNA_APP_KEY) not found."
        )

    # Adzuna API endpoint: https://api.adzuna.com/v1/api/jobs/{country}/search/1
    base_url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"

    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": int(results_per_page),
        "what": what,
        "content-type": "application/json",
    }

    if where:
        params["where"] = where

    try:
        logger.info(
            f"Calling Adzuna API: {base_url} with what='{what}', where='{where}'"
        )

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
            formatted_jobs = [
                f"Found {total_count} total jobs (showing top {results_per_page}):\n"
            ]
            for job in results:
                title = job.get("title", "N/A")
                company = job.get("company", {}).get("display_name", "N/A")
                location = job.get("location", {}).get("display_name", "N/A")
                salary_min = job.get("salary_min")
                salary_max = job.get("salary_max")
                url = job.get("redirect_url")
                description = (
                    job.get("description", "")[:200] + "..."
                )  # Truncate description

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
                    f"**Link:** [Apply Here]({url})\n"
                    f"**Summary:** {description}\n"
                    "---"
                )
                formatted_jobs.append(job_card)

            return "\n".join(formatted_jobs)

    except Exception as e:
        logger.error(f"Adzuna API Error: {e}")
        return f"Error: {str(e)}"
