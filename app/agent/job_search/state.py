from typing import TypedDict

from app.agent.schemas import JobListing, JobSpecialistInput


class JobSpecialistState(TypedDict):
    """
    State for the Job Search Specialist subgraph.
    """

    input: JobSpecialistInput
    search_results: list[JobListing] | None
