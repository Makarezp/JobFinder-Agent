from langchain_core.tools import tool

from app.agent.schemas import AgentResponse, JobListing
from app.tools.adzuna_api import adzuna_api_search
from app.tools.memory import (
    delete_preference,
    save_preference,
    update_my_profile,
)
from app.tools.scraper import scrape_website


# --- Tool: final_answer ---
@tool(args_schema=AgentResponse)
def final_answer(text_response: str, jobs: list[JobListing] | None = None) -> str:
    """Present the final response to the user with optional job listings."""
    if jobs is None:
        jobs = []
    return "Final Answer Processed"


main_tools = [
    adzuna_api_search,
    scrape_website,
    final_answer,
    update_my_profile,
    save_preference,
    delete_preference,
]
