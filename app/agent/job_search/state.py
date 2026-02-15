from typing import TypedDict

from app.agent.schemas import JobDetail, JobSpecialistInput, JobSummary


class JobSpecialistState(TypedDict):
    """
    State for the Job Search Specialist subgraph.
    """

    input: JobSpecialistInput
    # Output can be a list of summaries OR a single detail
    # We can use a union or separate fields
    search_results: list[JobSummary] | None
    inspect_result: JobDetail | None
