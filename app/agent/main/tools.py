from typing import Any

from langchain_core.tools import tool

from app.agent.schemas import AgentResponse, JobListing, JobSpecialistInput
from app.tools.memory import (
    delete_preference,
    save_preference,
    update_my_profile,
)


@tool(args_schema=JobSpecialistInput)
def job_specialist_tool(
    mode: str,
    query: str | None = None,
    location: str | None = None,
    url: str | None = None,
    summary_context: dict[str, Any] | None = None,
) -> str:
    """
    Delegates job search and inspection tasks to the Job Specialist Agent.
    - Mode 'search': Finds jobs based on query/location. Returns a list of summaries.
    - Mode 'inspect': Fetches full details for a specific job URL. Returns a detailed description.
    """
    return "Job Specialist invoked."


# --- Tool: final_answer ---
@tool(args_schema=AgentResponse)
def final_answer(text_response: str, jobs: list[JobListing] | None = None) -> str:
    """Present the final response to the user with optional job listings."""
    if jobs is None:
        jobs = []
    return "Final Answer Processed"


main_tools = [
    job_specialist_tool,
    final_answer,
    update_my_profile,
    save_preference,
    delete_preference,
]
