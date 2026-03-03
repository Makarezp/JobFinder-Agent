from langchain_core.tools import tool

from app.agent.schemas import AgentResponse, JobListing, JobSpecialistInput
from app.tools.memory import (
    delete_preference,
    save_preference,
    update_my_profile,
)


@tool(args_schema=JobSpecialistInput)
def job_specialist_tool(
    query: str,
    country: str = "us",
    date_posted: str = "all",
    employment_types: str | None = None,
    remote_only: bool = False,
    page: int = 1,
) -> str:
    """
    Delegates job search to the Job Specialist Agent.
    Returns a list of job listings with titles, companies, locations,
    salaries, descriptions (truncated to 1,000 characters), and apply links.
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
